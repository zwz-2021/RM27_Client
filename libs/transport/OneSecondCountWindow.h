#pragma once

#include <QtTypes>
#include <deque>

namespace rm27::transport {

// Group events by monotonic millisecond to keep at most 1000 buckets.
class OneSecondCountWindow {
public:
    quint64 record(qint64 nowMs)
    {
        countAt(nowMs);
        if (buckets_.empty() || buckets_.back().timeMs != nowMs)
            buckets_.push_back({nowMs, 0});
        ++buckets_.back().count;
        return ++count_;
    }

    quint64 countAt(qint64 nowMs)
    {
        while (!buckets_.empty() && nowMs - buckets_.front().timeMs >= 1000) {
            count_ -= buckets_.front().count;
            buckets_.pop_front();
        }
        return count_;
    }

    void clear()
    {
        buckets_.clear();
        count_ = 0;
    }

private:
    struct Bucket {
        qint64 timeMs;
        quint64 count;
    };
    std::deque<Bucket> buckets_;
    quint64 count_ = 0;
};

} // namespace rm27::transport
