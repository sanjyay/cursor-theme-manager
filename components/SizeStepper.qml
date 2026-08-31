import QtQuick
import qs.Commons
import "../CursorModel.js" as Model

Row {
  id: root
  property int committedSize: 16
  property bool cursorActive: false
  signal sizeActivated(int size)

  spacing: Style.space(12)

  Text {
    anchors.verticalCenter: parent.verticalCenter
    text: "Cursor size:"
    color: Color.popups.text
    font.family: Style.font.family
    font.pixelSize: Style.font.body
    font.bold: true
  }

  Row {
    anchors.verticalCenter: parent.verticalCenter
    spacing: Style.space(6)

    // Decrement Button [-]
    Rectangle {
      id: decBtn
      readonly property bool canDec: Model.canDecreaseSize(root.committedSize)
      width: Style.space(36)
      height: Style.space(32)
      radius: Style.cornerRadius - 2
      color: decMouse.containsMouse && canDec ? Style.hoverFillFor(Color.popups.text, Color.accent) : Style.normalFillFor(Color.popups.text, Color.accent)
      border.color: decMouse.containsMouse && canDec ? Style.hoverBorderFor(Color.popups.text, Color.accent) : Style.normalBorderFor(Color.popups.text, Color.accent)
      border.width: 1
      opacity: canDec ? 1.0 : 0.4

      Text {
        anchors.centerIn: parent
        text: "−"
        color: decBtn.canDec ? Color.popups.text : Color.muted
        font.family: Style.font.family
        font.pixelSize: Style.font.title
        font.bold: true
      }

      MouseArea {
        id: decMouse
        anchors.fill: parent
        enabled: decBtn.canDec
        hoverEnabled: true
        cursorShape: decBtn.canDec ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: {
          var prev = Model.prevSize(root.committedSize)
          root.sizeActivated(prev)
        }
      }
    }

    // Size Display Badge
    Rectangle {
      id: sizeBadge
      width: Style.space(80)
      height: Style.space(32)
      radius: Style.cornerRadius - 2
      color: root.cursorActive ? Style.selectedFillFor(Color.popups.text, Color.accent) : Util.alpha(Color.popups.text, 0.08)
      border.color: root.cursorActive ? Color.accent : Util.alpha(Color.popups.text, 0.18)
      border.width: 1

      Text {
        anchors.centerIn: parent
        text: root.committedSize + " px"
        color: Color.popups.text
        font.family: Style.font.family
        font.pixelSize: Style.font.body
        font.bold: true
      }
    }

    // Increment Button [+]
    Rectangle {
      id: incBtn
      readonly property bool canInc: Model.canIncreaseSize(root.committedSize)
      width: Style.space(36)
      height: Style.space(32)
      radius: Style.cornerRadius - 2
      color: incMouse.containsMouse && canInc ? Style.hoverFillFor(Color.popups.text, Color.accent) : Style.normalFillFor(Color.popups.text, Color.accent)
      border.color: incMouse.containsMouse && canInc ? Style.hoverBorderFor(Color.popups.text, Color.accent) : Style.normalBorderFor(Color.popups.text, Color.accent)
      border.width: 1
      opacity: canInc ? 1.0 : 0.4

      Text {
        anchors.centerIn: parent
        text: "+"
        color: incBtn.canInc ? Color.popups.text : Color.muted
        font.family: Style.font.family
        font.pixelSize: Style.font.title
        font.bold: true
      }

      MouseArea {
        id: incMouse
        anchors.fill: parent
        enabled: incBtn.canInc
        hoverEnabled: true
        cursorShape: incBtn.canInc ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: {
          var next = Model.nextSize(root.committedSize)
          root.sizeActivated(next)
        }
      }
    }
  }
}
