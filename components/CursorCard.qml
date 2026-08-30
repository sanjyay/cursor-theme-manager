import QtQuick
import qs.Commons

Rectangle {
  id: root
  required property var theme
  property bool selected: false
  property bool hasCursor: false
  signal activated()
  signal hovered(bool active)

  radius: Style.cornerRadius
  implicitWidth: Style.space(170)
  implicitHeight: Style.space(116)
  color: selected ? Style.selectedFillFor(Color.popups.text, Color.accent)
    : (mouse.containsMouse || hasCursor ? Style.hoverFillFor(Color.popups.text, Color.accent) : Style.normalFillFor(Color.popups.text, Color.accent))
  border.color: selected ? Style.selectedBorderFor(Color.popups.text, Color.accent)
    : (mouse.containsMouse || hasCursor ? Style.hoverBorderFor(Color.popups.text, Color.accent) : Style.normalBorderFor(Color.popups.text, Color.accent))
  border.width: selected ? Math.max(1, Style.selectedBorderWidth) : (mouse.containsMouse || hasCursor ? Style.hoverBorderWidth : Style.normalBorderWidth)

  Column {
    anchors.fill: parent
    anchors.margins: Style.space(10)
    spacing: Style.space(5)

    Item {
      width: parent.width
      height: Style.space(60)

      Image {
        visible: root.theme.previewPath !== ""
        anchors.centerIn: parent
        width: Style.space(54)
        height: width
        source: root.theme.previewPath === "" ? "" : "file://" + root.theme.previewPath
        fillMode: Image.PreserveAspectFit
        asynchronous: true
        smooth: true
      }

      Text {
        visible: root.theme.previewPath === ""
        anchors.centerIn: parent
        text: "↖"
        color: Color.popups.text
        font.family: Style.font.family
        font.pixelSize: Style.font.displayLarge
      }

      Text {
        visible: root.selected
        anchors.right: parent.right
        anchors.top: parent.top
        text: "✓"
        color: Color.accent
        font.family: Style.font.family
        font.pixelSize: Style.font.body
        font.bold: true
      }
    }

    Text {
      width: parent.width
      text: root.theme.displayName
      color: Color.popups.text
      font.family: Style.font.family
      font.pixelSize: Style.font.body
      font.bold: root.selected
      elide: Text.ElideRight
      horizontalAlignment: Text.AlignHCenter
    }

    Text {
      width: parent.width
      text: root.theme.subtitle ? root.theme.subtitle : (root.theme.formats.length === 2 ? "HYPR + X" : (root.theme.formats[0] === "hyprcursor" ? "HYPR" : "XCURSOR"))
      color: Color.muted
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
      horizontalAlignment: Text.AlignHCenter
    }
  }

  MouseArea {
    id: mouse
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onContainsMouseChanged: root.hovered(containsMouse)
    onClicked: root.activated()
  }
}
