#pragma once

#include "video/HevcFileDecoder.h"

class QProcess;

namespace rm27::video::detail {

// A file or a worker-thread pump writing Annex B to the child's stdin.
HevcDecodeResult decodeHevc(const QString &file, const std::atomic_bool &stopRequested,
                            const HevcFileDecoder::FrameHandler &onFrame,
                            const std::function<void(QProcess &)> &pumpInput = {},
                            const std::function<void(const QString &)> &onDiagnostic = {});

} // namespace rm27::video::detail
