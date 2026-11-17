#pragma once

#include "video/HevcStreamDecoder.h"
#include <QObject>
#include <QStringList>
#include <QTimer>

namespace rm27::transport { class UdpVideoReceiver; }

namespace rm27::client {

// One local simulator is the source of each continuous HEVC segment.
class SimulationVideoDecode final : public QObject {
    Q_OBJECT
public:
    SimulationVideoDecode(transport::UdpVideoReceiver &receiver, bool tracePixels);

signals:
    void statusChanged(const QString &text);
    void logRecord(const QString &level, const QString &event, const QString &detail);

private:
    QString statusText(const video::HevcStreamStatus &state) const;
    void stop();

    QTimer refresh_;
    QString address_;
    quint16 port_ = 0;
    quint64 otherSourceFrames_ = 0;
    // Only the worker fills the sample. The owner reads it after joining the worker.
    QStringList sample_;
    video::HevcStreamDecoder decoder_;
};

} // namespace rm27::client
