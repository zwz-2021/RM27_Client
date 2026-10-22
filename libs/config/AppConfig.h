#pragma once

#include "domain/RunMode.h"
#include <QString>
#include <optional>

namespace rm27::config {

struct AppConfig {
    domain::RunMode mode = domain::RunMode::Official;
};

struct ConfigResult {
    std::optional<AppConfig> config;
    QString error;
};

ConfigResult loadConfig(const QString &path);

} // namespace rm27::config

