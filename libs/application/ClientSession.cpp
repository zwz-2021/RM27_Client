#include "ClientSession.h"

namespace rm27::application {

ClientSession::ClientSession(IDataSource &source, QObject *parent)
    : QObject(parent), source_(source)
{
    qRegisterMetaType<domain::ClientSnapshot>();
    qRegisterMetaType<domain::ConnectionState>();

    connect(&source_, &IDataSource::connectionChanged, this,
            [this](domain::ConnectionState state, const QString &detail) {
        if (!active_) {
            return;
        }
        connectionState_ = state;
        connectionDetail_ = detail;
        if (state == domain::ConnectionState::Unavailable
            || state == domain::ConnectionState::Disconnected) {
            active_ = false;
            clearSnapshot();
        }
        emit stateChanged();
    });
    connect(&source_, &IDataSource::snapshotReceived, this,
            [this](const domain::ClientSnapshot &snapshot) {
        if (!active_ || connectionState_ != domain::ConnectionState::Connected) {
            return;
        }
        snapshot_ = snapshot;
        hasSnapshot_ = true;
        emit snapshotChanged();
    });
}

ClientSession::~ClientSession()
{
    stop();
}

void ClientSession::start()
{
    if (active_) {
        return;
    }
    clearSnapshot();
    active_ = true;
    connectionState_ = domain::ConnectionState::Connecting;
    connectionDetail_ = QStringLiteral("正在启动数据源……");
    emit stateChanged();
    source_.start();
}

void ClientSession::stop()
{
    if (!active_ && connectionState_ == domain::ConnectionState::Disconnected
        && !hasSnapshot_) {
        return;
    }

    // 先关闭接收入口，避免 stop() 期间的数据回写。
    active_ = false;
    source_.stop();
    clearSnapshot();
    connectionState_ = domain::ConnectionState::Disconnected;
    connectionDetail_ = QStringLiteral("数据源已停止。");
    emit stateChanged();
}

void ClientSession::clearSnapshot()
{
    snapshot_ = {};
    if (hasSnapshot_) {
        hasSnapshot_ = false;
        emit snapshotChanged();
    }
}

} // namespace rm27::application
