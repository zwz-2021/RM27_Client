#include "video/VideoFrameAssembler.h"
#include <QTest>
#include <algorithm>

using rm27::video::UdpVideoHeader;
using rm27::video::VideoFrameAssembler;

namespace {
const QString Local = QStringLiteral("127.0.0.1");
constexpr quint16 Port = 40234;
}

class VideoFrameAssemblerCheck final : public QObject {
    Q_OBJECT
private slots:
    void reversedFragmentsAndWrap();
    void endpointIsolation();
    void conflicts();
    void deadlinesAndReset();
    void frameAndMetadataLimits();
    void totalByteBudget();
};

void VideoFrameAssemblerCheck::reversedFragmentsAndWrap()
{
    VideoFrameAssembler frames;
    const QByteArray original = QByteArray::fromHex("0000000126010080ff201a");
    QByteArray tail = original.mid(8);
    QVERIFY(!frames.accept(Local, Port, {65535, 2, 11}, tail, 0));
    QVERIFY(!frames.accept(Local, Port, {65535, 2, 11}, tail, 1));
    tail.fill('x'); // The receive buffer can be overwritten before the next datagram.
    QVERIFY(!frames.accept(Local, Port, {0, 1, 3}, "YZ", 2));
    QVERIFY(!frames.accept(Local, Port, {65535, 0, 11}, original.first(3), 3));
    const auto complete = frames.accept(Local, Port, {65535, 1, 11}, original.mid(3, 5), 4);
    QVERIFY(complete);
    QCOMPARE(*complete, original);
    const auto wrapped = frames.accept(Local, Port, {0, 0, 3}, "X", 5);
    QVERIFY(wrapped);
    QCOMPARE(*wrapped, QByteArray("XYZ"));
    QVERIFY(!frames.accept(Local, Port, {0, 0, 3}, "X", 6));
    QCOMPARE(frames.stats().completedFrames, 2ULL);
    QCOMPARE(frames.stats().duplicateFragments, 1ULL);
    QCOMPARE(frames.stats().ignoredLateFragments, 1ULL);
    QCOMPARE(frames.stats().droppedFrames(), 0ULL);
    QCOMPARE(frames.stats().bufferedBytes, 0);
    QCOMPARE(frames.stats().bufferedFragments, 0);
    QVERIFY(!frames.nextDeadlineMs());
}

void VideoFrameAssemblerCheck::endpointIsolation()
{
    VideoFrameAssembler frames;
    const QString secondIp = QStringLiteral("127.0.0.2");
    QVERIFY(!frames.accept(Local, Port, {7, 0, 2}, "A", 0));
    QVERIFY(!frames.accept(Local, Port + 1, {7, 1, 2}, "D", 0));
    QVERIFY(!frames.accept(secondIp, Port, {7, 1, 2}, "F", 0));
    QCOMPARE(frames.stats().pendingFrames, 3);
    const auto first = frames.accept(Local, Port, {7, 1, 2}, "B", 0);
    const auto second = frames.accept(Local, Port + 1, {7, 0, 2}, "C", 0);
    const auto third = frames.accept(secondIp, Port, {7, 0, 2}, "E", 0);
    QVERIFY(first && second && third);
    QCOMPARE(*first, QByteArray("AB"));
    QCOMPARE(*second, QByteArray("CD"));
    QCOMPARE(*third, QByteArray("EF"));
}

void VideoFrameAssemblerCheck::conflicts()
{
    VideoFrameAssembler frames;
    QVERIFY(!frames.accept(Local, Port, {11, 0, 3}, "A", 0));
    QVERIFY(!frames.accept(Local, Port, {11, 1, 4}, "BC", 0)); // Contradictory frame length.
    QVERIFY(!frames.accept(Local, Port, {11, 1, 3}, "BC", 0)); // Late after discard.
    QVERIFY(!frames.accept(Local, Port, {12, 0, 3}, "A", 0));
    QVERIFY(!frames.accept(Local, Port, {12, 0, 3}, "X", 0)); // Conflicting duplicate.
    QVERIFY(!frames.accept(Local, Port, {13, 0, 3}, "AB", 0));
    QVERIFY(!frames.accept(Local, Port, {13, 1, 3}, "CD", 0)); // Total exceeds declaration.
    QVERIFY(!frames.accept(Local, Port, {14, 2, 2}, "Z", 0)); // A missing index cannot be empty.
    QVERIFY(!frames.accept(Local, Port, {15, 0, 1}, "AB", 0)); // Even a single fragment cannot fit.
    QCOMPARE(frames.stats().conflictFrames, 5ULL);
    QCOMPARE(frames.stats().ignoredLateFragments, 1ULL);
    QCOMPARE(frames.stats().completedFrames, 0ULL);
    QCOMPARE(frames.stats().pendingFrames, 0);
    QCOMPARE(frames.stats().bufferedBytes, 0);
}

void VideoFrameAssemblerCheck::deadlinesAndReset()
{
    VideoFrameAssembler frames;
    constexpr int deadline = VideoFrameAssembler::FrameTimeoutMs;
    QVERIFY(!frames.accept(Local, Port, {7, 1, 3}, "B", 0));
    QVERIFY(!frames.accept(Local, Port, {7, 1, 3}, "B", deadline - 1));
    QVERIFY(!frames.accept(Local, Port, {8, 0, 2}, "X", deadline - 1));
    QVERIFY(frames.nextDeadlineMs());
    QCOMPARE(*frames.nextDeadlineMs(), deadline);
    QVERIFY(!frames.expire(deadline - 1));
    QVERIFY(frames.expire(deadline));
    QVERIFY(!frames.expire(deadline));
    QCOMPARE(frames.stats().timeoutFrames, 1ULL);
    QCOMPARE(frames.stats().pendingFrames, 1);
    QCOMPARE(frames.stats().bufferedBytes, 1);
    QVERIFY(!frames.accept(Local, Port, {7, 0, 3}, "A", deadline)); // Can't restart a stale frame.
    QVERIFY(frames.nextDeadlineMs());
    QCOMPARE(*frames.nextDeadlineMs(), 2 * deadline - 1);
    const auto reused = frames.accept(Local, Port, {7, 0, 1}, "X", 2 * deadline);
    QVERIFY(reused && *reused == "X");
    QCOMPARE(frames.stats().timeoutFrames, 2ULL);
    QVERIFY(!frames.accept(Local, Port, {9, 0, 2}, "Y", 2 * deadline));
    frames.reset();
    QCOMPARE(frames.stats().bufferedFragments, 0);
    QCOMPARE(frames.stats().pendingFrames, 0);
    QCOMPARE(frames.stats().completedFrames, 0ULL);
    QCOMPARE(frames.stats().droppedFrames(), 0ULL);
    QCOMPARE(frames.stats().ignoredLateFragments, 0ULL);
    QVERIFY(!frames.nextDeadlineMs());
    QVERIFY(frames.accept(Local, Port, {7, 0, 1}, "Z", 0));
}

void VideoFrameAssemblerCheck::frameAndMetadataLimits()
{
    VideoFrameAssembler frames;
    QVERIFY(!frames.accept(Local, Port, {1, 0, 0xffffffffU}, "X", 0));
    QVERIFY(!frames.accept(Local, Port, {2, VideoFrameAssembler::MaxFragmentsPerFrame, 20000}, "X", 0));
    QCOMPARE(frames.stats().limitFrames, 2ULL);
    QCOMPARE(frames.stats().bufferedBytes, 0);
    for (quint16 i = 0; i < VideoFrameAssembler::MaxPendingFrames; ++i)
        QVERIFY(!frames.accept(Local, Port, {quint16(10 + i), 0, 2}, "X", 0));
    QVERIFY(!frames.accept(Local, Port, {30, 0, 2}, "Y", 0));
    QCOMPARE(frames.stats().pendingFrames, VideoFrameAssembler::MaxPendingFrames);
    QCOMPARE(frames.stats().limitFrames, 3ULL);
    QVERIFY(frames.accept(Local, Port, {10, 1, 2}, "Z", 0));

    frames.reset();
    constexpr int partsPerFrame = VideoFrameAssembler::MaxBufferedFragments / 4;
    for (quint16 frame = 0; frame < 4; ++frame) {
        for (quint16 i = 0; i < partsPerFrame; ++i)
            QVERIFY(!frames.accept(Local, Port, {frame, i, partsPerFrame + 1}, "Y", 0));
    }
    QCOMPARE(frames.stats().bufferedFragments, VideoFrameAssembler::MaxBufferedFragments);
    QVERIFY(!frames.accept(Local, Port, {5, 0, 2}, "Z", 0));
    QCOMPARE(frames.stats().limitFrames, 1ULL);
    QVERIFY(frames.expire(VideoFrameAssembler::FrameTimeoutMs));
    QCOMPARE(frames.stats().bufferedFragments, 0);
    QCOMPARE(frames.stats().bufferedBytes, 0);
    QCOMPARE(frames.stats().timeoutFrames, 4ULL);
}

void VideoFrameAssemblerCheck::totalByteBudget()
{
    VideoFrameAssembler frames;
    constexpr quint32 frameSize = VideoFrameAssembler::MaxFrameBytes;
    const QByteArray chunk(1392, 'Q');
    quint16 nextIndex = 0;
    for (quint16 id : {100, 101}) {
        nextIndex = 0;
        quint32 remaining = frameSize - 1;
        while (remaining > 0) {
            const auto size = std::min(remaining, quint32(chunk.size()));
            QVERIFY(!frames.accept(Local, Port, {id, nextIndex++, frameSize}, QByteArrayView(chunk).first(size), 0));
            remaining -= size;
        }
    }
    QVERIFY(!frames.accept(Local, Port, {102, 0, 3}, "AB", 0));
    QCOMPARE(frames.stats().bufferedBytes, VideoFrameAssembler::MaxBufferedBytes);
    QVERIFY(!frames.accept(Local, Port, {102, 1, 3}, "C", 0)); // One byte over, discard only 102.
    QCOMPARE(frames.stats().limitFrames, 1ULL);
    QCOMPARE(frames.stats().bufferedBytes, VideoFrameAssembler::MaxBufferedBytes - 2);
    const QByteArray expected = QByteArray(frameSize - 1, 'Q') + 'Z';
    for (quint16 id : {100, 101}) {
        const auto complete = frames.accept(Local, Port, {id, nextIndex, frameSize}, "Z", 0);
        QVERIFY(complete);
        QCOMPARE(*complete, expected);
    }
    QCOMPARE(frames.stats().pendingFrames, 0);
    QCOMPARE(frames.stats().bufferedBytes, 0);
    QCOMPARE(frames.stats().bufferedFragments, 0);
}

QTEST_GUILESS_MAIN(VideoFrameAssemblerCheck)
#include "VideoFrameAssemblerCheck.moc"
