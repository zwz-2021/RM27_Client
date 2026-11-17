#include "video/HevcStreamDecoder.h"
#include <QDir>
#include <QFile>
#include <QScopeGuard>
#include <QSemaphore>
#include <QTemporaryDir>
#include <QTest>
#include <cstdio>
#include <cstring>

using rm27::video::DecodedVideoFrame;
using rm27::video::HevcStreamDecoder;

namespace {
// One independently encoded, white 32x32 4:2:0 picture with its parameter sets.
const QByteArray WhitePicture = QByteArray::fromHex(
    "0000000140010c01ffff01600000030090000003000003001e928090"
    "0000000142010101600000030090000003000003001ea042085964ab932bc05a020000030002000003007810"
    "000000014401c173d0890000012801af0a60f1e5f4aeeed5b0");
}

class HevcStreamDecoderCheck final : public QObject {
    Q_OBJECT
private slots:
    void initTestCase();
    void boundedWhileConsumerIsBusy_data();
    void boundedWhileConsumerIsBusy();
    void failedSegmentThenRestart();
    void missingDecoderReportsRejectedInput();
    void stalledChildAfterEndOfInput();
};

void HevcStreamDecoderCheck::initTestCase()
{
    const auto ffmpegDir = qgetenv("RM27_TEST_FFMPEG_DIR");
    if (!ffmpegDir.isEmpty())
        QVERIFY(qputenv("PATH", ffmpegDir + QDir::listSeparator().toLatin1() + qgetenv("PATH")));
}

void HevcStreamDecoderCheck::boundedWhileConsumerIsBusy_data()
{
    QTest::addColumn<int>("unitBytes");
    QTest::addColumn<int>("accepted");
    QTest::newRow("frame limit") << 1 << HevcStreamDecoder::MaxPendingFrames;
    QTest::newRow("byte limit") << HevcStreamDecoder::MaxAccessUnitBytes
                               << HevcStreamDecoder::MaxPendingBytes / HevcStreamDecoder::MaxAccessUnitBytes;
}

void HevcStreamDecoderCheck::boundedWhileConsumerIsBusy()
{
    QFETCH(int, unitBytes);
    QFETCH(int, accepted);
    QSemaphore firstPicture, resume;
    QByteArray pixels;
    HevcStreamDecoder decoder;
    const auto releaseOnFailure = qScopeGuard([&] { resume.release(); });
    QVERIFY(!decoder.submit(WhitePicture));
    QVERIFY(decoder.start([&](DecodedVideoFrame frame) {
        pixels = frame.pixels;
        firstPicture.release();
        resume.acquire();
    }));
    QVERIFY(!decoder.start([](DecodedVideoFrame) {}));
    QVERIFY(decoder.submit(WhitePicture));
    QVERIFY(firstPicture.tryAcquire(1, 5000)); // The idle segment drains its final picture.
    QCOMPARE(pixels, QByteArray(1024, char(235)) + QByteArray(512, char(128)));
    QVERIFY(!decoder.submit({}));
    QVERIFY(!decoder.submit(QByteArray(HevcStreamDecoder::MaxAccessUnitBytes + 1, 'x')));
    const QByteArray bytes(unitBytes, 'x');
    for (int index = 0; index < accepted; ++index)
        QVERIFY(decoder.submit(bytes));
    QVERIFY(!decoder.submit(bytes));
    const auto full = decoder.status();
    QCOMPARE(full.pendingFrames, accepted);
    QCOMPARE(full.pendingBytes, accepted * unitBytes);
    QCOMPARE(full.droppedFrames, 3ULL);
    QCOMPARE(full.decodedFrames, 1ULL);
    QVERIFY(full.segmentActive);

    // Keep the consumer blocked until the owner has discarded the entire waiting queue.
    auto unblock = std::unique_ptr<QThread>(QThread::create([&] {
        while (decoder.status().pendingFrames)
            QThread::msleep(1);
        resume.release();
    }));
    unblock->start();
    const auto stopped = decoder.stop();
    unblock->wait();
    QCOMPARE(stopped.decodedFrames, 1ULL);
    QCOMPARE(stopped.droppedFrames, 3ULL);
    QCOMPARE(stopped.pendingBytes, 0);
    QVERIFY(!stopped.segmentActive);
    QCOMPARE(decoder.status().decodedFrames, 0ULL);
    QVERIFY(!decoder.submit(WhitePicture));
}

void HevcStreamDecoderCheck::failedSegmentThenRestart()
{
    HevcStreamDecoder decoder;
    QSemaphore picture;
    int index = 0;
    const auto start = [&] {
        return decoder.start([&](DecodedVideoFrame frame) {
            index = frame.index;
            picture.release();
        });
    };
    QVERIFY(start());
    QVERIFY(decoder.submit(QByteArray(100, 'x')));
    QTRY_VERIFY_WITH_TIMEOUT(!decoder.status().error.isEmpty(), 5000);
    auto failed = decoder.status();
    QVERIFY(!failed.segmentActive);
    QCOMPARE(failed.decodedFrames, 0ULL);
    QVERIFY(decoder.submit(WhitePicture));
    QVERIFY(picture.tryAcquire(1, 5000));
    QCOMPARE(index, 1);
    QTRY_VERIFY_WITH_TIMEOUT(!decoder.status().segmentActive, 5000);
    auto recovered = decoder.status();
    QVERIFY2(recovered.error.isEmpty(), qPrintable(recovered.error));
    QVERIFY2(recovered.diagnostic.isEmpty(), qPrintable(recovered.diagnostic));
    QCOMPARE(recovered.width, 32);
    QCOMPARE(recovered.height, 32);
    QVERIFY(decoder.submit(WhitePicture));
    QVERIFY(picture.tryAcquire(1, 5000));
    QCOMPARE(index, 2);
    decoder.stop();
    QVERIFY(start());
    QVERIFY(decoder.submit(WhitePicture));
    QVERIFY(picture.tryAcquire(1, 5000));
    QCOMPARE(index, 1);
    QCOMPARE(decoder.stop().decodedFrames, 1ULL);
}

void HevcStreamDecoderCheck::missingDecoderReportsRejectedInput()
{
    QTemporaryDir emptyDirectory;
    QVERIFY(emptyDirectory.isValid());
    const auto savedPath = qgetenv("PATH");
    const auto restorePath = qScopeGuard([&] { qputenv("PATH", savedPath); });
    QVERIFY(qputenv("PATH", emptyDirectory.path().toLocal8Bit()));
    HevcStreamDecoder decoder;
    QVERIFY(decoder.start([](DecodedVideoFrame) {}));
    QVERIFY(decoder.submit(WhitePicture));
    QTRY_VERIFY_WITH_TIMEOUT(decoder.status().error.contains("FFmpeg"), 5000);
    QVERIFY(!decoder.submit(WhitePicture));
    const auto failed = decoder.stop();
    QCOMPARE(failed.droppedFrames, 2ULL);
    QCOMPARE(failed.decodedFrames, 0ULL);
    QCOMPARE(failed.pendingFrames, 0);
    QVERIFY(!failed.segmentActive);
}

void HevcStreamDecoderCheck::stalledChildAfterEndOfInput()
{
    QTemporaryDir folder;
    QVERIFY(folder.isValid());
#ifdef Q_OS_WIN
    const QString name = QStringLiteral("ffmpeg.exe");
#else
    const QString name = QStringLiteral("ffmpeg");
#endif
    QVERIFY(QFile::copy(QCoreApplication::applicationFilePath(), folder.filePath(name)));
    const auto savedPath = qgetenv("PATH");
    const auto restorePath = qScopeGuard([&] { qputenv("PATH", savedPath); });
    QVERIFY(qputenv("PATH", folder.path().toLocal8Bit() + QDir::listSeparator().toLatin1() + savedPath));
    HevcStreamDecoder decoder;
    QVERIFY(decoder.start([](DecodedVideoFrame) {}));
    QVERIFY(decoder.submit(WhitePicture));
    const int limit = HevcStreamDecoder::IdleDrainMs + HevcStreamDecoder::DrainProgressTimeoutMs + 4000;
    QTRY_VERIFY_WITH_TIMEOUT(decoder.status().error.contains(QStringLiteral("排空超时")), limit);
    QCOMPARE(decoder.stop().decodedFrames, 0ULL);
}

int main(int argc, char **argv)
{
    // When copied as the test's FFmpeg stand-in, consume stdin through EOF, then hang.
    if (argc > 1 && std::strcmp(argv[1], "-hide_banner") == 0) {
        while (std::getchar() != EOF) {}
        QThread::sleep(30);
        return 1;
    }
    QCoreApplication app(argc, argv);
    HevcStreamDecoderCheck test;
    return QTest::qExec(&test, argc, argv);
}

#include "HevcStreamDecoderCheck.moc"
