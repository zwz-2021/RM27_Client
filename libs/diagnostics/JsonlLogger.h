#pragma once

#include <QFile>
#include <QString>

namespace rm27::diagnostics {

// Startup/shutdown only. Rotation and diagnostic export belong to T26.
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

