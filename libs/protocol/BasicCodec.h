#pragma once

#include "domain/BasicData.h"

#include <QByteArray>
#include <QString>
#include <optional>

namespace rm27::protocol {

struct TopicContract {
    const char *name;
    int frequencyHz;
    int maximumQos;
};

const TopicContract *contractFor(const QString &topic);

struct DecodeResult {
    std::optional<domain::BasicMessage> message;
    QString error;
};

struct EncodeResult {
    QString topic;
    QByteArray payload;
    QString error;
};

// No network connection or state merging. Empty optional messages stay empty.
DecodeResult decode(const QString &topic, const QByteArray &payload);
EncodeResult encode(const domain::BasicMessage &message);

} // namespace rm27::protocol
