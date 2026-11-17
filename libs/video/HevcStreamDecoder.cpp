#include "video/HevcStreamDecoder.h"
#include "video/HevcDecodeProcess_p.h"
#include <QElapsedTimer>
#include <QProcess>
#include <utility>

namespace rm27::video {

HevcStreamDecoder::~HevcStreamDecoder()
{
    stop();
}

bool HevcStreamDecoder::start(HevcFileDecoder::FrameHandler onFrame)
{
    if (worker_ || !onFrame)
        return false;
    {
        QMutexLocker lock(&mutex_);
        status_ = {};
        stopping_ = false;
        accepting_ = true;
    }
    worker_.reset(QThread::create([this, onFrame = std::move(onFrame)] { run(onFrame); }));
    worker_->start();
    return true;
}

bool HevcStreamDecoder::submit(const QByteArray &accessUnit)
{
    QMutexLocker lock(&mutex_);
    if (!accepting_) {
        if (!stopping_ && !status_.error.isEmpty())
            ++status_.droppedFrames;
        return false;
    }
    if (accessUnit.isEmpty() || accessUnit.size() > MaxAccessUnitBytes ||
        status_.pendingFrames >= MaxPendingFrames ||
        accessUnit.size() > MaxPendingBytes - status_.pendingBytes) {
        ++status_.droppedFrames;
        return false;
    }
    queue_.push_back(accessUnit);
    ++status_.pendingFrames;
    status_.pendingBytes += accessUnit.size();
    inputReady_.wakeOne();
    return true;
}

HevcStreamStatus HevcStreamDecoder::status() const
{
    QMutexLocker lock(&mutex_);
    return status_;
}

void HevcStreamDecoder::clearQueue()
{
    queue_.clear();
    status_.pendingFrames = 0;
    status_.pendingBytes = 0;
}

HevcStreamStatus HevcStreamDecoder::stop()
{
    {
        QMutexLocker lock(&mutex_);
        accepting_ = false;
        stopping_ = true;
        clearQueue();
        inputReady_.wakeOne();
    }
    if (worker_) {
        worker_->wait();
        worker_.reset();
    }
    QMutexLocker lock(&mutex_);
    auto finished = status_;
    status_ = {};
    return finished;
}

void HevcStreamDecoder::run(const HevcFileDecoder::FrameHandler &onFrame)
{
    while (!stopping_) {
        {
            QMutexLocker lock(&mutex_);
            while (queue_.empty() && !stopping_)
                inputReady_.wait(&mutex_);
            if (stopping_)
                return;
            status_.segmentActive = true;
        }

        bool inputClosed = false;
        bool hasSegmentDiagnostic = false;
        QString writeError;
        QString drainError;
        QElapsedTimer lastWrite;
        QElapsedTimer drainProgress;
        const auto feed = [&](QProcess &decoder) {
            // The process's own write queue holds at most one additional access unit.
            if (stopping_ || decoder.state() != QProcess::Running)
                return;
            if (inputClosed) {
                if (drainProgress.isValid() && drainProgress.hasExpired(DrainProgressTimeoutMs)) {
                    drainError = QStringLiteral("模拟视频末帧排空超时");
                    drainProgress.invalidate();
                    decoder.kill();
                }
                return;
            }
            if (decoder.bytesToWrite() > 0)
                return;
            QByteArray bytes;
            {
                QMutexLocker lock(&mutex_);
                if (!queue_.empty()) {
                    bytes = std::move(queue_.front());
                    queue_.pop_front();
                    --status_.pendingFrames;
                    status_.pendingBytes -= bytes.size();
                }
            }
            if (!bytes.isEmpty()) {
                if (decoder.write(bytes) != bytes.size()) {
                    writeError = QStringLiteral("无法写入 HEVC 解码输入：%1").arg(decoder.errorString());
                    inputClosed = true;
                    decoder.kill();
                }
                lastWrite.start();
            } else if (lastWrite.isValid() && lastWrite.hasExpired(IdleDrainMs)) {
                // UDP has no end-of-file message. Drain a quiet local recording segment
                // so the final delayed pictures are available even after its sender exits.
                decoder.closeWriteChannel();
                inputClosed = true;
                drainProgress.start();
            }
        };
        const auto deliver = [&](DecodedVideoFrame frame) {
            {
                QMutexLocker lock(&mutex_);
                if (stopping_)
                    return;
                frame.index = static_cast<int>(++status_.decodedFrames);
                status_.width = frame.width;
                status_.height = frame.height;
                status_.error.clear();
                if (!hasSegmentDiagnostic)
                    status_.diagnostic.clear();
            }
            onFrame(std::move(frame));
            if (drainProgress.isValid())
                drainProgress.restart();
        };
        const auto diagnostic = [&](const QString &message) {
            QMutexLocker lock(&mutex_);
            hasSegmentDiagnostic = true;
            status_.diagnostic = message;
        };
        const auto result = detail::decodeHevc({}, stopping_, deliver, feed, diagnostic);
        QMutexLocker lock(&mutex_);
        status_.segmentActive = false;
        if (stopping_)
            return;
        status_.error = writeError.isEmpty() ? result.error : writeError;
        if (!drainError.isEmpty())
            status_.error = drainError;
        status_.diagnostic = result.diagnostic;
        if (!lastWrite.isValid() || !writeError.isEmpty()) {
            // A startup/pipe failure cannot make progress on queued data.
            status_.droppedFrames += status_.pendingFrames;
            clearQueue();
            accepting_ = false;
            return;
        }
    }
}

} // namespace rm27::video
