#pragma once

#include "application/IDataSource.h"

#include <QElapsedTimer>
#include <QTimer>
#include <memory>

namespace rm27::transport {

// A six-topic MQTT 3.1.1 receiver. The Paho callbacks never access Qt objects;
// a bounded mailbox is drained on the object's thread. Static identity changes
// are ordered barriers, never coalesced away. Each connection attempt owns a new
// callback context, which is retired before destruction, preventing old writes.
class MqttDataSource final : public application::IDataSource {
    Q_OBJECT
public:
    MqttDataSource(QString host, int port, int robotId, int connectTimeoutMs,
                   QObject *parent = nullptr);
    ~MqttDataSource() override;
    void setRobotIdWhileStopped(int robotId);
    void start() override;
    void stop() override;

private:
    struct Context;
    void beginAttempt();
    void connectAddress(const QString &address);
    void drain();
    void subscribe();
    void fail(const QString &detail);
    void releaseAttempt();

    QString host_;
    int port_;
    int robotId_;
    int timeoutMs_;
    QTimer poll_;
    QTimer retryTimer_;
    int nextRetryMs_ = 0;
    QElapsedTimer phaseClock_;
    std::unique_ptr<Context> context_;
    void *client_ = nullptr;
    int lookupId_ = -1;
    quint64 generation_ = 0;
    bool active_ = false;
    bool subscribing_ = false;
    bool ready_ = false;
};

} // namespace rm27::transport
