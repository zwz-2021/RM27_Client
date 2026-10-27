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
      heading: "当前模式"
      value: root.viewModel.modeText
      description: "通过启动参数 --config 选择配置文件，更改配置后重新启动客户端。"
    }
    Frame {
      Layout.fillWidth: true
      padding: 20
      ColumnLayout {
        anchors.fill: parent
        spacing: 12
        Label { text: "本次运行日志"; font.bold: true }
        TextArea {
          Layout.fillWidth: true
          text: root.viewModel.logPath
          readOnly: true
          selectByMouse: true
          wrapMode: TextEdit.WrapAnywhere
        }
        Label {
          Layout.fillWidth: true
          text: "JSONL 记录启动、数据源状态变化和退出，每次启动使用独立文件。"
          color: "#526078"
          wrapMode: Text.Wrap
        }
      }
    }
    InfoCard {
      Layout.fillWidth: true
      heading: "扩展入口"
      description: "比赛状态：libs/domain\n通信接入：libs/transport 与 libs/protocol\n视频链路：libs/video\n界面数据：libs/presentation\n页面与组件：apps/client/qml"
    }
  }
}
