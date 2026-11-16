#include <QCommandLineParser>
#include <QCoreApplication>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QRegularExpression>
#include <cstdio>

namespace {

constexpr int MaxWidth = 1920;
constexpr int MaxHeight = 1080;
// HEVC may pad the coded picture to a full coding-tree row before cropping to 1080.
constexpr int MaxCodedPixels = MaxWidth * 1088;
constexpr int MaxReportLineBytes = 1024;
constexpr int ShortClipTimeoutMs = 120000;

void writeEvent(QFile &output, const QJsonObject &event)
{
    output.write(QJsonDocument(event).toJson(QJsonDocument::Compact) + '\n');
    output.flush();
}

// FFmpeg hashes each decoded rawvideo frame. Only short report lines cross the pipe.
class FrameReader {
public:
    FrameReader(QFile &output, int stopAfter) : output_(output), stopAfter_(stopAfter) {}

    void drain(QProcess &decoder)
    {
        while (decoder.canReadLine() && error.isEmpty() && !stopped) {
            const auto line = decoder.readLine(MaxReportLineBytes);
            if (!line.endsWith('\n')) {
                error = QStringLiteral("FFmpeg 帧校验报告的行过长");
                break;
            }
            readLine(QString::fromLatin1(line).trimmed());
        }
        if (decoder.bytesAvailable() >= MaxReportLineBytes && !stopped && error.isEmpty())
            error = QStringLiteral("FFmpeg 帧校验报告的行过长");
    }

    int frames = 0;
    bool stopped = false;
    QString error;

private:
    void readLine(const QString &line)
    {
        static const QString dimensions = QStringLiteral("#dimensions 0: ");
        if (line.startsWith(dimensions)) {
            const auto size = line.sliced(dimensions.size()).split('x');
            width_ = size.value(0).toInt();
            height_ = size.value(1).toInt();
            if (size.size() != 2 || width_ < 1 || width_ > MaxWidth || height_ < 1 || height_ > MaxHeight)
                error = QStringLiteral("不支持的解码输出尺寸：%1").arg(line);
            return;
        }
        if (line.startsWith('#'))
            return;

        // framehash v1 columns: stream, DTS, PTS, duration, raw packet size, digest.
        static const QRegularExpression frame(
            QStringLiteral(R"(^0,\s*-?\d+,\s*-?\d+,\s*\d+,\s*(\d+),\s*([0-9a-f]{64})$)"));
        const auto match = frame.match(line);
        const int chromaBytes = ((width_ + 1) / 2) * ((height_ + 1) / 2);
        const int yuvBytes = width_ * height_ + 2 * chromaBytes;
        if (!match.hasMatch() || !yuvBytes || match.captured(1).toInt() != yuvBytes) {
            error = QStringLiteral("FFmpeg 输出的帧校验报告与 YUV420p 尺寸不符：%1").arg(line);
            return;
        }
        writeEvent(output_, {{"event", "frame"}, {"index", ++frames}, {"width", width_},
                             {"height", height_}, {"sha256", match.captured(2)}});
        stopped = frames == stopAfter_;
    }

    QFile &output_;
    int stopAfter_;
    int width_ = 0;
    int height_ = 0;
};

bool decodeFile(const QString &file, int stopAfter, QFile &output)
{
    FrameReader reader(output, stopAfter);
    QByteArray diagnostics;
    QProcess decoder;
    const auto drainFrames = [&] {
        reader.drain(decoder);
        if ((reader.stopped || !reader.error.isEmpty()) && decoder.state() != QProcess::NotRunning)
            decoder.kill();
    };
    const auto drainDiagnostics = [&] {
        diagnostics = (diagnostics + decoder.readAllStandardError()).right(4096);
    };
    QObject::connect(&decoder, &QProcess::readyReadStandardOutput, drainFrames);
    QObject::connect(&decoder, &QProcess::readyReadStandardError, drainDiagnostics);

    const QFileInfo input(file);
    if (!input.isFile()) {
        reader.error = QStringLiteral("找不到本地视频文件：%1").arg(file);
    } else {
        decoder.start("ffmpeg", {"-hide_banner", "-nostdin", "-loglevel", "error", "-xerror",
            "-protocol_whitelist", "file", "-hwaccel", "none", "-c:v", "hevc", "-threads", "2",
            "-max_pixels", QString::number(MaxCodedPixels),
            "-err_detect", "explode", "-f", "hevc", "-i", input.absoluteFilePath(), "-map", "0:v:0",
            "-fps_mode", "passthrough", "-pix_fmt", "yuv420p", "-c:v", "rawvideo", "-f", "framehash",
            "-format_version", "1", "-hash", "sha256", "-flush_packets", "1", "pipe:1"});
        if (!decoder.waitForStarted()) {
            reader.error = QStringLiteral("无法启动 FFmpeg，请检查 PATH：%1").arg(decoder.errorString());
            if (decoder.state() != QProcess::NotRunning) {
                decoder.kill();
                decoder.waitForFinished(-1);
            }
        } else {
            if (!decoder.waitForFinished(ShortClipTimeoutMs) && decoder.state() != QProcess::NotRunning) {
                reader.error = QStringLiteral("本地短片解码超时");
                decoder.kill();
                decoder.waitForFinished(-1);
            }
            drainFrames();
            drainDiagnostics();
            if (!reader.stopped && reader.error.isEmpty()) {
                if (decoder.exitStatus() != QProcess::NormalExit || decoder.exitCode() != 0
                    || !diagnostics.trimmed().isEmpty())
                    reader.error = QStringLiteral("FFmpeg 解码失败（退出码 %1）").arg(decoder.exitCode());
                else if (decoder.bytesAvailable())
                    reader.error = QStringLiteral("FFmpeg 帧校验报告在行内中断");
                else if (!reader.frames)
                    reader.error = QStringLiteral("未解码出完整视频帧");
            }
        }
    }
    if (!reader.error.isEmpty() && !diagnostics.trimmed().isEmpty())
        reader.error += QStringLiteral("：") + QString::fromUtf8(diagnostics.trimmed());
    QString status = QStringLiteral("completed");
    if (!reader.error.isEmpty())
        status = QStringLiteral("error");
    else if (reader.stopped)
        status = QStringLiteral("stopped");
    writeEvent(output, {{"event", "summary"}, {"file", file}, {"status", status},
                        {"frames", reader.frames}, {"error", reader.error}});
    return reader.error.isEmpty();
}

} // namespace

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("逐帧核对本地 Annex B HEVC 短片的软件解码结果。"));
    parser.addHelpOption();
    const QCommandLineOption stopOption("stop-after", QStringLiteral("每个文件输出 N 帧后停止并回收解码器。"), "N");
    parser.addOption(stopOption);
    parser.addPositionalArgument("file", QStringLiteral("本地 Annex B HEVC 短片，可提供多个文件。"), "file...");
    parser.process(app);
    bool validLimit = false;
    const int stopAfter = parser.value(stopOption).toInt(&validLimit);
    const auto files = parser.positionalArguments();
    if (files.isEmpty() || (parser.isSet(stopOption) && (!validLimit || stopAfter < 1)))
        parser.showHelp(2);

    QFile output;
    if (!output.open(stdout, QIODevice::WriteOnly))
        return 1;
    bool passed = true;
    for (const auto &file : files) {
        if (!decodeFile(file, stopAfter, output))
            passed = false;
    }
    return passed ? 0 : 1;
}
