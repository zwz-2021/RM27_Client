#pragma once

#include <QString>
#include <optional>

namespace rm27::video {

struct UdpVideoHeader {
    quint16 frameId;
    quint16 fragmentIndex;
    quint32 frameBytes;
};

enum class UdpVideoState { Stopped, Bound, BindFailed, ReadFailed };

struct UdpVideoStatus {
    UdpVideoState state = UdpVideoState::Stopped;
    QString bindAddress;
    quint16 bindPort = 0;
    QString error;

    quint64 validPackets = 0;
    quint64 shortPackets = 0;
    quint64 oversizedPackets = 0;
    quint64 emptyPayloadPackets = 0;
    quint64 inconsistentFramePackets = 0;
    std::optional<UdpVideoHeader> lastHeader;
    QString lastSourceAddress;
    quint16 lastSourcePort = 0;
    int lastPacketBytes = 0;

    quint64 droppedPackets() const
    {
        return shortPackets + oversizedPackets + emptyPayloadPackets + inconsistentFramePackets;
    }
};

} // namespace rm27::video
