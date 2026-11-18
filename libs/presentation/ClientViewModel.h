#pragma once

#include "application/ClientSession.h"
#include "domain/RunMode.h"
#include "video/UdpVideoStatus.h"

#include <QObject>
#include <QString>
#include <QTimer>
#include <QVariantMap>
#include <QVariantList>
#include <functional>
#include <optional>

namespace rm27::presentation {

// 只把应用状态投影给 QML；不解析配置文件或协议，也不创建数据源。
class ClientViewModel : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString modeText READ modeText CONSTANT)
    Q_PROPERTY(QString connectionText READ connectionText NOTIFY stateChanged)
    Q_PROPERTY(QString connectionDetail READ connectionDetail NOTIFY stateChanged)
    Q_PROPERTY(bool active READ active NOTIFY stateChanged)
    Q_PROPERTY(bool canStart READ canStart NOTIFY stateChanged)
    Q_PROPERTY(bool hasSnapshot READ hasSnapshot NOTIFY snapshotChanged)
    Q_PROPERTY(QString sequenceText READ sequenceText NOTIFY snapshotChanged)
    Q_PROPERTY(QString elapsedText READ elapsedText NOTIFY snapshotChanged)
    Q_PROPERTY(QString startupError READ startupError CONSTANT)
    Q_PROPERTY(QString logPath READ logPath CONSTANT)
    Q_PROPERTY(bool preview READ preview CONSTANT)
    Q_PROPERTY(QString sourceText READ sourceText NOTIFY identityChanged)
    Q_PROPERTY(QString seatText READ seatText NOTIFY identityChanged)
    Q_PROPERTY(bool infantrySeat READ infantrySeat NOTIFY identityChanged)
    Q_PROPERTY(int configuredRobotId READ configuredRobotId NOTIFY identityChanged)
    Q_PROPERTY(QVariantList receiverChoices READ receiverChoices CONSTANT)
    Q_PROPERTY(QString personalConfigPath READ personalConfigPath NOTIFY personalConfigPathChanged)
    Q_PROPERTY(QString configFeedback READ configFeedback NOTIFY configFeedbackChanged)
    Q_PROPERTY(QString actionFeedback READ actionFeedback NOTIFY actionFeedbackChanged)
    Q_PROPERTY(QString diagnosticText READ diagnosticText NOTIFY diagnosticChanged)
    Q_PROPERTY(QString udpBindingText READ udpBindingText NOTIFY udpChanged)
    Q_PROPERTY(QString udpCountersText READ udpCountersText NOTIFY udpChanged)
    Q_PROPERTY(QString udpPacketAgeText READ udpPacketAgeText NOTIFY udpPacketAgeChanged)
    Q_PROPERTY(QString udpHeaderText READ udpHeaderText NOTIFY udpChanged)
    Q_PROPERTY(QString udpAssemblyText READ udpAssemblyText NOTIFY udpChanged)
    Q_PROPERTY(QString udpLastFrameText READ udpLastFrameText NOTIFY udpChanged)
    Q_PROPERTY(QString videoDecodeText READ videoDecodeText NOTIFY videoDecodeChanged)
    Q_PROPERTY(QString healthText READ healthText NOTIFY basicStateChanged)
    Q_PROPERTY(QString dynamicStatusText READ dynamicStatusText NOTIFY basicStateChanged)
    Q_PROPERTY(QString dynamicSummary READ dynamicSummary NOTIFY basicStateChanged)
    Q_PROPERTY(QString robotIdentityText READ robotIdentityText NOTIFY basicStateChanged)
    Q_PROPERTY(QString staticSummary READ staticSummary NOTIFY basicStateChanged)
    Q_PROPERTY(QString gameText READ gameText NOTIFY basicStateChanged)
    Q_PROPERTY(QString gameSummary READ gameSummary NOTIFY basicStateChanged)
    Q_PROPERTY(QString economyText READ economyText NOTIFY basicStateChanged)
    Q_PROPERTY(QString logisticsSummary READ logisticsSummary NOTIFY basicStateChanged)
    Q_PROPERTY(QString unitsSummary READ unitsSummary NOTIFY basicStateChanged)
    Q_PROPERTY(QVariantList topicStates READ topicStates NOTIFY basicStateChanged)

public:
    ClientViewModel(application::ClientSession &session,
                    std::optional<domain::RunMode> mode,
                    QString startupError, QString logPath, QObject *parent = nullptr);

    QString modeText() const;
    QString connectionText() const;
    QString connectionDetail() const;
    bool active() const;
    bool canStart() const;
    bool hasSnapshot() const;
    QString sequenceText() const;
    QString elapsedText() const;
    QString startupError() const;
    QString logPath() const;
    bool preview() const;
    QString sourceText() const;
    QString seatText() const;
    bool infantrySeat() const;
    int configuredRobotId() const { return session_.robotId(); }
    QVariantList receiverChoices() const;
    QString personalConfigPath() const { return personalConfigPath_; }
    QString configFeedback() const { return configFeedback_; }
    void setPersonalConfigEditor(QString path, std::function<QString(int)> save);
    QString actionFeedback() const;
    QString diagnosticText() const;
    void setUdpStatus(const video::UdpVideoStatus &status);
    QString udpBindingText() const;
    QString udpCountersText() const;
    QString udpPacketAgeText() const;
    QString udpHeaderText() const;
    QString udpAssemblyText() const;
    QString udpLastFrameText() const;
    QString videoDecodeText() const { return videoDecodeText_; }
    void setVideoDecodeText(const QString &text);
    QString healthText() const;
    QString dynamicStatusText() const;
    QString dynamicSummary() const;
    QString robotIdentityText() const;
    QString staticSummary() const;
    QString gameText() const;
    QString gameSummary() const;
    QString economyText() const;
    QString logisticsSummary() const;
    QString unitsSummary() const;
    QVariantList topicStates() const;

    // Read-only evidence from the same projection displayed by QML.
    Q_INVOKABLE QVariantMap basicEvidence() const;

    Q_INVOKABLE void start();
    Q_INVOKABLE void stop();
    Q_INVOKABLE void requestBusinessAction();
    Q_INVOKABLE void saveInfantryConfig(int robotId);

signals:
    void stateChanged();
    void snapshotChanged();
    void basicStateChanged();
    void diagnosticChanged();
    void udpChanged();
    void udpPacketAgeChanged();
    void videoDecodeChanged();
    void identityChanged();
    void actionFeedbackChanged();
    void personalConfigPathChanged();
    void configFeedbackChanged();

private:
    application::ClientSession &session_;
    std::optional<domain::RunMode> mode_;
    QString startupError_;
    QString logPath_;
    QString personalConfigPath_;
    std::function<QString(int)> saveConfig_;
    QString configFeedback_;
    video::UdpVideoStatus udpStatus_;
    QTimer udpPacketAgeRefresh_;
    QString videoDecodeText_;
};

} // namespace rm27::presentation
