#include "transport/UdpVideoReceiver.h"

#include <QUdpSocket>
#include <QtEndian>

namespace rm27::transport {
using video::UdpVideoState;

namespace {

constexpr int PacketsPerTurn = 64;

} // namespace

UdpVideoReceiver::UdpVideoReceiver(QObject *parent)
    : QObject(parent), socket_(new QUdpSocket(this))
{
    continuation_.setSingleShot(true);
    notification_.setSingleShot(true);
    notification_.setInterval(100);
    expiry_.setSingleShot(true);
    expiry_.setTimerType(Qt::PreciseTimer);
    connect(socket_, &QUdpSocket::readyRead, this, &UdpVideoReceiver::drain);
    connect(&continuation_, &QTimer::timeout, this, &UdpVideoReceiver::drain);
    connect(&notification_, &QTimer::timeout, this, &UdpVideoReceiver::statusChanged);
    connect(&expiry_, &QTimer::timeout, this, [this] {
        if (assembler_.expire(sessionClock_.elapsed())) {
            status_.assembly = assembler_.stats();
            if (!notification_.isActive())
                notification_.start();
        }
        scheduleExpiry();
    });
    connect(socket_, &QUdpSocket::errorOccurred, this, [this](QAbstractSocket::SocketError error) {
        if (status_.state == UdpVideoState::Bound && error != QAbstractSocket::TemporaryError)
            fail(UdpVideoState::ReadFailed, socket_->errorString());
    });
}

bool UdpVideoReceiver::start(const QString &bindAddress, quint16 port, bool assembleLocalSimulation)
{
    if (status_.state == UdpVideoState::Bound && status_.bindAddress == bindAddress
        && assembleLocalSimulation_ == assembleLocalSimulation
        && (port == 0 || status_.bindPort == port))
        return true;
    closeSocket();
    status_ = {};
    status_.bindAddress = bindAddress;
    status_.bindPort = port;
    QHostAddress address;
    if (!address.setAddress(bindAddress)) {
        fail(UdpVideoState::BindFailed, QStringLiteral("无效的本地 IP 地址"));
        return false;
    }
    if (!socket_->bind(address, port, QAbstractSocket::DontShareAddress)) {
        fail(UdpVideoState::BindFailed, socket_->errorString());
        return false;
    }
    status_.state = UdpVideoState::Bound;
    status_.bindPort = socket_->localPort();
    assembleLocalSimulation_ = assembleLocalSimulation;
    sessionClock_.start();
    emit statusChanged();
    return true;
}

void UdpVideoReceiver::closeSocket()
{
    status_.state = UdpVideoState::Stopped;
    continuation_.stop();
    notification_.stop();
    expiry_.stop();
    assembleLocalSimulation_ = false;
    assembler_.reset();
    status_.assembly.pendingFrames = 0;
    status_.assembly.bufferedBytes = 0;
    status_.assembly.bufferedFragments = 0;
    socket_->close();
}

void UdpVideoReceiver::fail(UdpVideoState state, QString detail)
{
    closeSocket();
    status_.state = state;
    status_.error = detail;
    emit statusChanged();
}

void UdpVideoReceiver::stop()
{
    if (status_.state == UdpVideoState::Stopped)
        return;
    closeSocket();
    status_ = {};
    emit statusChanged();
}

void UdpVideoReceiver::scheduleExpiry()
{
    const auto deadline = assembler_.nextDeadlineMs();
    if (deadline) {
        const int remaining = static_cast<int>(qMax<qint64>(0, *deadline - sessionClock_.elapsed()));
        if (!expiry_.isActive() || remaining < expiry_.remainingTime())
            expiry_.start(remaining);
    } else {
        expiry_.stop();
    }
}

void UdpVideoReceiver::drain()
{
    if (status_.state != UdpVideoState::Bound)
        return;
    // One extra byte distinguishes a full-size packet from any truncated oversized one.
    char bytes[video::MaxVideoDatagramBytes + 1];
    for (int i = 0; i < PacketsPerTurn && socket_->hasPendingDatagrams(); ++i) {
        QHostAddress sender;
        quint16 senderPort = 0;
        const qint64 length = socket_->readDatagram(bytes, sizeof(bytes), &sender, &senderPort);
        if (length < 0) {
            if (status_.state == UdpVideoState::Bound && socket_->error() != QAbstractSocket::TemporaryError)
                fail(UdpVideoState::ReadFailed, socket_->errorString());
            return;
        }
        if (length < video::VideoHeaderBytes) {
            ++status_.shortPackets;
        } else if (length > video::MaxVideoDatagramBytes) {
            ++status_.oversizedPackets;
        } else {
            const video::UdpVideoHeader header{qFromBigEndian<quint16>(bytes),
                                               qFromBigEndian<quint16>(bytes + 2),
                                               qFromBigEndian<quint32>(bytes + 4)};
            const QString address = sender.toString();
            if (length == video::VideoHeaderBytes) {
                ++status_.emptyPayloadPackets;
            } else if (header.frameBytes < length - video::VideoHeaderBytes) {
                ++status_.inconsistentFramePackets;
            } else {
                ++status_.validPackets;
                status_.lastHeader = header;
                status_.lastSourceAddress = address;
                status_.lastSourcePort = senderPort;
                status_.lastPacketBytes = static_cast<int>(length);
            }
            // The local simulator uses zero-based indices. Official sources only have header diagnostics.
            if (assembleLocalSimulation_ && sender.isLoopback()) {
                const auto frame = assembler_.accept(address, senderPort, header,
                    QByteArrayView(bytes + video::VideoHeaderBytes, length - video::VideoHeaderBytes), sessionClock_.elapsed());
                status_.assembly = assembler_.stats();
                if (frame) {
                    status_.lastFrame = video::UdpFrameInfo{header.frameId, frame->size(), address, senderPort};
                    emit frameAssembled(header.frameId, *frame);
                }
            }
        }
    }
    if (status_.state != UdpVideoState::Bound)
        return;
    scheduleExpiry();
    if (!notification_.isActive())
        notification_.start();
    // Qt may coalesce readyRead signals; drain the rest after other events get a turn.
    if (socket_->hasPendingDatagrams() && !continuation_.isActive())
        continuation_.start(0);
}

} // namespace rm27::transport
