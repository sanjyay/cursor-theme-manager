import QtQuick
import QtQuick.Controls
import qs.Commons

Item {
  id: root
  property var themes: []
  property var committedTheme: null
  property int committedIndex: -1
  property int cursorIndex: 0
  property bool cursorActive: true

  signal themeActivated(var theme, int index)
  signal themeHovered(var theme, bool active)
  signal openFolderRequested(var theme)
  signal renameThemeRequested(var theme)
  signal removeThemeRequested(var theme)

  readonly property var userThemes: {
    var list = []
    for (var i = 0; i < root.themes.length; i++) {
      var t = root.themes[i]
      if (t && (t.imported || t.sourceType === "imported" || t.sourceType === "user")) {
        list.push({ theme: t, originalIndex: i })
      }
    }
    return list
  }

  readonly property var systemThemes: {
    var list = []
    for (var i = 0; i < root.themes.length; i++) {
      var t = root.themes[i]
      if (t && t.sourceType === "system" && !t.imported) {
        list.push({ theme: t, originalIndex: i })
      }
    }
    return list
  }

  Timer {
    id: hoverRestoreTimer
    interval: 80
    repeat: false
    onTriggered: root.themeHovered(null, false)
  }

  // Empty State when 0 themes are found
  Item {
    id: emptyState
    visible: root.themes.length === 0
    anchors.fill: parent

    Column {
      anchors.centerIn: parent
      spacing: Style.space(8)
      width: parent.width - Style.space(24)

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: "No cursor themes found"
        color: Color.popups.text
        font.family: Style.font.family
        font.pixelSize: Style.font.body
        font.bold: true
      }

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        text: "Install a cursor theme or use Import to add one."
        color: Color.muted
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        width: parent.width
      }
    }
  }

  // Scrollable Theme List
  Flickable {
    id: scrollArea
    visible: root.themes.length > 0
    anchors.fill: parent
    contentWidth: width
    contentHeight: sectionsCol.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    Column {
      id: sectionsCol
      width: parent.width
      spacing: Style.space(10)

      // ── 1. USER / IMPORTED SECTION ─────────────────────────────────────
      Column {
        width: parent.width
        spacing: Style.space(3)
        visible: root.userThemes.length > 0

        Text {
          text: "USER"
          color: Color.muted
          font.family: Style.font.family
          font.pixelSize: Style.font.caption - 2
          font.bold: true
          leftPadding: Style.space(8)
          bottomPadding: Style.space(2)
          visible: root.systemThemes.length > 0
        }

        Repeater {
          model: root.userThemes
          delegate: Rectangle {
            id: userRow
            required property int index
            required property var modelData

            readonly property bool isCommitted: root.committedTheme && (root.committedTheme.id === modelData.theme.id || root.committedTheme.displayName === modelData.theme.displayName)

            width: scrollArea.width - (scrollArea.ScrollBar.vertical.visible ? scrollArea.ScrollBar.vertical.width + Style.space(6) : Style.space(4))
            height: Style.space(34)
            radius: Style.cornerRadius - 2

            color: isCommitted
              ? Style.selectedFillFor(Color.popups.text, Color.accent)
              : (uRowMouse.containsMouse ? Style.hoverFillFor(Color.popups.text, Color.accent) : "transparent")

            border.color: isCommitted ? Style.selectedBorderFor(Color.popups.text, Color.accent) : "transparent"
            border.width: isCommitted ? 1 : 0

            // Left Accent Strip Indicator
            Rectangle {
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              width: 3
              height: parent.height - Style.space(10)
              radius: 1.5
              color: Color.accent
              visible: userRow.isCommitted
            }

            Item {
              anchors.fill: parent
              anchors.leftMargin: Style.space(12)
              anchors.rightMargin: Style.space(8)

              // Context Menu Button [⋯] (Only for Cursor Theme Manager imported themes)
              Rectangle {
                id: rowMenuBtn
                visible: (userRow.modelData.theme.imported === true || userRow.modelData.theme.sourceType === "imported") && (uRowMouse.containsMouse || userRow.isCommitted)
                anchors.verticalCenter: parent.verticalCenter
                anchors.right: parent.right
                width: Style.space(20)
                height: Style.space(20)
                radius: Style.space(3)
                color: rowMenuMouse.containsMouse ? Util.alpha(Color.accent, 0.25) : Util.alpha(Color.popups.text, 0.08)

                Text {
                  anchors.centerIn: parent
                  text: "⋯"
                  color: Color.popups.text
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }

                MouseArea {
                  id: rowMenuMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: rowContextMenu.open()
                }

                Menu {
                  id: rowContextMenu
                  y: rowMenuBtn.height + 2
                  MenuItem {
                    text: "Open folder"
                    onTriggered: root.openFolderRequested(userRow.modelData.theme)
                  }
                  MenuItem {
                    text: "Rename"
                    onTriggered: root.renameThemeRequested(userRow.modelData.theme)
                  }
                  MenuItem {
                    text: "Remove"
                    onTriggered: root.removeThemeRequested(userRow.modelData.theme)
                  }
                }
              }

              // Theme display name
              Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.right: rowMenuBtn.visible ? rowMenuBtn.left : parent.right
                anchors.rightMargin: Style.space(6)
                text: userRow.modelData.theme.displayName || userRow.modelData.theme.id
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                font.bold: userRow.isCommitted
                elide: Text.ElideRight
              }
            }

            MouseArea {
              id: uRowMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onEntered: {
                hoverRestoreTimer.stop()
                root.themeHovered(userRow.modelData.theme, true)
              }
              onExited: {
                hoverRestoreTimer.restart()
              }
              onClicked: {
                hoverRestoreTimer.stop()
                root.themeActivated(userRow.modelData.theme, userRow.modelData.originalIndex)
              }
            }
          }
        }
      }

      // ── 2. SYSTEM SECTION ──────────────────────────────────────────────
      Column {
        width: parent.width
        spacing: Style.space(3)
        visible: root.systemThemes.length > 0

        Text {
          text: "SYSTEM"
          color: Color.muted
          font.family: Style.font.family
          font.pixelSize: Style.font.caption - 2
          font.bold: true
          leftPadding: Style.space(8)
          bottomPadding: Style.space(2)
          visible: root.userThemes.length > 0
        }

        Repeater {
          model: root.systemThemes
          delegate: Rectangle {
            id: systemRow
            required property int index
            required property var modelData

            readonly property bool isCommitted: root.committedTheme && (root.committedTheme.id === modelData.theme.id || root.committedTheme.displayName === modelData.theme.displayName)

            width: scrollArea.width - (scrollArea.ScrollBar.vertical.visible ? scrollArea.ScrollBar.vertical.width + Style.space(6) : Style.space(4))
            height: Style.space(34)
            radius: Style.cornerRadius - 2

            color: isCommitted
              ? Style.selectedFillFor(Color.popups.text, Color.accent)
              : (sRowMouse.containsMouse ? Style.hoverFillFor(Color.popups.text, Color.accent) : "transparent")

            border.color: isCommitted ? Style.selectedBorderFor(Color.popups.text, Color.accent) : "transparent"
            border.width: isCommitted ? 1 : 0

            // Left Accent Strip Indicator
            Rectangle {
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              width: 3
              height: parent.height - Style.space(10)
              radius: 1.5
              color: Color.accent
              visible: systemRow.isCommitted
            }

            Item {
              anchors.fill: parent
              anchors.leftMargin: Style.space(12)
              anchors.rightMargin: Style.space(8)

              // Theme display name
              Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.rightMargin: Style.space(6)
                text: systemRow.modelData.theme.displayName || systemRow.modelData.theme.id
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                font.bold: systemRow.isCommitted
                elide: Text.ElideRight
              }
            }

            MouseArea {
              id: sRowMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onEntered: {
                hoverRestoreTimer.stop()
                root.themeHovered(systemRow.modelData.theme, true)
              }
              onExited: {
                hoverRestoreTimer.restart()
              }
              onClicked: {
                hoverRestoreTimer.stop()
                root.themeActivated(systemRow.modelData.theme, systemRow.modelData.originalIndex)
              }
            }
          }
        }
      }
    }
  }
}

