#include "transport/UdpVideoReceiver.h"

#include <QUdpSocket>
#include <QtEndian>

namespace rm27::transport {
using video::UdpVideoState;

namespace {

// RM27 communication protocol, chapter 2, PDF p.47.
constexpr int HeaderBytes = 8;
constexpr int MaxPacketBytes = 1400;
constexpr int PacketsPerTurn = 64;

} // namespace

UdpVideoReceiver::UdpVideoReceiver(QObject *parent)
    : QObject(parent), socket_(new QUdpSocket(this))
{
    continuation_.setSingleShot(true);
    notification_.setSingleShot(true);
    notification_.setInterval(100);
    connect(socket_, &QUdpSocket::readyRead, this, &UdpVideoReceiver::drain);
    connect(&continuation_, &QTimer::timeout, this, &UdpVideoReceiver::drain);
    connect(&notification_, &QTimer::timeout, this, &UdpVideoReceiver::statusChanged);
    connect(socket_, &QUdpSocket::errorOccurred, this, [this](QAbstractSocket::SocketError error) {
        if (status_.state == UdpVideoState::Bound && error != QAbstractSocket::TemporaryError)
            fail(UdpVideoState::ReadFailed, socket_->errorString());
    });
}

bool UdpVideoReceiver::start(const QString &bindAddress, quint16 port)
{
    if (status_.state == UdpVideoState::Bound && status_.bindAddress == bindAddress
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
    emit statusChanged();
    return true;
}

void UdpVideoReceiver::closeSocket()
{
    status_.state = UdpVideoState::Stopped;
    continuation_.stop();
    notification_.stop();
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

void UdpVideoReceiver::drain()
{
    if (status_.state != UdpVideoState::Bound)
        return;
    // One extra byte distinguishes a full-size packet from any truncated oversized one.
    char bytes[MaxPacketBytes + 1];
    for (int i = 0; i < PacketsPerTurn && socket_->hasPendingDatagrams(); ++i) {
        QHostAddress sender;
        quint16 senderPort = 0;
        const qint64 length = socket_->readDatagram(bytes, sizeof(bytes), &sender, &senderPort);
        if (length < 0) {
            if (status_.state == UdpVideoState::Bound && socket_->error() != QAbstractSocket::TemporaryError)
                fail(UdpVideoState::ReadFailed, socket_->errorString());
            return;
        }
        if (length < HeaderBytes) {
            ++status_.shortPackets;
        } else if (length > MaxPacketBytes) {
            ++status_.oversizedPackets;
        } else if (length == HeaderBytes) {
            ++status_.emptyPayloadPackets;
        } else {
            const video::UdpVideoHeader header{qFromBigEndian<quint16>(bytes),
                                               qFromBigEndian<quint16>(bytes + 2),
                                               qFromBigEndian<quint32>(bytes + 4)};
            if (header.frameBytes < length - HeaderBytes) {
                ++status_.inconsistentFramePackets;
            } else {
                ++status_.validPackets;
                status_.lastHeader = header;
                status_.lastSourceAddress = sender.toString();
                status_.lastSourcePort = senderPort;
                status_.lastPacketBytes = static_cast<int>(length);
            }
        }
    }
    if (!notification_.isActive())
        notification_.start();
    // Qt may coalesce readyRead signals; drain the rest after other events get a turn.
    if (socket_->hasPendingDatagrams() && !continuation_.isActive())
        continuation_.start(0);
}

} // namespace rm27::transport
