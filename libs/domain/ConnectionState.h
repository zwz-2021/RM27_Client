#pragma once

namespace rm27::domain {

enum class ConnectionState { Disconnected, Connecting, Subscribing, Connected, RetryWaiting, Unavailable };

} // namespace rm27::domain
