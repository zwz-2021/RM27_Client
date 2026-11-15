#pragma once

#include "video/UdpVideoStatus.h"
#include <QObject>
#include <QTimer>

class QUdpSocket;

namespace rm27::transport {

class UdpVideoReceiver final : public QObject {
    Q_OBJECT
public:
    explicit UdpVideoReceiver(QObject *parent = nullptr);
    bool start(const QString &bindAddress, quint16 port);
    void stop();
    const video::UdpVideoStatus &status() const { return status_; }

signals:
    void statusChanged();

private:
    void drain();
    void closeSocket();
    void fail(video::UdpVideoState state, QString detail);

    QUdpSocket *socket_;
    QTimer continuation_;
    QTimer notification_;
    video::UdpVideoStatus status_;
};

} // namespace rm27::transport
