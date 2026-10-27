#include "ClientApplication.h"

#include <QGuiApplication>

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    app.setOrganizationName(QStringLiteral("RM27"));
    app.setApplicationName(QStringLiteral("RM27_Client"));
    app.setApplicationVersion(QStringLiteral(RM27_VERSION));
    return rm27::client::ClientApplication::run(app);
}
