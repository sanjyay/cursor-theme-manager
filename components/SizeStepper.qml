import QtQuick
import QtQuick.Controls
import qs.Commons
import "../CursorModel.js" as Model

Row {
  id: root
  property int committedSize: 16
  property bool cursorActive: false
  signal sizeActivated(int size)

  spacing: Style.space(12)

  readonly property var supportedSizes: Model.SupportedSizes
  readonly property int currentIndex: {
    var idx = supportedSizes.indexOf(root.committedSize)
    return idx !== -1 ? idx : 0
  }

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
    spacing: Style.space(8)

    // Decrement Button [-]
    Rectangle {
      id: decBtn
      readonly property bool canDec: Model.canDecreaseSize(root.committedSize)
      anchors.verticalCenter: parent.verticalCenter
      width: Style.space(32)
      height: Style.space(30)
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

    // Interactive Slider Track
    Item {
      id: sliderTrackContainer
      anchors.verticalCenter: parent.verticalCenter
      width: Style.space(140)
      height: Style.space(30)

      // Background groove
      Rectangle {
        id: trackGroove
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.right: parent.right
        height: Style.space(4)
        radius: height / 2
        color: Util.alpha(Color.popups.text, 0.15)

        // Filled active track portion
        Rectangle {
          anchors.left: parent.left
          anchors.top: parent.top
          anchors.bottom: parent.bottom
          width: handle.x + handle.width / 2
          radius: height / 2
          color: Color.accent
        }
      }

      // Slider Handle
      Rectangle {
        id: handle
        anchors.verticalCenter: parent.verticalCenter
        x: {
          var maxIdx = Math.max(1, root.supportedSizes.length - 1)
          var frac = Math.max(0, Math.min(1, root.currentIndex / maxIdx))
          return Math.round(frac * (sliderTrackContainer.width - width))
        }
        width: Style.space(14)
        height: Style.space(14)
        radius: width / 2
        color: Color.accent
        border.color: Color.popups.background
        border.width: 2

        Behavior on x {
          enabled: !trackMouse.drag.active
          NumberAnimation { duration: 90; easing.type: Easing.OutQuad }
        }
      }

      MouseArea {
        id: trackMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor

        function updateFromPosition(mouseX) {
          var maxIdx = root.supportedSizes.length - 1
          var clamped = Math.max(0, Math.min(sliderTrackContainer.width, mouseX))
          var frac = clamped / sliderTrackContainer.width
          var targetIdx = Math.round(frac * maxIdx)
          targetIdx = Math.max(0, Math.min(maxIdx, targetIdx))
          var targetSize = root.supportedSizes[targetIdx]
          if (targetSize !== root.committedSize) {
            root.sizeActivated(targetSize)
          }
        }

        onClicked: function(mouse) {
          updateFromPosition(mouse.x)
        }

        onPositionChanged: function(mouse) {
          if (pressed) {
            updateFromPosition(mouse.x)
          }
        }
      }
    }

    // Increment Button [+]
    Rectangle {
      id: incBtn
      readonly property bool canInc: Model.canIncreaseSize(root.committedSize)
      anchors.verticalCenter: parent.verticalCenter
      width: Style.space(32)
      height: Style.space(30)
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

    // Size Display Badge
    Rectangle {
      id: sizeBadge
      anchors.verticalCenter: parent.verticalCenter
      width: Style.space(72)
      height: Style.space(30)
      radius: Style.cornerRadius - 2
      color: root.cursorActive ? Style.selectedFillFor(Color.popups.text, Color.accent) : Util.alpha(Color.popups.text, 0.08)
      border.color: root.cursorActive ? Color.accent : Util.alpha(Color.popups.text, 0.18)
      border.width: 1

      Text {
        anchors.centerIn: parent
        text: root.committedSize + " px"
        color: Color.popups.text
        font.family: Style.font.family
        font.pixelSize: Style.font.bodySmall
        font.bold: true
      }
    }
  }
}
