#pragma once

#include "video/UdpVideoStatus.h"
#include <QByteArray>
#include <QByteArrayView>
#include <QString>
#include <deque>
#include <list>
#include <map>
#include <optional>

namespace rm27::video {

// For the simulator's zero-based fragment indices. Call with nondecreasing monotonic time.
class VideoFrameAssembler {
public:
    // Local resource budgets. The wire header does not specify these limits.
    static constexpr int MaxFrameBytes = 2 * 1024 * 1024;
    static constexpr int MaxPendingFrames = 8;
    static constexpr int MaxBufferedBytes = 4 * 1024 * 1024;
    static constexpr int MaxFragmentsPerFrame = 4096;
    static constexpr int MaxBufferedFragments = 8192;
    static constexpr int FrameTimeoutMs = 250;
    static constexpr int MaxRecentFrames = 256;

    std::optional<QByteArray> accept(const QString &sourceAddress, quint16 sourcePort,
                                     const UdpVideoHeader &header, QByteArrayView payload,
                                     qint64 nowMs);
    bool expire(qint64 nowMs);
    std::optional<qint64> nextDeadlineMs() const;
    void reset();
    const VideoFrameAssemblyStats &stats() const { return stats_; }

private:
    struct FrameKey {
        QString address;
        quint16 port;
        quint16 id;

        bool operator==(const FrameKey &other) const
        {
            return id == other.id && port == other.port && address == other.address;
        }
    };
    struct Pending {
        FrameKey key;
        quint32 declaredBytes;
        qint64 deadline;
        int receivedBytes = 0;
        std::map<quint16, QByteArray> fragments;
    };
    struct Closed {
        FrameKey key;
        qint64 until;
    };

    using PendingIterator = std::list<Pending>::iterator;
    void removePending(PendingIterator frame);
    void remember(const FrameKey &key, qint64 nowMs);

    std::list<Pending> pending_; // Earliest deadline first, regardless of wire frame ID.
    std::deque<Closed> recent_;
    VideoFrameAssemblyStats stats_;
};

} // namespace rm27::video
