import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RM27.Client 1.0
import "../components"

ScrollView {
  id: root
  required property ClientViewModel viewModel
  contentWidth: availableWidth
  clip: true

  ColumnLayout {
    width: root.availableWidth
    spacing: 16

    InfoCard {
      Layout.fillWidth: true
      heading: "数据源"
      value: root.viewModel.connectionText
      description: root.viewModel.connectionDetail
    }

    RowLayout {
      spacing: 12
      Button {
        objectName: "startButton"
        text: "启动数据源"
        enabled: root.viewModel.canStart
        onClicked: root.viewModel.start()
      }
      Button {
        objectName: "stopButton"
        text: "停止"
        enabled: root.viewModel.active
        onClicked: root.viewModel.stop()
      }
      Label {
        Layout.fillWidth: true
        text: "模拟模式可直接预览数据更新。"
        color: "#526078"
        wrapMode: Text.Wrap
      }
    }

    GridLayout {
      Layout.fillWidth: true
      columns: root.availableWidth >= 800 ? 2 : 1
      columnSpacing: 16
      rowSpacing: 16

      InfoCard {
        Layout.fillWidth: true
        Layout.preferredWidth: 1
        heading: "演示心跳序号"
        value: root.viewModel.sequenceText
        description: "用于确认数据源到界面的更新链路。"
      }
      InfoCard {
        Layout.fillWidth: true
        Layout.preferredWidth: 1
        heading: "本次模拟运行时间"
        value: root.viewModel.elapsedText
        description: "停止后清空，再次启动从零计时。"
      }
    }

    InfoCard {
      Layout.fillWidth: true
      heading: "业务工作区"
      value: "等待接入比赛状态与图传"
      description: "后续在这里添加机器人状态、地图、视频画面与操作面板。当前心跳仅用于本地开发，不代表赛事数据。"
    }
  }
}
