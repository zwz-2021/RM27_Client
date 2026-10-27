#pragma once

#include "application/IDataSource.h"

#include <QElapsedTimer>
#include <QTimer>

namespace rm27::transport {

// 仅用于离线预览界面；与独立 simulator/ 进程没有通信关系。
class MockDataSource final : public application::IDataSource {
    Q_OBJECT

public:
    explicit MockDataSource(int intervalMs, QObject *parent = nullptr);

    void start() override;
    void stop() override;

private:
    void publishSnapshot();

    QTimer timer_;
    QElapsedTimer elapsed_;
    std::uint64_t sequence_ = 0;
};

} // namespace rm27::transport
