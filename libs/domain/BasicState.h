#pragma once

#include "BasicData.h"

namespace rm27::domain {

// Local receive time is diagnostic metadata, not an official timestamp.
template<class T> struct BasicSample {
    std::optional<T> value;
    bool stale = false;
    std::int64_t receivedAtMs = -1;
};

struct BasicState {
    BasicSample<GameData> game;
    BasicSample<GlobalUnitData> units;
    BasicSample<LogisticsData> logistics;
    BasicSample<RobotStaticData> robotStatic;
    BasicSample<RobotDynamicData> robotDynamic;
    BasicSample<RobotModuleData> robotModule;
};

} // namespace rm27::domain
