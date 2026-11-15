#pragma once

#include "domain/ClientSnapshot.h"
#include "domain/BasicState.h"
#include "domain/ConnectionState.h"

#include <QMetaType>
#include <QObject>
#include <QString>

Q_DECLARE_METATYPE(rm27::domain::ClientSnapshot)
Q_DECLARE_METATYPE(rm27::domain::ConnectionState)
Q_DECLARE_METATYPE(rm27::domain::BasicMessage)

namespace rm27::application {

// 当前接口在主线程调用。以后网络 worker 应通过信号把数据送回此边界。
// stop() 必须停止产生数据；start()/stop() 均应允许重复调用。
// 异步适配器须取消或隔离旧会话回调，确保再次 start() 后不会混入旧快照。
class IDataSource : public QObject {
    Q_OBJECT

public:
    explicit IDataSource(QObject *parent = nullptr) : QObject(parent) {}
    ~IDataSource() override = default;

    virtual void start() = 0;
    virtual void stop() = 0;

signals:
    void connectionChanged(rm27::domain::ConnectionState state, const QString &detail);
    void snapshotReceived(const rm27::domain::ClientSnapshot &snapshot);
    // Age is measured from transport reception on a monotonic clock, including
    // time spent waiting for SUBACK or the Qt event loop. Not server time.
    void basicMessageReceived(const rm27::domain::BasicMessage &message, qint64 ageMs = 0);
    void diagnosticReceived(const QString &detail);
};

} // namespace rm27::application
