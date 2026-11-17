#include "video/HevcFileDecoder.h"

#include <QCoreApplication>
#include <QDeadlineTimer>
#include <QFileInfo>
#include <QLocalServer>
#include <QLocalSocket>
#include <QProcess>
#include <QUuid>
#include <exception>
#include <utility>

namespace rm27::video {
namespace {

constexpr int MaxWidth = 1920;
constexpr int MaxHeight = 1080;
// HEVC may pad the coded picture to a full coding-tree row before cropping to 1080.
constexpr int MaxCodedPixels = MaxWidth * 1088;
constexpr int ShortClipTimeoutMs = 120000;
constexpr int StopPollMs = 50;

// YUV4MPEG2 supplies the dimensions and a marker before each fixed-size frame.
// Read directly into an owning QByteArray. Only the current frame is assembled here.
class PixelPipe {
public:
    PixelPipe(QLocalSocket &socket, const std::atomic_bool &stopRequested,
              QDeadlineTimer deadline, QString &error)
        : socket_(socket), stopRequested_(stopRequested), deadline_(deadline), error_(error) {}

    QByteArray readLine()
    {
        QByteArray line;
        while (waitForData()) {
            char byte;
            if (!socket_.getChar(&byte)) {
                error_ = socket_.errorString();
                return {};
            }
            if (byte == '\n') {
                if (line.isEmpty())
                    error_ = QStringLiteral("FFmpeg 像素流的头部为空");
                return line;
            }
            line.append(byte);
            if (line.size() >= 1024) {
                error_ = QStringLiteral("FFmpeg 像素流的头部过长");
                return {};
            }
        }
        if (!line.isEmpty() && error_.isEmpty() && !stopRequested_)
            error_ = QStringLiteral("FFmpeg 像素流的头部中断");
        return {};
    }

    QByteArray readPixels(int size)
    {
        QByteArray pixels(size, Qt::Uninitialized);
        qsizetype received = 0;
        while (received < size && waitForData()) {
            const auto count = socket_.read(pixels.data() + received, size - received);
            if (count <= 0) {
                error_ = socket_.errorString();
                return {};
            }
            received += count;
        }
        if (received == size)
            return pixels;
        if (error_.isEmpty() && !stopRequested_)
            error_ = QStringLiteral("FFmpeg 像素流在帧内中断");
        return {};
    }

private:
    bool waitForData()
    {
        while (!stopRequested_) {
            if (deadline_.hasExpired()) {
                error_ = QStringLiteral("本地短片解码超时");
                return false;
            }
            if (socket_.bytesAvailable() > 0)
                return true;
            if (socket_.state() == QLocalSocket::UnconnectedState)
                break;
            if (!socket_.waitForReadyRead(StopPollMs))
                QCoreApplication::processEvents(); // Drain stderr even if the input yields no frame.
        }
        return false;
    }

    QLocalSocket &socket_;
    const std::atomic_bool &stopRequested_;
    QDeadlineTimer deadline_;
    QString &error_;
};

bool parseFormat(const QByteArray &header, int &width, int &height)
{
    const auto fields = header.split(' ');
    if (fields.first() != "YUV4MPEG2")
        return false;
    bool yuv420p = false;
    for (const auto &field : fields) {
        if (field.startsWith('W'))
            width = field.sliced(1).toInt();
        else if (field.startsWith('H'))
            height = field.sliced(1).toInt();
        else if (field.startsWith('C'))
            yuv420p = field == "C420" || field == "C420jpeg" ||
                      field == "C420mpeg2" || field == "C420paldv";
    }
    return yuv420p && width > 0 && width <= MaxWidth && height > 0 && height <= MaxHeight;
}

void deliverFrames(QLocalSocket &socket, const std::atomic_bool &stopRequested, QDeadlineTimer deadline,
                   const HevcFileDecoder::FrameHandler &onFrame, HevcDecodeResult &result)
{
    PixelPipe pipe(socket, stopRequested, deadline, result.error);
    const auto header = pipe.readLine();
    if (header.isEmpty())
        return;
    int width = 0;
    int height = 0;
    if (!parseFormat(header, width, height)) {
        result.error = QStringLiteral("不支持的 FFmpeg 像素流格式：%1").arg(QString::fromLatin1(header));
        return;
    }
    const int chromaSize = ((width + 1) / 2) * ((height + 1) / 2);
    const int frameSize = width * height + 2 * chromaSize;
    while (!stopRequested) {
        const auto marker = pipe.readLine();
        if (marker.isEmpty())
            break; // End of file between frames, cancellation or a reported pipe error.
        if (marker != "FRAME" && !marker.startsWith("FRAME ")) {
            result.error = QStringLiteral("FFmpeg 像素流缺少帧标记");
            break;
        }
        auto pixels = pipe.readPixels(frameSize);
        if (pixels.isEmpty() || stopRequested)
            break;
        onFrame({++result.frames, width, height, std::move(pixels)});
        QCoreApplication::processEvents(); // Consume decoder diagnostics during continuous output.
    }
}

HevcDecodeResult decodeFile(const QString &file, const std::atomic_bool &stopRequested,
                            const HevcFileDecoder::FrameHandler &onFrame)
{
    HevcDecodeResult result;
    const QFileInfo input(file);
    if (!input.isFile()) {
        result.error = QStringLiteral("找不到本地视频文件：%1").arg(file);
        return result;
    }
    if (stopRequested) {
        result.stopped = true;
        return result;
    }

    // QProcess's Windows stdout reader can read ahead through the whole file. A local
    // socket with a finite read buffer backpressures FFmpeg while the consumer is busy.
    QLocalServer server;
    server.setSocketOptions(QLocalServer::UserAccessOption);
    if (!server.listen("rm27-hevc-" + QUuid::createUuid().toString(QUuid::WithoutBraces))) {
        result.error = QStringLiteral("无法打开本机像素管道：%1").arg(server.errorString());
        return result;
    }
#ifdef Q_OS_WIN
    const auto destination = server.fullServerName(); // FFmpeg file output to a Windows named pipe.
#else
    const auto destination = "unix:" + server.fullServerName();
#endif

    QByteArray diagnostics;
    QProcess decoder;
    const auto drainDiagnostics = [&] {
        diagnostics = (diagnostics + decoder.readAllStandardError().right(4096)).right(4096);
    };
    QObject::connect(&decoder, &QProcess::readyReadStandardError, drainDiagnostics);
    decoder.setStandardOutputFile(QProcess::nullDevice());
    decoder.start("ffmpeg", {"-hide_banner", "-nostdin", "-y", "-loglevel", "error",
        "-protocol_whitelist", "file", "-hwaccel", "none", "-c:v", "hevc", "-threads", "2",
        "-max_pixels", QString::number(MaxCodedPixels),
        "-err_detect", "explode", "-f", "hevc", "-i", input.absoluteFilePath(), "-map", "0:v:0",
        "-fps_mode", "passthrough", "-pix_fmt", "yuv420p", "-f", "yuv4mpegpipe",
        "-flush_packets", "1", destination}, QIODevice::ReadOnly);
    const QDeadlineTimer deadline(ShortClipTimeoutMs);
    if (!decoder.waitForStarted()) {
        result.error = QStringLiteral("无法启动 FFmpeg，请检查 PATH：%1").arg(decoder.errorString());
    } else {
        while (!stopRequested && !deadline.hasExpired() && !server.hasPendingConnections()) {
            server.waitForNewConnection(StopPollMs);
            if (decoder.state() == QProcess::NotRunning || decoder.waitForFinished(0))
                break;
        }
        if (auto *socket = server.nextPendingConnection()) {
            socket->setReadBufferSize(256 * 1024);
            try {
                deliverFrames(*socket, stopRequested, deadline, onFrame, result);
            } catch (const std::exception &e) {
                result.error = QStringLiteral("像素帧交付失败：%1").arg(QString::fromUtf8(e.what()));
            } catch (...) {
                result.error = QStringLiteral("像素帧交付失败");
            }
        }
        while (!stopRequested && result.error.isEmpty() && !deadline.hasExpired()
               && decoder.state() != QProcess::NotRunning)
            decoder.waitForFinished(StopPollMs);
        if (!stopRequested && deadline.hasExpired() && result.error.isEmpty())
            result.error = QStringLiteral("本地短片解码超时");
    }
    result.stopped = stopRequested.load();
    if (decoder.state() != QProcess::NotRunning) {
        decoder.kill();
        decoder.waitForFinished(-1);
    }
    drainDiagnostics();
    result.diagnostic = QString::fromUtf8(diagnostics.trimmed());
    if (result.error.isEmpty() && !result.stopped) {
        if (decoder.exitStatus() != QProcess::NormalExit || decoder.exitCode() != 0)
            result.error = QStringLiteral("FFmpeg 解码失败（退出码 %1）").arg(decoder.exitCode());
        else if (!result.frames)
            result.error = QStringLiteral("未解码出完整视频帧");
    }
    return result;
}

} // namespace

HevcFileDecoder::~HevcFileDecoder()
{
    requestStop();
    waitForFinished();
}

bool HevcFileDecoder::start(const QString &file, FrameHandler onFrame)
{
    if (worker_ || !onFrame)
        return false;
    stopRequested_ = false;
    result_ = {};
    worker_.reset(QThread::create([this, file, onFrame = std::move(onFrame)] {
        result_ = decodeFile(file, stopRequested_, onFrame);
    }));
    worker_->start();
    return true;
}

void HevcFileDecoder::requestStop()
{
    stopRequested_ = true;
}

HevcDecodeResult HevcFileDecoder::waitForFinished()
{
    if (worker_) {
        worker_->wait();
        worker_.reset();
    }
    return result_;
}

} // namespace rm27::video
