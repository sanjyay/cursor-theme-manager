import QtQuick
import qs.Commons
import "../CursorModel.js" as Model

Item {
  id: root

  property var sizes: Model.SupportedSizes
  property int committedSize: 16
  property bool cursorActive: false

  signal sizeActivated(int size)
  signal decreaseRequested()
  signal increaseRequested()

  readonly property bool canDecrease: Model.canDecreaseSize(committedSize)
  readonly property bool canIncrease: Model.canIncreaseSize(committedSize)

  function decrease() {
    if (canDecrease) {
      var target = Model.prevSize(committedSize)
      decreaseRequested()
      sizeActivated(target)
    }
  }

  function increase() {
    if (canIncrease) {
      var target = Model.nextSize(committedSize)
      increaseRequested()
      sizeActivated(target)
    }
  }

  implicitWidth: row.implicitWidth
  implicitHeight: row.implicitHeight

  Row {
    id: row
    spacing: Style.space(6)

    // Minus Button
    Rectangle {
      id: minusBtn
      width: Style.space(34)
      height: Style.space(34)
      radius: Style.cornerRadius
      color: root.canDecrease
        ? (minusMouse.containsMouse ? Style.hoverFillFor(Color.popups.text, Color.accent) : Style.normalFillFor(Color.popups.text, Color.accent))
        : Style.normalFillFor(Color.popups.text, Color.accent)
      border.color: root.canDecrease
        ? (minusMouse.containsMouse ? Style.hoverBorderFor(Color.popups.text, Color.accent) : Style.normalBorderFor(Color.popups.text, Color.accent))
        : Style.normalBorderFor(Color.popups.text, Color.accent)
      border.width: root.canDecrease && minusMouse.containsMouse ? Style.hoverBorderWidth : Style.normalBorderWidth

      Accessible.name: "Decrease cursor size"
      Accessible.role: Accessible.Button

      Text {
        anchors.centerIn: parent
        text: "−"
        textFormat: Text.PlainText
        color: root.canDecrease ? Color.popups.text : Color.muted
        opacity: root.canDecrease ? 1.0 : 0.35
        font.family: Style.font.family
        font.pixelSize: Style.font.title
        font.bold: true
      }

      MouseArea {
        id: minusMouse
        anchors.fill: parent
        enabled: root.canDecrease
        hoverEnabled: true
        cursorShape: root.canDecrease ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.decrease()
      }
    }

    // Read-only numeric display
    Rectangle {
      id: valueDisplay
      width: Style.space(52)
      height: Style.space(34)
      radius: Style.cornerRadius
      color: root.cursorActive
        ? Style.selectedFillFor(Color.popups.text, Color.accent)
        : Style.normalFillFor(Color.popups.text, Color.accent)
      border.color: root.cursorActive
        ? Style.selectedBorderFor(Color.popups.text, Color.accent)
        : Style.normalBorderFor(Color.popups.text, Color.accent)
      border.width: root.cursorActive ? Math.max(1, Style.selectedBorderWidth) : Style.normalBorderWidth

      Accessible.name: "Cursor size " + root.committedSize
      Accessible.role: Accessible.StaticText

      Text {
        anchors.centerIn: parent
        text: String(root.committedSize)
        textFormat: Text.PlainText
        color: Color.popups.text
        font.family: Style.font.family
        font.pixelSize: Style.font.body
        font.bold: true
      }
    }

    // Plus Button
    Rectangle {
      id: plusBtn
      width: Style.space(34)
      height: Style.space(34)
      radius: Style.cornerRadius
      color: root.canIncrease
        ? (plusMouse.containsMouse ? Style.hoverFillFor(Color.popups.text, Color.accent) : Style.normalFillFor(Color.popups.text, Color.accent))
        : Style.normalFillFor(Color.popups.text, Color.accent)
      border.color: root.canIncrease
        ? (plusMouse.containsMouse ? Style.hoverBorderFor(Color.popups.text, Color.accent) : Style.normalBorderFor(Color.popups.text, Color.accent))
        : Style.normalBorderFor(Color.popups.text, Color.accent)
      border.width: root.canIncrease && plusMouse.containsMouse ? Style.hoverBorderWidth : Style.normalBorderWidth

      Accessible.name: "Increase cursor size"
      Accessible.role: Accessible.Button

      Text {
        anchors.centerIn: parent
        text: "+"
        textFormat: Text.PlainText
        color: root.canIncrease ? Color.popups.text : Color.muted
        opacity: root.canIncrease ? 1.0 : 0.35
        font.family: Style.font.family
        font.pixelSize: Style.font.title
        font.bold: true
      }

      MouseArea {
        id: plusMouse
        anchors.fill: parent
        enabled: root.canIncrease
        hoverEnabled: true
        cursorShape: root.canIncrease ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.increase()
      }
    }
  }
}
