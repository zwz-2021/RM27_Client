#include "video/VideoFrameAssembler.h"

#include <algorithm>
#include <iterator>

namespace rm27::video {

void VideoFrameAssembler::removePending(PendingIterator frame)
{
    stats_.bufferedBytes -= frame->receivedBytes;
    stats_.bufferedFragments -= static_cast<int>(frame->fragments.size());
    --stats_.pendingFrames;
    pending_.erase(frame);
}

void VideoFrameAssembler::remember(const FrameKey &key, qint64 nowMs)
{
    if (recent_.size() == MaxRecentFrames)
        recent_.pop_front();
    recent_.push_back({key, nowMs + FrameTimeoutMs});
}

bool VideoFrameAssembler::expire(qint64 nowMs)
{
    while (!recent_.empty() && recent_.front().until <= nowMs)
        recent_.pop_front();
    bool changed = false;
    while (!pending_.empty() && pending_.front().deadline <= nowMs) {
        remember(pending_.front().key, nowMs);
        removePending(pending_.begin());
        ++stats_.timeoutFrames;
        changed = true;
    }
    return changed;
}

std::optional<qint64> VideoFrameAssembler::nextDeadlineMs() const
{
    if (pending_.empty())
        return std::nullopt;
    return pending_.front().deadline;
}

void VideoFrameAssembler::reset()
{
    pending_.clear();
    recent_.clear();
    stats_ = {};
}

std::optional<QByteArray> VideoFrameAssembler::accept(const QString &sourceAddress, quint16 sourcePort,
                                                     const UdpVideoHeader &header, QByteArrayView payload,
                                                     qint64 nowMs)
{
    expire(nowMs);
    const FrameKey key{sourceAddress, sourcePort, header.frameId};
    if (std::any_of(recent_.begin(), recent_.end(), [&](const Closed &entry) { return entry.key == key; })) {
        ++stats_.ignoredLateFragments;
        return std::nullopt;
    }
    auto frame = std::find_if(pending_.begin(), pending_.end(),
                              [&](const Pending &entry) { return entry.key == key; });
    const auto drop = [&](quint64 &counter) {
        if (frame != pending_.end())
            removePending(frame);
        ++counter;
        remember(key, nowMs);
        return std::nullopt;
    };
    if (frame != pending_.end() && frame->declaredBytes != header.frameBytes)
        return drop(stats_.conflictFrames);
    if (payload.isEmpty() || payload.size() > MaxFragmentBytes || payload.size() > header.frameBytes)
        return drop(stats_.conflictFrames);
    if (header.frameBytes > MaxFrameBytes || header.fragmentIndex >= MaxFragmentsPerFrame)
        return drop(stats_.limitFrames);
    if (frame == pending_.end()) {
        if (stats_.pendingFrames == MaxPendingFrames)
            return drop(stats_.limitFrames);
        pending_.push_back({key, header.frameBytes, nowMs + FrameTimeoutMs, 0, {}});
        frame = std::prev(pending_.end());
        ++stats_.pendingFrames;
    }

    auto &fragments = frame->fragments;
    const auto existing = fragments.find(header.fragmentIndex);
    if (existing != fragments.end()) {
        if (QByteArrayView(existing->second) != payload)
            return drop(stats_.conflictFrames);
        ++stats_.duplicateFragments;
        return std::nullopt;
    }

    const int payloadBytes = static_cast<int>(payload.size());
    const int nextBytes = frame->receivedBytes + payloadBytes;
    const int highestIndex = fragments.empty() ? header.fragmentIndex
                                               : std::max(fragments.rbegin()->first, header.fragmentIndex);
    // Every missing index below the highest seen must contribute at least one byte.
    const int missing = highestIndex - static_cast<int>(fragments.size());
    if (nextBytes + missing > static_cast<int>(header.frameBytes))
        return drop(stats_.conflictFrames);
    const int slotsLeft = MaxFragmentsPerFrame - static_cast<int>(fragments.size()) - 1;
    if (nextBytes + slotsLeft * MaxFragmentBytes < static_cast<int>(header.frameBytes))
        return drop(stats_.limitFrames);
    if (stats_.bufferedBytes + payloadBytes > MaxBufferedBytes || stats_.bufferedFragments == MaxBufferedFragments)
        return drop(stats_.limitFrames);

    fragments.emplace(header.fragmentIndex, QByteArray(payload.data(), payloadBytes));
    frame->receivedBytes = nextBytes;
    stats_.bufferedBytes += payloadBytes;
    ++stats_.bufferedFragments;
    if (nextBytes != static_cast<int>(header.frameBytes))
        return std::nullopt;

    // Contiguity is proved above when nextBytes == declaredBytes. Allocate the
    // contiguous result only now, from the number of bytes actually received.
    QByteArray bytes;
    bytes.reserve(nextBytes);
    for (const auto &fragment : fragments)
        bytes.append(fragment.second);
    removePending(frame);
    remember(key, nowMs);
    ++stats_.completedFrames;
    return bytes;
}

} // namespace rm27::video
