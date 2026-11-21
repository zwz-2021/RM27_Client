#pragma once

#include "domain/RunMode.h"
#include <QJsonObject>
#include <QString>
#include <optional>

namespace rm27::application { class ClientSession; }
namespace rm27::video { struct UdpVideoStatus; }

namespace rm27::client {

inline constexpr qsizetype MaxLinkSnapshotBytes = 32 * 1024;

// Capture on the session's owner thread. No payloads, addresses, paths or free
// text diagnostics enter this document. Rates are sampled by their owners.
QJsonObject captureLinkDiagnostics(const application::ClientSession &session,
    std::optional<domain::RunMode> mode, const video::UdpVideoStatus &udp,
    const QJsonObject &decode);

struct SnapshotSaveResult {
    bool success = false;
    QString path;
    QString error;
};

// Pure value inputs permit writing on a worker, without retaining live sources.
// The caller reuses one destination; a failed write never replaces the old file.
SnapshotSaveResult saveLinkDiagnostics(const QString &path, const QJsonObject &snapshot);

} // namespace rm27::client
