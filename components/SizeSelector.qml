import QtQuick
import qs.Commons

Item {
  id: root
  property var sizes: []
  property int committedSize: 24
  property int cursorIndex: 0
  property bool cursorActive: false
  signal sizeActivated(int size, int index)
  signal sizeHovered(int size, int index, bool active)

  implicitHeight: row.implicitHeight

  Row {
    id: row
    width: parent.width
    spacing: Style.space(7)

    Repeater {
      model: root.sizes
      delegate: Rectangle {
        required property int index
        required property var modelData
        readonly property bool chosen: Number(modelData) === root.committedSize
        readonly property bool hot: mouse.containsMouse || (root.cursorActive && index === root.cursorIndex)
        width: (row.width - row.spacing * (root.sizes.length - 1)) / root.sizes.length
        height: Style.space(34)
        radius: Style.cornerRadius
        color: chosen ? Style.selectedFillFor(Color.popups.text, Color.accent)
          : (hot ? Style.hoverFillFor(Color.popups.text, Color.accent) : Style.normalFillFor(Color.popups.text, Color.accent))
        border.color: chosen ? Style.selectedBorderFor(Color.popups.text, Color.accent)
          : (hot ? Style.hoverBorderFor(Color.popups.text, Color.accent) : Style.normalBorderFor(Color.popups.text, Color.accent))
        border.width: chosen ? Math.max(1, Style.selectedBorderWidth) : (hot ? Style.hoverBorderWidth : Style.normalBorderWidth)

        Text {
          anchors.centerIn: parent
          text: modelData
          color: Color.popups.text
          font.family: Style.font.family
          font.pixelSize: Style.font.bodySmall
          font.bold: parent.chosen
        }
        MouseArea {
          id: mouse
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onContainsMouseChanged: root.sizeHovered(Number(modelData), index, containsMouse)
          onClicked: root.sizeActivated(Number(modelData), index)
        }
      }
    }
  }
}
