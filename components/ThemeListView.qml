import QtQuick
import QtQuick.Controls
import qs.Commons

Item {
  id: root
  property var themes: []
  property int committedIndex: -1
  property int cursorIndex: 0
  property bool cursorActive: true
  signal themeActivated(var theme, int index)
  signal themeHovered(var theme, int index, bool active)

  function ensureVisible(index) {
    if (index >= 0 && index < listView.count) {
      listView.positionViewAtIndex(index, ListView.Contain)
    }
  }

  ListView {
    id: listView
    anchors.fill: parent
    model: root.themes
    clip: true
    spacing: Style.space(4)
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    delegate: Rectangle {
      id: rowItem
      required property int index
      required property var modelData

      readonly property bool isCommitted: rowItem.index === root.committedIndex
      readonly property bool isFocused: root.cursorActive && rowItem.index === root.cursorIndex
      readonly property bool isSelected: isCommitted || isFocused

      width: listView.width - (listView.ScrollBar.vertical.visible ? listView.ScrollBar.vertical.width + Style.space(6) : Style.space(4))
      height: Style.space(38)
      radius: Style.cornerRadius - 2

      color: isCommitted ? Style.selectedFillFor(Color.popups.text, Color.accent)
        : (isFocused || rowMouse.containsMouse ? Style.hoverFillFor(Color.popups.text, Color.accent) : "transparent")

      border.color: isCommitted ? Style.selectedBorderFor(Color.popups.text, Color.accent)
        : (isFocused ? Style.hoverBorderFor(Color.popups.text, Color.accent) : "transparent")
      border.width: isCommitted || isFocused ? 1 : 0

      Item {
        anchors.fill: parent
        anchors.leftMargin: Style.space(12)
        anchors.rightMargin: Style.space(12)

        // Active Checkmark Icon
        Text {
          id: checkIcon
          visible: rowItem.isCommitted
          anchors.verticalCenter: parent.verticalCenter
          anchors.right: parent.right
          text: "✓"
          color: Color.accent
          font.family: Style.font.family
          font.pixelSize: Style.font.body
          font.bold: true
        }

        // Subtle Imported Badge
        Rectangle {
          id: badgeRect
          visible: Boolean(rowItem.modelData && (rowItem.modelData.imported === true || rowItem.modelData.sourceType === "imported"))
          anchors.verticalCenter: parent.verticalCenter
          anchors.right: checkIcon.visible ? checkIcon.left : parent.right
          anchors.rightMargin: checkIcon.visible ? Style.space(8) : 0
          height: Style.space(20)
          radius: Style.space(3)
          color: Util.alpha(Color.popups.text, 0.12)
          border.color: Util.alpha(Color.popups.text, 0.22)
          border.width: 1
          implicitWidth: badgeLabel.implicitWidth + Style.space(8)

          Text {
            id: badgeLabel
            anchors.centerIn: parent
            text: "Imported"
            color: Color.popups.text
            font.family: Style.font.family
            font.pixelSize: Style.font.caption - 2
            font.bold: true
          }
        }

        // Theme display name
        Text {
          id: themeLabel
          anchors.verticalCenter: parent.verticalCenter
          anchors.left: parent.left
          anchors.right: badgeRect.visible ? badgeRect.left : (checkIcon.visible ? checkIcon.left : parent.right)
          anchors.rightMargin: Style.space(8)
          text: rowItem.modelData ? (rowItem.modelData.displayName || rowItem.modelData.id) : ""
          color: rowItem.isCommitted ? Color.accent : Color.popups.text
          font.family: Style.font.family
          font.pixelSize: Style.font.body
          font.bold: rowItem.isCommitted
          elide: Text.ElideRight
        }
      }

      MouseArea {
        id: rowMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onEntered: root.themeHovered(rowItem.modelData, rowItem.index, true)
        onExited: root.themeHovered(rowItem.modelData, rowItem.index, false)
        onClicked: root.themeActivated(rowItem.modelData, rowItem.index)
      }
    }
  }
}
