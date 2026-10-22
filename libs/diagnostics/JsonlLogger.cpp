#include "JsonlLogger.h"

#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>

namespace rm27::diagnostics {

bool JsonlLogger::open(const QString &path)
{
    file_.setFileName(path);
    if (!QDir().mkpath(QFileInfo(path).absolutePath())) {
        error_ = QStringLiteral("无法创建日志目录：%1").arg(QFileInfo(path).absolutePath());
        return false;
    }
    if (!file_.open(QIODevice::WriteOnly | QIODevice::Append)) {
        error_ = QStringLiteral("无法打开日志 %1：%2").arg(path, file_.errorString());
        return false;
    }
    error_.clear();
    return true;
}

bool JsonlLogger::write(const QString &level, const QString &event, const QString &detail)
{
    const QJsonObject record{
        {"timestamp", QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs)},
        {"level", level}, {"event", event}, {"detail", detail}
    };
    const QByteArray line = QJsonDocument(record).toJson(QJsonDocument::Compact) + '\n';
    if (!file_.isOpen() || file_.write(line) != line.size() || !file_.flush()) {
        error_ = QStringLiteral("写入日志失败 %1：%2").arg(file_.fileName(), file_.errorString());
        return false;
    }
    return true;
}

QString JsonlLogger::errorString() const
{
    return error_;
}

} // namespace rm27::diagnostics

