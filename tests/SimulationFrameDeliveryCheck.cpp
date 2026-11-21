#include "SimulationVideoDecode.h"
#include "transport/UdpVideoReceiver.h"
#include <QDir>
#include <QEvent>
#include <QTest>
#include <functional>

using rm27::client::SimulationVideoDecode;
using rm27::transport::UdpVideoReceiver;

namespace {
// Three independently decodable 32x32 YUV420p frames with Y=32,128,224 and U=V=128.
// Encoded from those uniform planes with libx265 lossless=1:keyint=1:info=0.
void sendThreePictures(UdpVideoReceiver &receiver)
{
    const auto headers = QByteArray::fromHex(
        "0000000140010c01ffff0408000003009fa80000030000ffba0240"
        "000000014201010408000003009fa80000030000ffa04208596eae4cae6808000003000800000300c840"
        "000000014401c1718912");
    quint16 id = 0;
    for (const auto picture : {
             "0000012801af05b8182eb0d219ffff9bff35fcb7e3bdef7bdef7bdff7fdff7fdff7fdff7fff0883317ad406baaa90660",
             "0000012801af05b872ae7f80",
             "0000012801af05a8182eb0d11a00ff9bff35fcb7e3bdef7bdef7bdff7fdff7fdff7fdff7fff0883317ad406baaa90660"}) {
        receiver.frameAssembled(++id, headers + QByteArray::fromHex(picture), QStringLiteral("127.0.0.1"), 1);
    }
}

class HoldFirstDelivery : public QObject {
public:
    std::function<void()> beforeDispatch;
    int wakeups = 0;

protected:
    bool eventFilter(QObject *, QEvent *event) override
    {
        if (event->type() == QEvent::MetaCall && ++wakeups == 1)
            beforeDispatch();
        return false;
    }
};
} // namespace

class SimulationFrameDeliveryCheck : public QObject {
    Q_OBJECT
private slots:
    void initTestCase()
    {
        const auto ffmpegDir = qgetenv("RM27_TEST_FFMPEG_DIR");
        if (!ffmpegDir.isEmpty())
            QVERIFY(qputenv("PATH", ffmpegDir + QDir::listSeparator().toLatin1() + qgetenv("PATH")));
    }

    void delayedDelivery_data()
    {
        QTest::addColumn<bool>("restart");
        QTest::newRow("only the latest of three frames reaches the sink") << false;
        QTest::newRow("stop and reopen before the pending delivery") << true;
    }

    void delayedDelivery()
    {
        QFETCH(bool, restart);
        UdpVideoReceiver receiver;
        SimulationVideoDecode decode(receiver, false);
        QVideoSink sink;
        decode.setVideoSink(&sink);
        int displayed = 0;
        connect(&sink, &QVideoSink::videoFrameChanged, this, [&](const QVideoFrame &frame) {
            if (frame.isValid())
                ++displayed;
        });
        QString status, rate;
        QStringList rateChanges;
        connect(&decode, &SimulationVideoDecode::statusChanged, this, [&](const QString &text) { status = text; });
        connect(&decode, &SimulationVideoDecode::decodeRateChanged, this, [&](const QString &text) {
            rate = text;
            if (rateChanges.isEmpty() || rateChanges.back() != text)
                rateChanges.append(text);
        });
        const auto loopback = QStringLiteral("127.0.0.1");
        QVERIFY(receiver.start(loopback, 0, true));
        const auto zero = QStringLiteral("最近 1 秒解码输出：0 帧/秒");
        const auto one = QStringLiteral("最近 1 秒解码输出：1 帧/秒");
        const auto two = QStringLiteral("最近 1 秒解码输出：2 帧/秒");
        const auto stopped = QStringLiteral("最近 1 秒解码输出：—");
        QCOMPARE(rate, zero);

        bool firstOutput = false;
        bool drained = false;
        bool reopened = false;
        bool stoppedRateCleared = false;
        QString rateBeforeReopen;
        QString historyBeforeReopen;
        int displayedBeforeRelease = -1;
        HoldFirstDelivery gate;
        gate.beforeDispatch = [&] {
            // Keep GUI delivery blocked while the decoder first outputs one picture,
            // then drains the final two after input has been quiet for one second.
            // The first picture has left the rate window when those two arrive.
            firstOutput = QTest::qWaitFor([&] {
                return status.contains(QStringLiteral("已解码 1 帧")) && rate == one;
            }, 2000);
            drained = QTest::qWaitFor([&] {
                return status.contains(QStringLiteral("等待输入 · 已解码 3 帧")) && rate == two;
            }, 5000);
            rateBeforeReopen = rate;
            historyBeforeReopen = rateChanges.join(';');
            displayedBeforeRelease = displayed;
            if (restart) {
                receiver.stop();
                stoppedRateCleared = rate == stopped;
                rateChanges.clear();
                reopened = receiver.start(loopback, 0, true);
            }
        };
        decode.installEventFilter(&gate);
        sendThreePictures(receiver);
        QTRY_VERIFY_WITH_TIMEOUT(gate.wakeups > 0, 7000);
        QCoreApplication::sendPostedEvents(&decode, QEvent::MetaCall);
        const auto evidence = status + QStringLiteral(" | rate history: ") + historyBeforeReopen;
        QVERIFY2(firstOutput, qPrintable(evidence));
        QVERIFY2(drained, qPrintable(evidence));
        QCOMPARE(rateBeforeReopen, two);
        QCOMPARE(displayedBeforeRelease, 0);
        QCOMPARE(gate.wakeups, 1);
        if (restart) {
            QVERIFY(reopened);
            QVERIFY(stoppedRateCleared);
            QCOMPARE(displayed, 0);
            QVERIFY(!sink.videoFrame().isValid());
            QCOMPARE(decode.displayStatus(), QStringLiteral("等待模拟画面"));
            QCOMPARE(rate, zero);
            // Dispatching the old GUI wakeup cannot count a new decoder output.
            QTest::qWait(1100);
            for (const auto &text : rateChanges)
                QCOMPARE(text, zero);
            sendThreePictures(receiver);
            QVERIFY2(QTest::qWaitFor([&] {
                return status.contains(QStringLiteral("已解码 1 帧")) && rate == one;
            }, 5000), qPrintable(status + QStringLiteral(" | rate history: ") + rateChanges.join(';')));
            QVERIFY2(QTest::qWaitFor([&] {
                return status.contains(QStringLiteral("等待输入 · 已解码 3 帧")) && rate == two;
            }, 5000), qPrintable(status + QStringLiteral(" | rate history: ") + rateChanges.join(';')));
        } else {
            QCOMPARE(displayed, 1);
            QCOMPARE(rate, two); // Both drained outputs count even though the sink receives only the final picture.
            auto frame = sink.videoFrame();
            QCOMPARE(frame.size(), QSize(32, 32));
            QVERIFY(frame.map(QVideoFrame::ReadOnly));
            QCOMPARE(QByteArrayView(frame.bits(0), frame.mappedBytes(0)), QByteArray(1024, char(224)));
            frame.unmap();
        }
        QTRY_COMPARE_WITH_TIMEOUT(rate, zero, 2500);
        receiver.stop();
        QCOMPARE(rate, stopped);
        receiver.stop();
        QCOMPARE(rate, stopped);
    }
};

QTEST_GUILESS_MAIN(SimulationFrameDeliveryCheck)
#include "SimulationFrameDeliveryCheck.moc"
