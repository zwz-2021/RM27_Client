#include "MockDataSource.h"

#include <limits>

namespace rm27::transport {

MockDataSource::MockDataSource(int intervalMs, QObject *parent)
    : IDataSource(parent), timer_(this)
{
    timer_.setInterval(qMax(1, intervalMs));
    connect(&timer_, &QTimer::timeout, this, &MockDataSource::publishSnapshot);
}

void MockDataSource::start()
{
    if (timer_.isActive()) {
        return;
    }
    sequence_ = 0;
    elapsed_.start();
    timer_.start();
    emit connectionChanged(domain::ConnectionState::Connected,
                           QStringLiteral("内置模拟预览已启动；数据为演示心跳，未连接赛事设备。"));
    publishSnapshot();
}

void MockDataSource::stop()
{
    if (!timer_.isActive()) {
        return;
    }
    timer_.stop();
    elapsed_.invalidate();
    sequence_ = 0;
    emit connectionChanged(domain::ConnectionState::Disconnected,
                           QStringLiteral("内置模拟预览已停止。"));
}

void MockDataSource::publishSnapshot()
{
    if (!timer_.isActive()) {
        return;
    }
    domain::ClientSnapshot snapshot;
    snapshot.sequence = ++sequence_;
    snapshot.elapsedSeconds = static_cast<int>(qMin<qint64>(
        elapsed_.elapsed() / 1000, std::numeric_limits<int>::max()));
    emit snapshotReceived(snapshot);
}

} // namespace rm27::transport
