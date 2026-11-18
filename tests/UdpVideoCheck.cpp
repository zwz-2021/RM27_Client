#include "transport/UdpVideoReceiver.h"

#include <QSignalSpy>
#include <QTest>
#include <QUdpSocket>

using rm27::transport::UdpVideoReceiver;
using rm27::video::UdpVideoState;

class UdpVideoCheck final : public QObject {
    Q_OBJECT
private slots:
    void wireSamples();
    void exclusiveBindAndRestart();
    void burst();
    void simulationKeyframeBurst();
    void assembleSimulationBytes();
    void assemblySessionBoundary();
};

void UdpVideoCheck::wireSamples()
{
    UdpVideoReceiver receiver;
    const auto &s = receiver.status();
    QVERIFY(receiver.start(QStringLiteral("127.0.0.1"), 0));
    QVERIFY(s.state == UdpVideoState::Bound && s.bindPort != 0 && s.error.isEmpty() && !s.lastHeader);
    QSignalSpy changes(&receiver, &UdpVideoReceiver::statusChanged);
    QUdpSocket sender;
    const auto send = [&](const QByteArray &packet) {
        QCOMPARE(sender.writeDatagram(packet, QHostAddress::LocalHost, s.bindPort), packet.size());
    };

    for (int size = 0; size < 8; ++size)
        send(QByteArray(size, 'x'));
    send(QByteArray::fromHex("ffff000000000001"));      // complete header, no stream data
    send(QByteArray::fromHex("0001000100000001aabb"));  // two bytes in a one-byte frame
    send(QByteArray(1401, 'x'));
    send(QByteArray(16384, 'x'));                      // truncated at the read boundary
    QTRY_COMPARE(s.droppedPackets(), 12ULL);
    QCOMPARE(s.shortPackets, 8ULL);
    QCOMPARE(s.oversizedPackets, 2ULL);
    QCOMPARE(s.emptyPayloadPackets, 1ULL);
    QCOMPARE(s.inconsistentFramePackets, 1ULL);
    QVERIFY(!s.lastHeader && !s.validPackets && !s.lastValidPacketAt.isValid());

    // Literal network bytes independent of the simulator. An untrusted frame length
    // is reported verbatim and must never cause an allocation at the header stage.
    send(QByteArray::fromHex("ffff0102f1020304") + QByteArray(1392, 'a'));
    QTRY_COMPARE(s.validPackets, 1ULL);
    QVERIFY(s.lastHeader);
    QCOMPARE(s.lastHeader->frameId, 65535);
    QCOMPARE(s.lastHeader->fragmentIndex, 0x0102);
    QCOMPARE(s.lastHeader->frameBytes, 0xf1020304U);
    QCOMPARE(s.lastSourceAddress, QStringLiteral("127.0.0.1"));
    QCOMPARE(s.lastSourcePort, sender.localPort());
    QCOMPARE(s.lastPacketBytes, 1400);
    const auto firstPacketAt = s.lastValidPacketAt;
    QVERIFY(firstPacketAt.isValid());
    QTRY_VERIFY(firstPacketAt.elapsed() >= 1);
    send(QByteArray(3, 'x'));
    QTRY_COMPARE(s.shortPackets, 9ULL);
    QVERIFY(s.lastValidPacketAt == firstPacketAt);
    send(QByteArray::fromHex("0000000000000001ab"));
    QTRY_COMPARE(s.validPackets, 2ULL);
    QVERIFY(firstPacketAt.msecsTo(s.lastValidPacketAt) > 0);
    QCOMPARE(s.lastHeader->frameId, 0);
    QCOMPARE(s.lastHeader->fragmentIndex, 0);
    QCOMPARE(s.lastHeader->frameBytes, 1U);
    QCOMPARE(s.lastPacketBytes, 9);
    QTRY_VERIFY(!changes.isEmpty());
}

void UdpVideoCheck::exclusiveBindAndRestart()
{
    const QString address = QStringLiteral("127.0.0.1");
    QUdpSocket holder;
    UdpVideoReceiver receiver;
    const auto &s = receiver.status();
    QVERIFY(!receiver.start(QStringLiteral("invalid"), 3334));
    QVERIFY(s.state == UdpVideoState::BindFailed && !s.error.isEmpty());
    QVERIFY(holder.bind(QHostAddress::LocalHost, 0, QAbstractSocket::DontShareAddress));
    const quint16 port = holder.localPort();
    QVERIFY(!receiver.start(address, port));
    QVERIFY(s.state == UdpVideoState::BindFailed && !s.error.isEmpty());
    QCOMPARE(s.bindPort, port);
    holder.close();
    QVERIFY(receiver.start(address, port));
    QVERIFY(s.state == UdpVideoState::Bound && s.error.isEmpty());
    QUdpSocket sender;
    const QByteArray one = QByteArray::fromHex("3456000100000001ab");
    QCOMPARE(sender.writeDatagram(one, QHostAddress::LocalHost, port), one.size());
    QTRY_COMPARE(s.validPackets, 1ULL);
    QVERIFY(receiver.start(address, port));
    QCOMPARE(s.validPackets, 1ULL);
    QCOMPARE(sender.writeDatagram(one, QHostAddress::LocalHost, port), one.size());
    receiver.stop(); // a datagram is still queued in the old socket
    receiver.stop();
    QVERIFY(s.state == UdpVideoState::Stopped && !s.lastHeader && s.lastSourceAddress.isEmpty() && !s.validPackets);
    QVERIFY(!s.lastValidPacketAt.isValid());
    QVERIFY(holder.bind(QHostAddress::LocalHost, port, QAbstractSocket::DontShareAddress));
    holder.close();
    QVERIFY(receiver.start(address, port));
    QVERIFY(!s.lastValidPacketAt.isValid());
    QCOMPARE(sender.writeDatagram(one, QHostAddress::LocalHost, port), one.size());
    QTRY_COMPARE(s.validPackets, 1ULL);
    QCOMPARE(s.droppedPackets(), 0ULL);
    QCOMPARE(s.lastHeader->frameId, 0x3456);
}

void UdpVideoCheck::burst()
{
    UdpVideoReceiver receiver;
    QVERIFY(receiver.start(QStringLiteral("127.0.0.1"), 0));
    QSignalSpy changes(&receiver, &UdpVideoReceiver::statusChanged);
    QUdpSocket sender;
    const QByteArray one = QByteArray::fromHex("0001000100000001ab");
    for (int i = 0; i < 96; ++i)
        QCOMPARE(sender.writeDatagram(one, QHostAddress::LocalHost, receiver.status().bindPort), one.size());
    QTRY_COMPARE(receiver.status().validPackets, 96ULL);
    QTRY_VERIFY(!changes.isEmpty());
    QVERIFY(changes.count() < 96);
}

void UdpVideoCheck::simulationKeyframeBurst()
{
    UdpVideoReceiver receiver;
    const QString address = QStringLiteral("127.0.0.1");
    const auto &status = receiver.status();
    QSignalSpy frames(&receiver, &UdpVideoReceiver::frameAssembled);
    QUdpSocket sender;
    quint16 port = 0;
    for (int session = 0; session < 2; ++session) {
        QVERIFY(receiver.start(address, port, true));
        port = status.bindPort;
        QVERIFY(status.simulationReceiveBufferBytes.value_or(0) > 0);

        // The recording's 202257-byte keyframe takes 145 full fragments plus
        // a 417-byte tail. Do not pump GUI events until the entire burst is sent.
        QByteArray expected;
        for (int index = 0; index < 146; ++index) {
            const QByteArray payload(index == 145 ? 417 : 1392, static_cast<char>(index + session));
            QByteArray datagram = QByteArray::fromHex("1234 0000 00031611");
            datagram[3] = static_cast<char>(index);
            datagram += payload;
            expected += payload;
            QCOMPARE(sender.writeDatagram(datagram, QHostAddress::LocalHost, port), datagram.size());
        }
        QTRY_COMPARE(frames.size(), 1);
        QCOMPARE(frames.takeFirst().at(1).toByteArray(), expected);
        QCOMPARE(status.validPackets, 146ULL);
        QCOMPARE(status.assembly.droppedFrames(), 0ULL);
        receiver.stop();
        QVERIFY(!status.simulationReceiveBufferBytes);
    }
}

void UdpVideoCheck::assembleSimulationBytes()
{
    UdpVideoReceiver receiver;
    QVERIFY(receiver.start(QStringLiteral("127.0.0.1"), 0, true));
    QSignalSpy frames(&receiver, &UdpVideoReceiver::frameAssembled);
    const auto &status = receiver.status();
    QUdpSocket first;
    QUdpSocket second;
    const auto send = [&](QUdpSocket &socket, const char *hex) {
        const auto bytes = QByteArray::fromHex(hex);
        QCOMPARE(socket.writeDatagram(bytes, QHostAddress::LocalHost, status.bindPort), bytes.size());
    };

    // Two independent senders reuse a frame ID. Literal payloads include a zero
    // and a high bit, so a string conversion or a mix of sources is detectable.
    send(first,  "ffff 0001 00000004 00ff");
    send(first,  "ffff 0001 00000004 00ff");
    send(second, "ffff 0000 00000002 11");
    send(first,  "ffff 0000 00000004 abcd");
    QTRY_COMPARE(frames.count(), 1);
    QCOMPARE(frames.at(0).at(0).toUInt(), 65535U);
    QCOMPARE(frames.at(0).at(1).toByteArray(), QByteArray::fromHex("abcd00ff"));
    QCOMPARE(frames.at(0).at(2).toString(), QStringLiteral("127.0.0.1"));
    QCOMPARE(frames.at(0).at(3).toUInt(), first.localPort());
    send(second, "ffff 0001 00000002 22");
    QTRY_COMPARE(frames.count(), 2);
    QCOMPARE(frames.at(1).at(0).toUInt(), 65535U);
    QCOMPARE(frames.at(1).at(1).toByteArray(), QByteArray::fromHex("1122"));
    QCOMPARE(frames.at(1).at(3).toUInt(), second.localPort());
    send(first,  "0000 0000 00000001 7e");
    QTRY_COMPARE(frames.count(), 3);
    QCOMPARE(frames.at(2).at(0).toUInt(), 0U);
    QCOMPARE(frames.at(2).at(1).toByteArray(), QByteArray::fromHex("7e"));
    QCOMPARE(status.assembly.completedFrames, 3ULL);
    QCOMPARE(status.assembly.duplicateFragments, 1ULL);

    send(first, "000a 0000 00000002 31");
    send(first, "000a 0001 00000001 3233"); // invalid at the header stage, poisons the pending frame
    send(first, "000a 0001 00000002 32");
    QTRY_COMPARE(status.inconsistentFramePackets, 1ULL);
    QCOMPARE(status.assembly.conflictFrames, 1ULL);
    send(first, "000b 0000 00000002 41");
    send(first, "000b 0001 00000005"); // intact but contradictory header, empty fragment
    send(first, "000b 0001 00000002 42");
    QTRY_COMPARE(status.assembly.ignoredLateFragments, 2ULL);
    QCOMPARE(status.emptyPayloadPackets, 1ULL);
    QCOMPARE(status.assembly.conflictFrames, 2ULL);
    QCOMPARE(status.assembly.pendingFrames, 0);
    QCOMPARE(frames.size(), 3);
}

void UdpVideoCheck::assemblySessionBoundary()
{
    UdpVideoReceiver receiver;
    QUdpSocket sender;
    QSignalSpy frames(&receiver, &UdpVideoReceiver::frameAssembled);
    const auto &status = receiver.status();
    const QString address = QStringLiteral("127.0.0.1");
    const auto send = [&](const char *hex) {
        const auto bytes = QByteArray::fromHex(hex);
        QCOMPARE(sender.writeDatagram(bytes, QHostAddress::LocalHost, status.bindPort), bytes.size());
    };

    QVERIFY(receiver.start(address, 0)); // header-only reception
    QVERIFY(!status.simulationReceiveBufferBytes);
    const quint16 port = status.bindPort;
    send("0000 0000 00000001 01");
    QTRY_COMPARE(status.validPackets, 1ULL);
    QCOMPARE(frames.size(), 0);
    QVERIFY(receiver.start(address, port, true));
    send("0010 0000 00000002 aa");
    QTRY_COMPARE(status.assembly.pendingFrames, 1);
    receiver.stop();
    QCOMPARE(status.assembly.pendingFrames, 0);
    QVERIFY(receiver.start(address, port, true));
    send("0010 0001 00000002 bb");
    QTRY_COMPARE(status.assembly.timeoutFrames, 1ULL); // no further incoming packets
    QCOMPARE(status.assembly.bufferedBytes, 0);
    QCOMPARE(frames.size(), 0);
}

QTEST_GUILESS_MAIN(UdpVideoCheck)
#include "UdpVideoCheck.moc"
