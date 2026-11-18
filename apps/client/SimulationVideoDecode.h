#pragma once

#include "video/HevcStreamDecoder.h"
#include <QObject>
#include <QPointer>
#include <QStringList>
#include <QTimer>
#include <QVideoFrame>
#include <QVideoSink>
#include <chrono>
#include <optional>

namespace rm27::transport { class UdpVideoReceiver; }

namespace rm27::client {

// One local simulator is the source of each continuous HEVC segment.
class SimulationVideoDecode final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVideoSink *videoSink READ videoSink WRITE setVideoSink NOTIFY videoSinkChanged)
    Q_PROPERTY(QString statusText READ displayStatus NOTIFY displayStateChanged)
    Q_PROPERTY(bool stale READ stale NOTIFY displayStateChanged)
public:
    SimulationVideoDecode(transport::UdpVideoReceiver &receiver, bool tracePixels);
    QVideoSink *videoSink() const { return sink_.data(); }
    void setVideoSink(QVideoSink *sink);
    QString displayStatus() const { return displayStatus_; }
    bool stale() const { return stale_; }

signals:
    void videoSinkChanged();
    void displayStateChanged();
    void statusChanged(const QString &text);
    void logRecord(const QString &level, const QString &event, const QString &detail);

private:
    using Clock = std::chrono::steady_clock;
    void queueFrame(video::DecodedVideoFrame frame);
    void presentLatest();
    void updateDisplay(const video::HevcStreamStatus &state, bool newFrame);
    void setDisplayState(const QString &text, bool stale = false);
    QString statusText(const video::HevcStreamStatus &state) const;
    void stop();

    QTimer refresh_;
    QString address_;
    quint16 port_ = 0;
    quint64 otherSourceFrames_ = 0;
    QPointer<QVideoSink> sink_;
    QVideoFrame currentFrame_;
    Clock::time_point lastInput_, lastOutput_;
    QString displayStatus_ = QStringLiteral("已停止");
    bool stale_ = false;
    // One replaceable worker output and at most one outstanding GUI wakeup.
    QMutex frameMutex_;
    std::optional<video::DecodedVideoFrame> pendingFrame_;
    Clock::time_point pendingSince_;
    bool deliveryScheduled_ = false;
    // Only the worker fills the sample. The owner reads it after joining the worker.
    QStringList sample_;
    video::HevcStreamDecoder decoder_;
};

} // namespace rm27::client
