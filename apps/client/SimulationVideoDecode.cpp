#include "SimulationVideoDecode.h"
#include "transport/UdpVideoReceiver.h"

#include <QAbstractVideoBuffer>
#include <QCryptographicHash>
#include <QJsonDocument>
#include <QJsonObject>

namespace rm27::client {
namespace {

// The decoder already owns packed Y, U and V planes. Qt keeps them alive for
// as long as the render thread needs them, including across a GUI resize.
class SimulationPixelBuffer final : public QAbstractVideoBuffer {
public:
    explicit SimulationPixelBuffer(video::DecodedVideoFrame frame) : frame_(std::move(frame)) {}

    QVideoFrameFormat format() const override
    {
        return {{frame_.width, frame_.height}, QVideoFrameFormat::Format_YUV420P};
    }

    MapData map(QVideoFrame::MapMode mode) override
    {
        if (mode != QVideoFrame::ReadOnly)
            return {};
        const int luma = frame_.width * frame_.height;
        const int chromaWidth = (frame_.width + 1) / 2;
        const int chroma = chromaWidth * ((frame_.height + 1) / 2);
        auto *pixels = reinterpret_cast<uchar *>(frame_.pixels.data());
        return {3, {frame_.width, chromaWidth, chromaWidth},
                {pixels, pixels + luma, pixels + luma + chroma}, {luma, chroma, chroma}};
    }

private:
    video::DecodedVideoFrame frame_;
};

constexpr auto FrameTimeout = std::chrono::seconds(1);

} // namespace

SimulationVideoDecode::SimulationVideoDecode(transport::UdpVideoReceiver &receiver, bool traceVideo)
    : traceVideo_(traceVideo)
{
    refresh_.setInterval(100);
    connect(&refresh_, &QTimer::timeout, this, [this] {
        const auto state = decoder_.status();
        updateDisplay(state, false);
        emit statusChanged(statusText(state));
        refreshRates();
    });
    connect(&receiver, &transport::UdpVideoReceiver::statusChanged, this, [this, &receiver] {
        if (receiver.status().state != video::UdpVideoState::Bound) {
            stop();
            if (receiver.status().state == video::UdpVideoState::BindFailed)
                setDisplayState(QStringLiteral("视频端口绑定失败，请查看运行信息"));
            else if (receiver.status().state == video::UdpVideoState::ReadFailed)
                setDisplayState(QStringLiteral("视频接收失败，请查看运行信息"));
            return;
        }
        if (refresh_.isActive())
            return;
        decoder_.start([this](video::DecodedVideoFrame frame) {
            if (traceVideo_ && sample_.size() < 32) {
                const auto hash = QCryptographicHash::hash(frame.pixels, QCryptographicHash::Sha256).toHex();
                const QJsonObject data{{"index", frame.index}, {"width", frame.width}, {"height", frame.height},
                                       {"sha256", QString::fromLatin1(hash)}};
                sample_.append(QString::fromUtf8(QJsonDocument(data).toJson(QJsonDocument::Compact)));
            }
            queueFrame(std::move(frame));
        });
        setDisplayState(QStringLiteral("等待模拟画面"));
        refresh_.start();
        refreshRates();
        emit statusChanged(statusText(decoder_.status()));
    });
    connect(&receiver, &transport::UdpVideoReceiver::frameAssembled, this,
            [this](quint16, const QByteArray &bytes, const QString &address, quint16 port) {
        if (!refresh_.isActive())
            return;
        if (port_ != 0 && (port != port_ || address != address_)) {
            const auto state = decoder_.status();
            if (state.phase != video::HevcStreamPhase::Idle || state.pendingFrames) {
                ++otherSourceFrames_;
                return;
            }
        }
        if (decoder_.submit(bytes)) {
            lastInput_ = Clock::now();
            // Stop at the last accepted input. FFmpeg can return delayed pictures
            // during idle drain, after playback of this recording has stopped.
            if (traceVideo_)
                timingAtLastInput_ = displayTiming_;
            address_ = address;
            port_ = port;
        }
    });
}

void SimulationVideoDecode::setVideoSink(QVideoSink *sink)
{
    if (sink_ == sink)
        return;
    if (sink_)
        sink_->setVideoFrame({});
    previousPresentation_.reset();
    sink_ = sink;
    deliverCurrentFrame();
    emit videoSinkChanged();
}

void SimulationVideoDecode::queueFrame(video::DecodedVideoFrame frame)
{
    QMutexLocker lock(&frameMutex_);
    // Count every worker output before the GUI's latest-frame slot coalesces it.
    // Idle drain also produces real pixels; timestamp those at delivery, not input.
    const auto now = Clock::now();
    decodeRate_.record(std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()).count());
    pendingFrame_ = std::move(frame);
    pendingSince_ = now;
    if (!deliveryScheduled_) {
        deliveryScheduled_ = true;
        QMetaObject::invokeMethod(this, &SimulationVideoDecode::presentLatest, Qt::QueuedConnection);
    }
}

void SimulationVideoDecode::refreshRates()
{
    quint64 count;
    qint64 nowMs;
    {
        QMutexLocker lock(&frameMutex_);
        nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now().time_since_epoch()).count();
        count = decodeRate_.countAt(nowMs);
    }
    emit decodeRateChanged(QStringLiteral("最近 1 秒解码输出：%1 帧/秒").arg(count));
    emit presentationRateChanged(QStringLiteral("最近 1 秒控件交付：%1 帧/秒").arg(presentationRate_.countAt(nowMs)));
}

void SimulationVideoDecode::deliverCurrentFrame()
{
    if (!sink_)
        return;
    const auto frame = currentFrame_;
    // Count the first actual delivery, including a first sink attached after
    // decoding. Reattaching an already delivered frame and clearing a sink do
    // not count. Set these before notifying the sink: its synchronous callback
    // may detach it (delivery still counts) or stop/reopen (stop clears it).
    if (!currentFrameDelivered_ && frame.isValid() && refresh_.isActive()) {
        currentFrameDelivered_ = true;
        const auto nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now().time_since_epoch()).count();
        presentationRate_.record(nowMs);
    }
    sink_->setVideoFrame(frame);
}

void SimulationVideoDecode::presentLatest()
{
    std::optional<video::DecodedVideoFrame> frame;
    {
        QMutexLocker lock(&frameMutex_);
        deliveryScheduled_ = false;
        frame.swap(pendingFrame_);
        if (!frame)
            return;
        lastOutput_ = pendingSince_;
    }
    currentFrame_ = QVideoFrame(std::make_unique<SimulationPixelBuffer>(std::move(*frame)));
    currentFrameDelivered_ = false;
    deliverCurrentFrame();
    if (sink_) {
        if (traceVideo_) {
            const auto presented = Clock::now();
            if (previousPresentation_) {
                const auto gap = presented - *previousPresentation_;
                ++displayTiming_.intervals;
                if (gap > std::chrono::milliseconds(100))
                    ++displayTiming_.over100ms;
                displayTiming_.maxGap = qMax(displayTiming_.maxGap, gap);
            }
            previousPresentation_ = presented;
        }
    }
    updateDisplay(decoder_.status(), true);
}

void SimulationVideoDecode::updateDisplay(const video::HevcStreamStatus &state, bool newFrame)
{
    if (!state.error.isEmpty()) {
        const bool hasFrame = currentFrame_.isValid();
        setDisplayState(hasFrame ? QStringLiteral("画面已过期 · 解码失败，请查看运行信息")
                                 : QStringLiteral("解码失败，请查看运行信息"), hasFrame);
    } else if (state.phase == video::HevcStreamPhase::WaitingForPicture) {
        const bool hasFrame = currentFrame_.isValid();
        setDisplayState(hasFrame ? QStringLiteral("画面已过期 · 等待可解码画面")
                                 : QStringLiteral("等待可解码画面"), hasFrame);
    } else if (currentFrame_.isValid()) {
        const auto now = Clock::now();
        // Draining a quiet recording can deliver delayed pixels. New input alone
        // must also never relabel a stale picture before a new frame arrives.
        const bool expired = now - lastInput_ >= FrameTimeout || now - lastOutput_ >= FrameTimeout
                             || (stale_ && !newFrame);
        setDisplayState(expired ? QStringLiteral("画面已过期") : QStringLiteral("正在播放"), expired);
    }
}

void SimulationVideoDecode::setDisplayState(const QString &text, bool stale)
{
    if (displayStatus_ == text && stale_ == stale)
        return;
    displayStatus_ = text;
    stale_ = stale;
    emit displayStateChanged();
}

QString SimulationVideoDecode::statusText(const video::HevcStreamStatus &state) const
{
    QString detail;
    switch (state.phase) {
    case video::HevcStreamPhase::Idle: detail = QStringLiteral("等待输入"); break;
    case video::HevcStreamPhase::WaitingForPicture:
        detail = QStringLiteral("等待可解码画面（参数集和关键帧）");
        break;
    case video::HevcStreamPhase::Decoding: detail = QStringLiteral("正在解码"); break;
    }
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
        detail += QStringLiteral("\nFFmpeg 最近诊断 · ") + state.diagnostic.simplified().right(320);
    return QStringLiteral("本机模拟解码 · ") + detail;
}

void SimulationVideoDecode::stop()
{
    if (refresh_.isActive()) {
        refresh_.stop();
        const auto last = decoder_.stop();
        // No more callbacks after join. A wakeup already on the GUI queue can
        // now only take an empty slot or a frame produced by the next session.
        {
            QMutexLocker lock(&frameMutex_);
            pendingFrame_.reset();
            decodeRate_.clear();
        }
        currentFrame_ = {};
        currentFrameDelivered_ = false;
        presentationRate_.clear();
        if (sink_)
            sink_->setVideoFrame({});
        for (const auto &frame : sample_)
            emit logRecord(QStringLiteral("info"), QStringLiteral("video.decode_frame"), frame);
        if (traceVideo_) {
            const auto &timing = timingAtLastInput_;
            const QJsonObject data{{"intervals", timing.intervals}, {"over100ms", timing.over100ms},
                {"maxGapMs", std::chrono::duration<double, std::milli>(timing.maxGap).count()}};
            emit logRecord(QStringLiteral("info"), QStringLiteral("video.display_timing"),
                           QString::fromUtf8(QJsonDocument(data).toJson(QJsonDocument::Compact)));
            previousPresentation_.reset();
            displayTiming_ = {};
            timingAtLastInput_ = {};
        }
        emit logRecord(last.error.isEmpty() && last.diagnostic.isEmpty() ? QStringLiteral("info") : QStringLiteral("warning"),
                       QStringLiteral("video.decode_summary"), statusText(last));
        sample_.clear();
        address_.clear();
        port_ = 0;
        otherSourceFrames_ = 0;
    }
    setDisplayState(QStringLiteral("已停止"));
    emit decodeRateChanged(QStringLiteral("最近 1 秒解码输出：—"));
    emit presentationRateChanged(QStringLiteral("最近 1 秒控件交付：—"));
    emit statusChanged(QStringLiteral("本机模拟解码 · 已停止 · 已解码 0 帧"));
}

} // namespace rm27::client
