import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RM27.Client 1.0
import "pages"

ApplicationWindow {
  id: root
  required property ClientViewModel viewModel
  width: 1280
  height: 800
  minimumWidth: 640
  minimumHeight: 480
  visible: true
  title: "RM27 Client"
  color: "#f3f5f9"
  palette.windowText: "#17243b"
  palette.text: "#17243b"
  palette.buttonText: "#17243b"
  palette.highlight: "#2563eb"

  ColumnLayout {
    anchors.fill: parent
    anchors.margins: 24
    spacing: 16

    RowLayout {
      Layout.fillWidth: true
      Label {
        text: "RM27 Client"
        font.pixelSize: 28
        font.bold: true
      }
      Item { Layout.fillWidth: true }
      Label {
        objectName: "modeLabel"
        text: root.viewModel.modeText
        color: "#526078"
      }
    }

    Label {
      Layout.fillWidth: true
      objectName: "startupErrorLabel"
      visible: root.viewModel.startupError.length > 0
      text: "启动配置或日志错误：\n" + root.viewModel.startupError
      color: "#b42318"
      wrapMode: Text.WrapAnywhere
      // 异常路径可能很长，限制占用高度，避免把导航挤出窗口。
      maximumLineCount: 4
      elide: Text.ElideRight
      ToolTip.visible: errorMouse.containsMouse && visible
      ToolTip.text: root.viewModel.startupError
      MouseArea { id: errorMouse; anchors.fill: parent; hoverEnabled: true }
    }

    TabBar {
      id: tabs
      Layout.fillWidth: true
      TabButton { text: "工作台" }
      TabButton { text: "运行信息" }
    }
    StackLayout {
      Layout.fillWidth: true
      Layout.fillHeight: true
      currentIndex: tabs.currentIndex
      OverviewPage { viewModel: root.viewModel }
      DiagnosticsPage { viewModel: root.viewModel }
    }
    Label {
      Layout.fillWidth: true
      text: "开发骨架 · Qt Quick / C++17"
      color: "#748096"
      font.pixelSize: 12
    }
  }
}
