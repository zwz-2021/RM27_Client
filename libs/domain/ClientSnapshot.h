#pragma once

#include <cstdint>

namespace rm27::domain {

// 骨架阶段的演示心跳，不代表任何赛季的正式比赛协议。
struct ClientSnapshot {
    std::uint64_t sequence = 0;
    int elapsedSeconds = 0;
};

} // namespace rm27::domain
