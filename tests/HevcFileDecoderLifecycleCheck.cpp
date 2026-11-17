#include "video/HevcFileDecoder.h"
#include <QDir>
#include <QFile>
#include <QSemaphore>
#include <QTemporaryDir>
#include <QTest>
#include <atomic>
#include <memory>
#include <utility>

using rm27::video::DecodedVideoFrame;
using rm27::video::HevcFileDecoder;

class HevcFileDecoderLifecycleCheck final : public QObject {
    Q_OBJECT
private slots:
    void initTestCase();
    void ownerStopsWhileDelivering();
    void destructorJoinsActiveCallback();

private:
    QTemporaryDir directory_;
    QString clip_;
};

void HevcFileDecoderLifecycleCheck::initTestCase()
{
    const auto ffmpegDir = qgetenv("RM27_TEST_FFMPEG_DIR");
    if (!ffmpegDir.isEmpty())
        QVERIFY(qputenv("PATH", ffmpegDir + QDir::listSeparator().toLatin1() + qgetenv("PATH")));

    // Eight synthetic white 32x32 frames, encoded with libx265 (no B frames or SEI).
    // Keep the lifecycle test independent of an encoder and of previously generated clips.
    const auto bytes = QByteArray::fromHex(
        "0000000140010c01ffff01600000030090000003000003001e928090"
        "0000000142010101600000030090000003000003001ea042085964ab932bc05a020000030002000003007810"
        "000000014401c173d0890000012801af0a60f1e5f4aeeed5b0"
        "000000010201d0097e10c614c0fbac000000010201d011ffd443061440fbac"
        "000000010201d0189ffdc4301851fbac000000010201d0209ffdc4301853fbac"
        "000000010201d0289ffdc4301851fbac000000010201d0309ffdc4301853fbac"
        "000000010201d0389ffdc4301851fbac");
    QVERIFY(directory_.isValid());
    clip_ = directory_.filePath("eight.hevc");
    QFile file(clip_);
    QVERIFY(file.open(QIODevice::WriteOnly));
    QCOMPARE(file.write(bytes), bytes.size());
}

void HevcFileDecoderLifecycleCheck::ownerStopsWhileDelivering()
{
    QSemaphore firstFrame, resume;
    std::atomic_int callbacks{0}, rejectedCallbacks{0};
    HevcFileDecoder decoder;
    QVERIFY(decoder.start(clip_, [&](DecodedVideoFrame frame) {
        ++callbacks;
        if (frame.index == 1) {
            firstFrame.release();
            resume.acquire();
        }
    }));
    // Release the callback even on a failed assertion so teardown can always join it.
    const bool startedDelivery = firstFrame.tryAcquire(1, 5000);
    const bool replaced = decoder.start(clip_, [&](DecodedVideoFrame) { ++rejectedCallbacks; });
    decoder.requestStop();
    decoder.requestStop();
    resume.release();
    const auto stopped = decoder.waitForFinished();
    QVERIFY(startedDelivery);
    QVERIFY(!replaced);
    QVERIFY(stopped.stopped);
    QVERIFY2(stopped.error.isEmpty(), qPrintable(stopped.error));
    QCOMPARE(stopped.frames, 1);

    int reopenedCallbacks = 0;
    QVERIFY(decoder.start(clip_, [&](DecodedVideoFrame) { ++reopenedCallbacks; }));
    const auto reopened = decoder.waitForFinished();
    QVERIFY2(reopened.error.isEmpty(), qPrintable(reopened.error));
    QVERIFY2(reopened.diagnostic.isEmpty(), qPrintable(reopened.diagnostic));
    QVERIFY(!reopened.stopped);
    QCOMPARE(reopened.frames, 8);
    QCOMPARE(reopenedCallbacks, 8);
    QCOMPARE(callbacks.load(), 1);
    QCOMPARE(rejectedCallbacks.load(), 0);
}

void HevcFileDecoderLifecycleCheck::destructorJoinsActiveCallback()
{
    struct Delivery {
        QSemaphore firstFrame, resume, workerFinished;
        QByteArray retainedPixels;
    };
    // Keep the observations valid even if a broken implementation lets a callback escape.
    const auto delivery = std::make_shared<Delivery>();
    auto decoder = std::make_unique<HevcFileDecoder>();
    QVERIFY(decoder->start(clip_, [delivery](DecodedVideoFrame frame) {
        if (frame.index == 1) {
            QObject::connect(QThread::currentThread(), &QThread::finished,
                             [delivery] { delivery->workerFinished.release(); });
            delivery->retainedPixels = std::move(frame.pixels);
            delivery->firstFrame.release();
            delivery->resume.acquire();
        }
    }));
    const bool startedDelivery = delivery->firstFrame.tryAcquire(1, 5000);
    delivery->resume.release();
    decoder.reset();
    QVERIFY(startedDelivery);
    // No callback can run after the destructor returns, independently of scheduling.
    QVERIFY(delivery->workerFinished.tryAcquire());
    // White in this limited-range 8-bit YUV420p fixture (32x32 Y, then two 16x16 planes).
    QCOMPARE(delivery->retainedPixels, QByteArray(1024, char(235)) + QByteArray(512, char(128)));
}

QTEST_GUILESS_MAIN(HevcFileDecoderLifecycleCheck)
#include "HevcFileDecoderLifecycleCheck.moc"
