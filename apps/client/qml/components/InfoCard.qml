import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Frame {
  id: root
  required property string heading
  property string value: ""
  property string description: ""
  padding: 20

  background: Rectangle {
    color: "#ffffff"
    radius: 8
    border.color: "#dde3ec"
  }

  ColumnLayout {
    anchors.fill: parent
    spacing: 12
    Label {
      text: root.heading
      color: "#526078"
      font.pixelSize: 14
    }
    Label {
      Layout.fillWidth: true
      visible: root.value.length > 0
      text: root.value
      color: "#17243b"
      font.pixelSize: 24
      font.bold: true
      wrapMode: Text.Wrap
    }
    Label {
      Layout.fillWidth: true
      text: root.description
      color: "#526078"
      wrapMode: Text.Wrap
    }
  }
}
