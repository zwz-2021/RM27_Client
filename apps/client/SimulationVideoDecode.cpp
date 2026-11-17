#include "SimulationVideoDecode.h"
#include "transport/UdpVideoReceiver.h"

#include <QCryptographicHash>
#include <QJsonDocument>
#include <QJsonObject>

namespace rm27::client {

SimulationVideoDecode::SimulationVideoDecode(transport::UdpVideoReceiver &receiver, bool tracePixels)
{
    refresh_.setInterval(100);
    connect(&refresh_, &QTimer::timeout, this, [this] { emit statusChanged(statusText(decoder_.status())); });
    connect(&receiver, &transport::UdpVideoReceiver::statusChanged, this, [this, &receiver, tracePixels] {
        if (receiver.status().state != video::UdpVideoState::Bound) {
            stop();
            return;
        }
        if (refresh_.isActive())
            return;
        decoder_.start([this, tracePixels](video::DecodedVideoFrame frame) {
            if (!tracePixels || sample_.size() >= 32)
                return;
            const auto hash = QCryptographicHash::hash(frame.pixels, QCryptographicHash::Sha256).toHex();
            const QJsonObject data{{"index", frame.index}, {"width", frame.width}, {"height", frame.height},
                                   {"sha256", QString::fromLatin1(hash)}};
            sample_.append(QString::fromUtf8(QJsonDocument(data).toJson(QJsonDocument::Compact)));
        });
        refresh_.start();
        emit statusChanged(statusText(decoder_.status()));
    });
    connect(&receiver, &transport::UdpVideoReceiver::frameAssembled, this,
            [this](quint16, const QByteArray &bytes, const QString &address, quint16 port) {
        if (!refresh_.isActive())
            return;
        if (port_ != 0 && (port != port_ || address != address_)) {
            const auto state = decoder_.status();
            if (state.segmentActive || state.pendingFrames) {
                ++otherSourceFrames_;
                return;
            }
        }
        if (decoder_.submit(bytes)) {
            address_ = address;
            port_ = port;
        }
    });
}

QString SimulationVideoDecode::statusText(const video::HevcStreamStatus &state) const
{
    QString detail = state.segmentActive ? QStringLiteral("正在解码") : QStringLiteral("等待输入");
    detail += QStringLiteral(" · 已解码 %1 帧").arg(state.decodedFrames);
    if (state.width > 0)
        detail += QStringLiteral(" · %1×%2").arg(state.width).arg(state.height);
    detail += QStringLiteral(" · 排队 %1 帧 / %2 字节 · 输入丢弃 %3 帧")
                  .arg(state.pendingFrames).arg(state.pendingBytes).arg(state.droppedFrames);
    if (otherSourceFrames_)
        detail += QStringLiteral(" · 忽略其他发送端 %1 帧").arg(otherSourceFrames_);
    if (!state.error.isEmpty())
        detail += QStringLiteral("\n解码错误 · %1。请检查视频源和 FFmpeg，必要时停止并重新启动数据源。").arg(state.error);
    if (!state.diagnostic.isEmpty())
        detail += QStringLiteral("\nFFmpeg · ") + state.diagnostic.simplified().right(320);
    return QStringLiteral("本机模拟解码 · ") + detail;
}

void SimulationVideoDecode::stop()
{
    if (refresh_.isActive()) {
        refresh_.stop();
        const auto last = decoder_.stop();
        for (const auto &frame : sample_)
            emit logRecord(QStringLiteral("info"), QStringLiteral("video.decode_frame"), frame);
        emit logRecord(last.error.isEmpty() && last.diagnostic.isEmpty() ? QStringLiteral("info") : QStringLiteral("warning"),
                       QStringLiteral("video.decode_summary"), statusText(last));
        sample_.clear();
        address_.clear();
        port_ = 0;
        otherSourceFrames_ = 0;
    }
    emit statusChanged(QStringLiteral("本机模拟解码 · 已停止 · 已解码 0 帧"));
}

} // namespace rm27::client
