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
      heading: "当前模式与来源"
      value: root.viewModel.modeText
      description: root.viewModel.sourceText + "\n通过启动参数 --config 选择配置文件，更改身份或地址后重新启动客户端。"
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
      heading: "最近诊断"
      description: root.viewModel.diagnosticText.length > 0
        ? root.viewModel.diagnosticText : "暂无诊断。数据接收情况请查看工作台中的逐消息状态。"
    }
  }
}
