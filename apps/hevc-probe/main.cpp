#include "video/HevcFileDecoder.h"
#include <QCommandLineParser>
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QJsonDocument>
#include <QJsonObject>
#include <QThread>
#include <cstdio>
#include <optional>
#include <utility>

namespace {

using rm27::video::DecodedVideoFrame;
using rm27::video::HevcFileDecoder;

void writeEvent(const QJsonObject &event)
{
    const QByteArray line = QJsonDocument(event).toJson(QJsonDocument::Compact) + '\n';
    std::fwrite(line.constData(), 1, size_t(line.size()), stdout);
    std::fflush(stdout);
}

QJsonObject describeFrame(const DecodedVideoFrame &frame)
{
    const auto digest = QCryptographicHash::hash(frame.pixels, QCryptographicHash::Sha256);
    return {{"index", frame.index}, {"width", frame.width}, {"height", frame.height},
            {"sha256", QString::fromLatin1(digest.toHex())}};
}

bool decodeFile(HevcFileDecoder &decoder, const QString &file, int stopAfter,
                std::optional<DecodedVideoFrame> &previousFirst)
{
    std::optional<DecodedVideoFrame> first;
    bool background = true;
    const bool started = decoder.start(file, [&](DecodedVideoFrame frame) {
        background = background && !QThread::isMainThread();
        auto event = describeFrame(frame);
        event.insert("event", "frame");
        writeEvent(event);
        if (frame.index == stopAfter)
            decoder.requestStop();
        if (!first)
            first = std::move(frame);
    });
    if (!started) {
        writeEvent({{"event", "summary"}, {"file", file}, {"status", "error"}, {"frames", 0},
                    {"error", QStringLiteral("无法开始后台解码")}, {"diagnostic", ""}});
        return false;
    }

    const auto result = decoder.waitForFinished();
    QString status = QStringLiteral("completed");
    if (!result.error.isEmpty())
        status = QStringLiteral("error");
    else if (result.stopped)
        status = QStringLiteral("stopped");
    else if (!result.diagnostic.isEmpty())
        status = QStringLiteral("completed_with_errors");

    QJsonObject summary{{"event", "summary"}, {"file", file}, {"status", status},
                        {"frames", result.frames}, {"error", result.error}, {"diagnostic", result.diagnostic}};
    // Hash the retained pixels again on the caller thread, after the worker and FFmpeg exit.
    if (first) {
        summary.insert("frameCallbacksOffMainThread", background);
        summary.insert("firstFrameAfterClose", describeFrame(*first));
    }
    if (previousFirst)
        summary.insert("previousFirstFrameAfterClose", describeFrame(*previousFirst));
    writeEvent(summary);
    previousFirst = std::move(first);
    return result.error.isEmpty() && result.diagnostic.isEmpty();
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

    HevcFileDecoder decoder;
    std::optional<DecodedVideoFrame> previousFirst;
    bool passed = true;
    for (const auto &file : files) {
        if (!decodeFile(decoder, file, stopAfter, previousFirst))
            passed = false;
    }
    return passed ? 0 : 1;
}
