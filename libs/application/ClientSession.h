#pragma once

#include "IDataSource.h"
#include "domain/OperatorSeat.h"
#include <QElapsedTimer>
#include <QTimer>

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
    const domain::BasicState &basicState() const { return basicState_; }
    int robotId() const { return robotId_; }
    domain::OperatorSeat seat() const { return seat_; }
    const QString &actionFeedback() const { return actionFeedback_; }
    QString diagnostic() const { return diagnostic_; }
    QString sourceDescription() const { return sourceDescription_; }
    // Only the composition root configures identity, while the session is stopped.
    void configureIdentity(int robotId, const QString &sourceDescription,
                           domain::OperatorSeat seat = domain::OperatorSeat::Unspecified);

    void start();
    void stop();
    bool requestBusinessAction();

signals:
    void stateChanged();
    void snapshotChanged();
    void basicStateChanged();
    void diagnosticChanged();
    void identityChanged();
    void actionFeedbackChanged();

private:
    void clearSessionData();
    void acceptBasicMessage(const domain::BasicMessage &message, qint64 ageMs);
    void refreshFreshness();
    void setDiagnostic(const QString &detail);
    void setActionFeedback(const QString &detail);

    IDataSource &source_;
    domain::ConnectionState connectionState_ = domain::ConnectionState::Disconnected;
    QString connectionDetail_ = QStringLiteral("数据源尚未启动。");
    domain::ClientSnapshot snapshot_;
    bool hasSnapshot_ = false;
    bool active_ = false;
    quint64 startGeneration_ = 0;
    domain::BasicState basicState_;
    int robotId_ = 1;
    domain::OperatorSeat seat_ = domain::OperatorSeat::Unspecified;
    QString actionFeedback_;
    QString sourceDescription_;
    QString diagnostic_;
    QElapsedTimer receiveClock_;
    QTimer freshnessTimer_;
};

} // namespace rm27::application
