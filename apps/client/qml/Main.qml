import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
  id: root
  width: 960
  height: 600
  minimumWidth: 640
  minimumHeight: 480
  visible: true
  title: "RM27 Client"

  required property string modeText
  property string startupError: ""
  property string logPath: ""

  ColumnLayout {
    anchors.fill: parent
    anchors.margins: 32
    spacing: 16

    Label {
      text: "RM27 Client"
      font.pixelSize: 28
    }
    Label {
      objectName: "modeLabel"
      text: "运行模式：" + root.modeText
      font.pixelSize: 18
    }
    Label {
      objectName: "connectionLabel"
      text: "未连接"
      font.pixelSize: 18
    }
    Label {
      objectName: "startupErrorLabel"
      Layout.fillWidth: true
      visible: root.startupError.length > 0
      text: "启动配置或日志错误：\n" + root.startupError
      color: "#b42318"
      wrapMode: Text.WrapAnywhere
    }
    Item { Layout.fillHeight: true }
    Button {
      objectName: "replayButton"
      text: "回放（未实现）"
      enabled: false
    }
    Label {
      Layout.fillWidth: true
      text: "日志：" + root.logPath
      wrapMode: Text.WrapAnywhere
      font.pixelSize: 12
    }
  }
}
