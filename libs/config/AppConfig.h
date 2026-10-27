#pragma once

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

struct AppConfig {
    domain::RunMode mode = domain::RunMode::Official;
    WindowConfig window;
    SimulationConfig simulation;
    LoggingConfig logging;
};

struct ConfigResult {
    std::optional<AppConfig> config;
    QString error;
};

ConfigResult loadConfig(const QString &path);

} // namespace rm27::config
