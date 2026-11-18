import QtQuick
import QtQuick.Controls
import QtMultimedia

Item {
  id: root
  required property var simulationVideo

  Rectangle {
    objectName: "videoPreviewSurface"
    Accessible.role: Accessible.Graphic
    Accessible.name: "本机模拟录屏"
    anchors.fill: parent
    color: "#111923"

    VideoOutput {
      id: output
      anchors.fill: parent
      fillMode: VideoOutput.PreserveAspectFit
    }
  }

  Binding {
    target: root.simulationVideo
    property: "videoSink"
    value: output.videoSink
  }

  Row {
    anchors.top: parent.top
    anchors.left: parent.left
    anchors.margins: 8
    Label {
      id: caption
      text: "本机模拟录屏"
      padding: 6
      color: "white"
      background: Rectangle { color: "#1e293b" }
    }
    Label {
      objectName: "videoPreviewStatus"
      text: root.simulationVideo.statusText
      width: Math.max(0, Math.min(implicitWidth, root.width - caption.width - 16))
      wrapMode: Text.Wrap
      textFormat: Text.PlainText
      padding: 6
      color: "white"
      background: Rectangle { color: root.simulationVideo.stale ? "#92400e" : "#334155" }
    }
  }
}
