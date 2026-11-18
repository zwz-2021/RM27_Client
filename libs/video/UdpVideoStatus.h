#pragma once

#include <QElapsedTimer>
#include <QString>
#include <optional>

namespace rm27::video {

// RM27 communication protocol, chapter 2, PDF p.47.
inline constexpr int VideoHeaderBytes = 8;
inline constexpr int MaxVideoDatagramBytes = 1400;
inline constexpr int MaxFragmentBytes = MaxVideoDatagramBytes - VideoHeaderBytes;

// OS socket queue target verified with the local simulation recording.
inline constexpr int SimulationReceiveBufferBytes = 2 * 1024 * 1024;

struct UdpVideoHeader {
    quint16 frameId;
    quint16 fragmentIndex;
    quint32 frameBytes;
};

enum class UdpVideoState { Stopped, Bound, BindFailed, ReadFailed };

struct UdpFrameInfo {
    quint16 frameId;
    qsizetype bytes;
    QString sourceAddress;
    quint16 sourcePort;
};

struct VideoFrameAssemblyStats {
    quint64 completedFrames = 0;
    quint64 timeoutFrames = 0;
    quint64 conflictFrames = 0;
    quint64 limitFrames = 0;
    quint64 duplicateFragments = 0;
    quint64 ignoredLateFragments = 0;
    int pendingFrames = 0;
    int bufferedBytes = 0;
    int bufferedFragments = 0;

    quint64 droppedFrames() const { return timeoutFrames + conflictFrames + limitFrames; }
};

struct UdpVideoStatus {
    UdpVideoState state = UdpVideoState::Stopped;
    QString bindAddress;
    quint16 bindPort = 0;
    QString error;
    std::optional<int> simulationReceiveBufferBytes; // OS readback, <= 0 if unavailable.

    quint64 validPackets = 0;
    quint64 validPacketsLastSecond = 0;
    quint64 shortPackets = 0;
    quint64 oversizedPackets = 0;
    quint64 emptyPayloadPackets = 0;
    quint64 inconsistentFramePackets = 0;
    QElapsedTimer lastValidPacketAt;
    std::optional<UdpVideoHeader> lastHeader;
    QString lastSourceAddress;
    quint16 lastSourcePort = 0;
    int lastPacketBytes = 0;
    VideoFrameAssemblyStats assembly;
    quint64 completedFramesLastSecond = 0;
    std::optional<UdpFrameInfo> lastFrame;

    quint64 droppedPackets() const
    {
        return shortPackets + oversizedPackets + emptyPayloadPackets + inconsistentFramePackets;
    }
};

} // namespace rm27::video
