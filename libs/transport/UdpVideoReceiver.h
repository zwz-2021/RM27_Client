#pragma once

#include "video/UdpVideoStatus.h"
#include "video/VideoFrameAssembler.h"
#include <QElapsedTimer>
#include <QObject>
#include <QTimer>

class QUdpSocket;

namespace rm27::transport {

class UdpVideoReceiver final : public QObject {
    Q_OBJECT
public:
    explicit UdpVideoReceiver(QObject *parent = nullptr);
    bool start(const QString &bindAddress, quint16 port, bool assembleLocalSimulation = false);
    void stop();
    const video::UdpVideoStatus &status() const { return status_; }

signals:
    void statusChanged();
    void frameAssembled(quint16 frameId, const QByteArray &bytes);

private:
    void drain();
    void scheduleExpiry();
    void closeSocket();
    void fail(video::UdpVideoState state, QString detail);

    QUdpSocket *socket_;
    QTimer continuation_;
    QTimer notification_;
    QTimer expiry_;
    QElapsedTimer sessionClock_;
    bool assembleLocalSimulation_ = false;
    video::VideoFrameAssembler assembler_;
    video::UdpVideoStatus status_;
};

} // namespace rm27::transport
