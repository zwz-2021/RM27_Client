#include "AppConfig.h"

#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QStringList>

#include <cmath>

namespace rm27::config {
namespace {

QString checkKeys(const QJsonObject &object, const QStringList &allowed,
                  const QString &prefix = {})
{
    for (auto it = object.constBegin(); it != object.constEnd(); ++it) {
        if (!allowed.contains(it.key())) {
            return QStringLiteral("未知配置字段：%1%2").arg(prefix, it.key());
        }
    }
    return {};
}

QString readSection(const QJsonObject &root, const QString &name,
                    const QStringList &allowed, QJsonObject &section)
{
    if (!root.contains(name)) {
        return {};
    }
    if (!root.value(name).isObject()) {
        return QStringLiteral("字段 %1 必须是 JSON 对象。").arg(name);
    }
    section = root.value(name).toObject();
    return checkKeys(section, allowed, name + '.');
}

QString readInteger(const QJsonObject &object, const QString &key, const QString &path,
                    int minimum, int maximum, int &destination)
{
    if (!object.contains(key)) {
        return {};
    }
    const QJsonValue value = object.value(key);
    const double number = value.toDouble();
    if (!value.isDouble() || !std::isfinite(number) || std::floor(number) != number
        || number < minimum || number > maximum) {
        return QStringLiteral("字段 %1 必须是 %2 到 %3 之间的整数。")
            .arg(path).arg(minimum).arg(maximum);
    }
    destination = static_cast<int>(number);
    return {};
}

} // namespace

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
    QString error = checkKeys(object, {"mode", "window", "simulation", "logging"});
    if (!error.isEmpty()) {
        return failure(error);
    }
    if (!object.value("mode").isString()) {
        return failure(QStringLiteral("字段 mode 必须是字符串：official 或 simulation。"));
    }
    const auto mode = domain::parseRunMode(object.value("mode").toString().toStdString());
    if (!mode) {
        return failure(QStringLiteral("字段 mode 仅支持 official 或 simulation；回放尚未实现。"));
    }
    AppConfig config;
    config.mode = *mode;

    QJsonObject window;
    error = readSection(object, QStringLiteral("window"), {"title", "width", "height"}, window);
    if (!error.isEmpty()) {
        return failure(error);
    }
    if (window.contains("title")) {
        const auto title = window.value("title");
        if (!title.isString() || title.toString().trimmed().isEmpty()) {
            return failure(QStringLiteral("字段 window.title 必须是非空字符串。"));
        }
        config.window.title = title.toString().trimmed();
    }
    error = readInteger(window, QStringLiteral("width"), QStringLiteral("window.width"),
                        640, 7680, config.window.width);
    if (!error.isEmpty()) {
        return failure(error);
    }
    error = readInteger(window, QStringLiteral("height"), QStringLiteral("window.height"),
                        480, 4320, config.window.height);
    if (!error.isEmpty()) {
        return failure(error);
    }

    QJsonObject simulation;
    error = readSection(object, QStringLiteral("simulation"), {"intervalMs"}, simulation);
    if (!error.isEmpty()) {
        return failure(error);
    }
    error = readInteger(simulation, QStringLiteral("intervalMs"),
                        QStringLiteral("simulation.intervalMs"), 100, 60000,
                        config.simulation.intervalMs);
    if (!error.isEmpty()) {
        return failure(error);
    }

    QJsonObject logging;
    error = readSection(object, QStringLiteral("logging"), {"directory"}, logging);
    if (!error.isEmpty()) {
        return failure(error);
    }
    if (logging.contains("directory")) {
        if (!logging.value("directory").isString()) {
            return failure(QStringLiteral("字段 logging.directory 必须是字符串。"));
        }
        config.logging.directory = logging.value("directory").toString();
    }

    return {config, {}};
}

} // namespace rm27::config
