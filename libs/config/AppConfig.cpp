#include "AppConfig.h"

#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>

namespace rm27::config {

ConfigResult loadConfig(const QString &path)
{
    const QString source = path.startsWith(":/") ? path : QFileInfo(path).absoluteFilePath();
    const auto failure = [&source](const QString &reason) -> ConfigResult {
        return {std::nullopt, QStringLiteral("%1\n%2").arg(source, reason)};
    };

    QFile file(source);
    if (!file.open(QIODevice::ReadOnly)) {
        return failure(QStringLiteral("无法读取配置：%1").arg(file.errorString()));
    }
    const QByteArray contents = file.readAll();
    if (file.error() != QFileDevice::NoError) {
        return failure(QStringLiteral("读取配置失败：%1").arg(file.errorString()));
    }

    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(contents, &parseError);
    if (parseError.error != QJsonParseError::NoError) {
        return failure(QStringLiteral("JSON 字节偏移 %1：%2")
                           .arg(parseError.offset).arg(parseError.errorString()));
    }
    if (!document.isObject()) {
        return failure(QStringLiteral("配置根节点必须是 JSON 对象。"));
    }

    const QJsonObject object = document.object();
    for (auto it = object.constBegin(); it != object.constEnd(); ++it) {
        if (it.key() != QStringLiteral("mode")) {
            return failure(QStringLiteral("未知配置字段：%1").arg(it.key()));
        }
    }
    if (!object.value("mode").isString()) {
        return failure(QStringLiteral("字段 mode 必须是字符串：official 或 simulation。"));
    }
    const auto mode = domain::parseRunMode(object.value("mode").toString().toStdString());
    if (!mode) {
        return failure(QStringLiteral("字段 mode 仅支持 official 或 simulation；回放尚未实现。"));
    }
    return {AppConfig{*mode}, {}};
}

} // namespace rm27::config

