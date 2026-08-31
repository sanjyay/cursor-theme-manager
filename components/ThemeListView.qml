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

  readonly property var bundledThemes: {
    var list = []
    for (var i = 0; i < root.themes.length; i++) {
      var t = root.themes[i]
      if (t && !t.imported && t.sourceType !== "imported") {
        list.push({ theme: t, originalIndex: i })
      }
    }
    return list
  }

  readonly property var importedThemes: {
    var list = []
    for (var i = 0; i < root.themes.length; i++) {
      var t = root.themes[i]
      if (t && (t.imported || t.sourceType === "imported")) {
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

  // Scrollable Theme List
  Flickable {
    id: scrollArea
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

      // ── 1. BUNDLED SECTION ─────────────────────────────────────────────
      Column {
        width: parent.width
        spacing: Style.space(3)
        visible: root.bundledThemes.length > 0

        Repeater {
          model: root.bundledThemes
          delegate: Rectangle {
            id: bundledRow
            required property int index
            required property var modelData

            readonly property bool isCommitted: root.committedTheme && (root.committedTheme.id === modelData.theme.id || root.committedTheme.displayName === modelData.theme.displayName)

            width: scrollArea.width - (scrollArea.ScrollBar.vertical.visible ? scrollArea.ScrollBar.vertical.width + Style.space(6) : Style.space(4))
            height: Style.space(34)
            radius: Style.cornerRadius - 2

            color: isCommitted
              ? Style.selectedFillFor(Color.popups.text, Color.accent)
              : (bRowMouse.containsMouse ? Style.hoverFillFor(Color.popups.text, Color.accent) : "transparent")

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
              visible: bundledRow.isCommitted
            }

            Item {
              anchors.fill: parent
              anchors.leftMargin: Style.space(12)
              anchors.rightMargin: Style.space(10)

              // Theme display name
              Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.rightMargin: Style.space(6)
                text: bundledRow.modelData.theme.displayName || bundledRow.modelData.theme.id
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                font.bold: bundledRow.isCommitted
                elide: Text.ElideRight
              }
            }

            MouseArea {
              id: bRowMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onEntered: {
                hoverRestoreTimer.stop()
                root.themeHovered(bundledRow.modelData.theme, true)
              }
              onExited: {
                hoverRestoreTimer.restart()
              }
              onClicked: {
                hoverRestoreTimer.stop()
                root.themeActivated(bundledRow.modelData.theme, bundledRow.modelData.originalIndex)
              }
            }
          }
        }
      }

      // ── 2. IMPORTED SECTION ────────────────────────────────────────────
      Column {
        width: parent.width
        spacing: Style.space(3)
        visible: root.importedThemes.length > 0

        Text {
          text: "IMPORTED"
          color: Color.muted
          font.family: Style.font.family
          font.pixelSize: Style.font.caption - 2
          font.bold: true
          leftPadding: Style.space(8)
          bottomPadding: Style.space(2)
        }

        Repeater {
          model: root.importedThemes
          delegate: Rectangle {
            id: importedRow
            required property int index
            required property var modelData

            readonly property bool isCommitted: root.committedTheme && (root.committedTheme.id === modelData.theme.id || root.committedTheme.displayName === modelData.theme.displayName)

            width: scrollArea.width - (scrollArea.ScrollBar.vertical.visible ? scrollArea.ScrollBar.vertical.width + Style.space(6) : Style.space(4))
            height: Style.space(34)
            radius: Style.cornerRadius - 2

            color: isCommitted
              ? Style.selectedFillFor(Color.popups.text, Color.accent)
              : (iRowMouse.containsMouse ? Style.hoverFillFor(Color.popups.text, Color.accent) : "transparent")

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
              visible: importedRow.isCommitted
            }

            Item {
              anchors.fill: parent
              anchors.leftMargin: Style.space(12)
              anchors.rightMargin: Style.space(8)

              // Context Menu Button [⋯]
              Rectangle {
                id: rowMenuBtn
                visible: iRowMouse.containsMouse || importedRow.isCommitted
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
                    onTriggered: root.openFolderRequested(importedRow.modelData.theme)
                  }
                  MenuItem {
                    text: "Rename"
                    onTriggered: root.renameThemeRequested(importedRow.modelData.theme)
                  }
                  MenuItem {
                    text: "Remove"
                    onTriggered: root.removeThemeRequested(importedRow.modelData.theme)
                  }
                }
              }

              // Theme display name
              Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.right: rowMenuBtn.visible ? rowMenuBtn.left : parent.right
                anchors.rightMargin: Style.space(6)
                text: importedRow.modelData.theme.displayName || importedRow.modelData.theme.id
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                font.bold: importedRow.isCommitted
                elide: Text.ElideRight
              }
            }

            MouseArea {
              id: iRowMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onEntered: {
                hoverRestoreTimer.stop()
                root.themeHovered(importedRow.modelData.theme, true)
              }
              onExited: {
                hoverRestoreTimer.restart()
              }
              onClicked: {
                hoverRestoreTimer.stop()
                root.themeActivated(importedRow.modelData.theme, importedRow.modelData.originalIndex)
              }
            }
          }
        }
      }
    }
  }
}
