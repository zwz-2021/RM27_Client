import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import RM27.Client 1.0
import "../components"

ScrollView {
  id: root
  objectName: "overviewPage"
  required property ClientViewModel viewModel
  required property QtObject simulationVideo
  contentWidth: availableWidth
  clip: true

  Shortcut {
    sequence: "F6"
    context: Qt.WindowShortcut
    enabled: root.visible && root.viewModel.infantrySeat
    autoRepeat: false
    onActivated: root.viewModel.requestBusinessAction()
  }

  ColumnLayout {
    width: root.availableWidth
    spacing: 16

    InfoCard {
      Layout.fillWidth: true
      heading: root.viewModel.sourceText
      value: root.viewModel.connectionText
      valueObjectName: "connectionValue"
      description: root.viewModel.connectionDetail
    }

    RowLayout {
      Layout.fillWidth: true
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
      Button {
        objectName: "competitionActionButton"
        text: "赛事操作 (F6)"
        visible: root.viewModel.infantrySeat
        onClicked: root.viewModel.requestBusinessAction()
      }
      Label {
        Layout.fillWidth: true
        text: root.viewModel.preview
          ? "内置心跳仅用于界面预览。"
          : "订阅就绪后仍需等待数据；过期和缺失值显示 —。"
        color: "#526078"
        wrapMode: Text.Wrap
      }
    }

    Label {
      Layout.fillWidth: true
      objectName: "actionFeedbackLabel"
      text: root.viewModel.actionFeedback
      visible: root.viewModel.infantrySeat && text.length > 0
      wrapMode: Text.Wrap
    }

    Loader {
      Layout.fillWidth: true
      Layout.preferredHeight: Math.min(root.availableWidth * 9 / 16, root.height * 0.52)
      active: root.simulationVideo !== null && root.viewModel.infantrySeat
      visible: active
      sourceComponent: SimulationVideoPreview { simulationVideo: root.simulationVideo }
    }

    Frame {
      Layout.fillWidth: true
      visible: root.viewModel.personalConfigPath.length > 0
      padding: 12
      ColumnLayout {
        anchors.fill: parent
        RowLayout {
          Layout.fillWidth: true
          Label { text: "接收机器人" }
          ComboBox {
            id: receiverBox
            objectName: "receiverRobotBox"
            Accessible.name: "接收机器人"
            enabled: !root.viewModel.active
            model: root.viewModel.receiverChoices
            textRole: "label"
            valueRole: "id"
            implicitContentWidthPolicy: ComboBox.WidestTextWhenCompleted
            Component.onCompleted: currentIndex = indexOfValue(root.viewModel.configuredRobotId)
            Connections {
              target: root.viewModel
              function onIdentityChanged() {
                receiverBox.currentIndex = receiverBox.indexOfValue(root.viewModel.configuredRobotId)
              }
              function onStateChanged() {
                if (root.viewModel.active)
                  receiverBox.currentIndex = receiverBox.indexOfValue(root.viewModel.configuredRobotId)
              }
            }
          }
          Button {
            objectName: "saveReceiverButton"
            text: "保存步兵只读配置"
            enabled: !root.viewModel.active && receiverBox.currentIndex >= 0
            onClicked: root.viewModel.saveInfantryConfig(receiverBox.currentValue)
          }
        }
        Label {
          Layout.fillWidth: true
          text: (root.viewModel.active ? "停止数据源后可修改 · " : "个人配置 · ") + root.viewModel.personalConfigPath
          textFormat: Text.PlainText
          color: "#526078"
          wrapMode: Text.WrapAnywhere
        }
        Label {
          objectName: "configFeedbackLabel"
          Layout.fillWidth: true
          text: root.viewModel.configFeedback
          textFormat: Text.PlainText
          visible: text.length > 0
          wrapMode: Text.WrapAnywhere
        }
      }
    }

    Label {
      Layout.fillWidth: true
      objectName: "diagnosticLabel"
      Accessible.id: "diagnosticLabel"
      visible: root.viewModel.diagnosticText.length > 0
      text: root.viewModel.diagnosticText
      color: "#b42318"
      wrapMode: Text.WrapAnywhere
    }

    GridLayout {
      Layout.fillWidth: true
      visible: !root.viewModel.preview
      columns: root.availableWidth >= 900 ? 2 : 1
      columnSpacing: 16
      rowSpacing: 16

      InfoCard {
        Layout.fillWidth: true
        Layout.preferredWidth: 1
        heading: "当前机器人血量 · " + root.viewModel.dynamicStatusText
        value: root.viewModel.healthText
        valueObjectName: "healthValue"
        description: root.viewModel.dynamicSummary
      }
      InfoCard {
        Layout.fillWidth: true
        Layout.preferredWidth: 1
        heading: "机器人身份与静态状态"
        value: root.viewModel.robotIdentityText
        valueObjectName: "identityValue"
        description: root.viewModel.staticSummary
      }
      InfoCard {
        Layout.fillWidth: true
        Layout.preferredWidth: 1
        heading: "比赛状态"
        value: root.viewModel.gameText
        valueObjectName: "gameValue"
        description: root.viewModel.gameSummary
      }
      InfoCard {
        Layout.fillWidth: true
        Layout.preferredWidth: 1
        heading: "己方当前经济"
        value: root.viewModel.economyText
        valueObjectName: "economyValue"
        description: root.viewModel.logisticsSummary
      }
    }

    Frame {
      Layout.fillWidth: true
      visible: !root.viewModel.preview
      padding: 20
      ColumnLayout {
        anchors.fill: parent
        spacing: 10
        Label {
          objectName: "moduleStatus"
          Accessible.id: "moduleStatus"
          text: "机器人模块 · " + root.viewModel.moduleStatusText
          font.bold: true
        }
        GridLayout {
          Layout.fillWidth: true
          columns: root.availableWidth >= 900 ? 2 : 1
          columnSpacing: 24
          rowSpacing: 10
          Repeater {
            model: root.viewModel.moduleRows
            delegate: Label {
              required property var modelData
              Layout.fillWidth: true
              Layout.preferredWidth: 1
              objectName: "module_" + modelData.field
              Accessible.id: objectName
              text: modelData.label + "：" + modelData.text
              textFormat: Text.PlainText
              wrapMode: Text.Wrap
              color: modelData.state === "online" || modelData.state === "permission_granted" ? "#067647"
                : (modelData.state === "offline" || modelData.state === "installation_invalid" ? "#b42318"
                  : (modelData.state === "stale" ? "#b45309" : "#526078"))
            }
          }
        }
        Label {
          objectName: "moduleSummary"
          Accessible.id: "moduleSummary"
          Layout.fillWidth: true
          text: root.viewModel.moduleSummary
          color: "#748096"
          wrapMode: Text.Wrap
        }
      }
    }

    InfoCard {
      Layout.fillWidth: true
      visible: !root.viewModel.preview
      heading: "全局血量与剩余累计发弹量"
      description: root.viewModel.unitsSummary
    }

    Frame {
      Layout.fillWidth: true
      visible: !root.viewModel.preview
      padding: 20
      ColumnLayout {
        anchors.fill: parent
        spacing: 10
        Label { text: "逐消息接收状态"; font.bold: true }
        Repeater {
          model: root.viewModel.topicStates
          delegate: RowLayout {
            required property var modelData
            Layout.fillWidth: true
            Label {
              Layout.fillWidth: true
              text: modelData.topic
              wrapMode: Text.WrapAnywhere
              color: "#526078"
            }
            Label {
              objectName: modelData.topic + "Status"
              text: modelData.state
              color: modelData.stale ? "#b45309" : (modelData.received ? "#067647" : "#748096")
            }
          }
        }
        Label {
          Layout.fillWidth: true
          text: root.viewModel.infantrySeat ? "图传 UDP 收包计数可在“运行信息”查看。" : "当前显示六类消息的接收状态。"
          color: "#748096"
          wrapMode: Text.Wrap
        }
      }
    }

    GridLayout {
      Layout.fillWidth: true
      visible: root.viewModel.preview
      columns: root.availableWidth >= 900 ? 2 : 1
      columnSpacing: 16
      rowSpacing: 16
      InfoCard {
        Layout.fillWidth: true
        Layout.preferredWidth: 1
        heading: "演示心跳序号"
        value: root.viewModel.sequenceText
        description: "用于确认内置预览到界面的更新链路。"
      }
      InfoCard {
        Layout.fillWidth: true
        Layout.preferredWidth: 1
        heading: "本次预览运行时间"
        value: root.viewModel.elapsedText
        description: "停止后清空，再次启动从零计时。"
      }
    }
  }
}
