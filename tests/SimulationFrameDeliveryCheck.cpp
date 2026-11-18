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
        QString status;
        connect(&decode, &SimulationVideoDecode::statusChanged, this, [&](const QString &text) { status = text; });
        const auto loopback = QStringLiteral("127.0.0.1");
        QVERIFY(receiver.start(loopback, 0, true));

        bool drained = false;
        bool reopened = false;
        HoldFirstDelivery gate;
        gate.beforeDispatch = [&] {
            // Leave the first queued delivery on the stack. The diagnostic timer can
            // still report that the worker has finished the entire three-picture stream.
            drained = QTest::qWaitFor([&] { return status.contains(QStringLiteral("等待输入 · 已解码 3 帧")); }, 6000);
            if (restart) {
                receiver.stop();
                reopened = receiver.start(loopback, 0, true);
            }
        };
        decode.installEventFilter(&gate);
        sendThreePictures(receiver);
        QTRY_VERIFY_WITH_TIMEOUT(gate.wakeups > 0, 7000);
        QCoreApplication::sendPostedEvents(&decode, QEvent::MetaCall);
        QVERIFY2(drained, qPrintable(status));
        QCOMPARE(gate.wakeups, 1);
        if (restart) {
            QVERIFY(reopened);
            QCOMPARE(displayed, 0);
            QVERIFY(!sink.videoFrame().isValid());
            QCOMPARE(decode.displayStatus(), QStringLiteral("等待模拟画面"));
        } else {
            QCOMPARE(displayed, 1);
            auto frame = sink.videoFrame();
            QCOMPARE(frame.size(), QSize(32, 32));
            QVERIFY(frame.map(QVideoFrame::ReadOnly));
            QCOMPARE(QByteArrayView(frame.bits(0), frame.mappedBytes(0)), QByteArray(1024, char(224)));
            frame.unmap();
        }
        receiver.stop();
    }
};

QTEST_GUILESS_MAIN(SimulationFrameDeliveryCheck)
#include "SimulationFrameDeliveryCheck.moc"
