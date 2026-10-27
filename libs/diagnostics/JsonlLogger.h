#pragma once

#include <QFile>
#include <QString>

namespace rm27::diagnostics {

// 简单的单线程 JSONL 日志；由应用层决定日志文件的位置和生命周期。
class JsonlLogger {
public:
    bool open(const QString &path);
    bool write(const QString &level, const QString &event, const QString &detail = {});
    QString errorString() const;

private:
    QFile file_;
    QString error_;
};

} // namespace rm27::diagnostics
