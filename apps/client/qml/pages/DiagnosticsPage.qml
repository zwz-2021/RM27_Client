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

    Frame {
      Layout.fillWidth: true
      visible: root.viewModel.infantrySeat
      padding: 20
      ColumnLayout {
        anchors.fill: parent
        spacing: 8
        Label { text: "图传 UDP 收包"; font.bold: true }
        Label {
          objectName: "udpBindingLabel"
          Layout.fillWidth: true
          text: root.viewModel.udpBindingText
          wrapMode: Text.WrapAnywhere
        }
        Label {
          objectName: "udpCountersLabel"
          Layout.fillWidth: true
          text: root.viewModel.udpCountersText
          wrapMode: Text.Wrap
        }
        Label {
          objectName: "udpHeaderLabel"
          Layout.fillWidth: true
          text: root.viewModel.udpHeaderText
          wrapMode: Text.WrapAnywhere
        }
        Label {
          objectName: "udpAssemblyLabel"
          Layout.fillWidth: true
          text: root.viewModel.udpAssemblyText
          wrapMode: Text.Wrap
        }
        Label {
          objectName: "udpLastFrameLabel"
          Layout.fillWidth: true
          text: root.viewModel.udpLastFrameText
          visible: text.length > 0
          wrapMode: Text.WrapAnywhere
        }
        Label {
          objectName: "videoDecodeLabel"
          Layout.fillWidth: true
          text: root.viewModel.videoDecodeText
          visible: text.length > 0
          wrapMode: Text.WrapAnywhere
        }
      }
    }
    InfoCard {
      Layout.fillWidth: true
      heading: "当前模式与来源"
      value: root.viewModel.modeText
      description: root.viewModel.sourceText + (root.viewModel.preview || root.viewModel.startupError.length > 0 ? ""
        : (root.viewModel.personalConfigPath.length > 0
          ? "\n可在工作台停止数据源后更改接收机器人，并保存为步兵只读席位。"
          : "\n如需保存步兵只读配置，请复制配置示例到个人 JSON 文件，并通过 --config 打开副本。"))
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
