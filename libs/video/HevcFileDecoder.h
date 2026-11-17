#pragma once

#include <QByteArray>
#include <QString>
#include <QThread>
#include <atomic>
#include <functional>
#include <memory>

namespace rm27::video {

struct DecodedVideoFrame {
    int index;
    int width;
    int height;
    QByteArray pixels; // Owned, tightly packed 8-bit Y, U, V planes (4:2:0).
};

struct HevcDecodeResult {
    int frames = 0;
    bool stopped = false;
    QString error;
    QString diagnostic; // Tail of FFmpeg's error output, including recoverable errors.
};

class HevcFileDecoder {
public:
    using FrameHandler = std::function<void(DecodedVideoFrame)>;
    ~HevcFileDecoder();

    // Start, wait and destroy on the owning thread. Wait before starting another file.
    // The worker calls onFrame synchronously. The consumer may keep the frame by value.
    bool start(const QString &file, FrameHandler onFrame);
    void requestStop(); // Thread-safe, including inside onFrame.
    HevcDecodeResult waitForFinished();

private:
    std::unique_ptr<QThread> worker_;
    std::atomic_bool stopRequested_{false};
    HevcDecodeResult result_;
};

} // namespace rm27::video
