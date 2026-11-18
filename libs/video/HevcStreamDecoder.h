#pragma once

#include "video/HevcFileDecoder.h"
#include <QMutex>
#include <QWaitCondition>
#include <deque>

namespace rm27::video {

enum class HevcStreamPhase { Idle, WaitingForPicture, Decoding };

struct HevcStreamStatus {
    int pendingFrames = 0;
    qsizetype pendingBytes = 0;
    quint64 droppedFrames = 0;
    quint64 decodedFrames = 0;
    int width = 0;
    int height = 0;
    HevcStreamPhase phase = HevcStreamPhase::Idle;
    QString error;
    QString diagnostic;
};

// Input is one assembled Annex B access unit from the local recording simulator.
// Start/stop/destruction belong to the owner thread. submit/status are thread-safe.
class HevcStreamDecoder {
public:
    static constexpr int MaxAccessUnitBytes = 2 * 1024 * 1024;
    static constexpr int MaxPendingFrames = 32;
    static constexpr int MaxPendingBytes = 4 * 1024 * 1024;
    static constexpr int IdleDrainMs = 1000;
    static constexpr int DrainProgressTimeoutMs = 5000;

    ~HevcStreamDecoder();
    bool start(HevcFileDecoder::FrameHandler onFrame);
    bool submit(const QByteArray &accessUnit);
    HevcStreamStatus status() const;
    HevcStreamStatus stop(); // Final joined snapshot; subsequent status() is empty.

private:
    void run(const HevcFileDecoder::FrameHandler &onFrame);
    void clearQueue();

    std::unique_ptr<QThread> worker_;
    mutable QMutex mutex_;
    QWaitCondition inputReady_;
    std::deque<QByteArray> queue_;
    HevcStreamStatus status_;
    bool accepting_ = false;
    std::atomic_bool stopping_{false};
};

} // namespace rm27::video
