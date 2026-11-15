#pragma once

#include "domain/OperatorSeat.h"
#include "domain/RunMode.h"
#include <QString>
#include <optional>

namespace rm27::config {

struct WindowConfig {
    QString title = QStringLiteral("RM27 Client");
    int width = 1280;
    int height = 800;
};

struct SimulationConfig {
    int intervalMs = 1000;
};

struct LoggingConfig {
    // 空目录由应用层解析为系统提供的可写应用数据目录。
    QString directory;
};

struct MqttConfig {
    QString host = QStringLiteral("192.168.12.1");
    int port = 3333;
    int robotId = 1;
    int connectTimeoutMs = 5000;
};

struct AppConfig {
    domain::RunMode mode = domain::RunMode::Official;
    WindowConfig window;
    SimulationConfig simulation;
    LoggingConfig logging;
    MqttConfig mqtt;
    domain::OperatorSeat seat = domain::OperatorSeat::Unspecified;
};

struct ConfigResult {
    std::optional<AppConfig> config;
    QString error;
};

ConfigResult loadConfig(const QString &path);

} // namespace rm27::config
