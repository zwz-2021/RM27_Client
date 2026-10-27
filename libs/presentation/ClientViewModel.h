#pragma once

#include "application/ClientSession.h"
#include "domain/RunMode.h"

#include <QObject>
#include <QString>
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

    Q_INVOKABLE void start();
    Q_INVOKABLE void stop();

signals:
    void stateChanged();
    void snapshotChanged();

private:
    application::ClientSession &session_;
    std::optional<domain::RunMode> mode_;
    QString startupError_;
    QString logPath_;
};

} // namespace rm27::presentation
