#pragma once

#include "IDataSource.h"

namespace rm27::application {

// 统一保存会话状态；不创建网络连接，也不暴露 QML 属性。
// 数据源由应用组合根持有，生命周期必须长于 ClientSession。
class ClientSession : public QObject {
    Q_OBJECT

public:
    explicit ClientSession(IDataSource &source, QObject *parent = nullptr);
    ~ClientSession() override;

    domain::ConnectionState connectionState() const { return connectionState_; }
    const QString &connectionDetail() const { return connectionDetail_; }
    const domain::ClientSnapshot &snapshot() const { return snapshot_; }
    bool hasSnapshot() const { return hasSnapshot_; }
    bool active() const { return active_; }

    void start();
    void stop();

signals:
    void stateChanged();
    void snapshotChanged();

private:
    void clearSnapshot();

    IDataSource &source_;
    domain::ConnectionState connectionState_ = domain::ConnectionState::Disconnected;
    QString connectionDetail_ = QStringLiteral("数据源尚未启动。");
    domain::ClientSnapshot snapshot_;
    bool hasSnapshot_ = false;
    bool active_ = false;
};

} // namespace rm27::application
