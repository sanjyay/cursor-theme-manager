import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "components"
import "CursorModel.js" as Model

Item {
  id: root
  property var shell: null
  property var service: null
  property bool closingFromHost: false
  property string focusSection: "themes"
  property int themeIndex: 0
  readonly property bool opened: window.visible

  function open(payloadJson) {
    closingFromHost = false
    if (root.service) {
      root.service.refreshIfStale()
      var idx = root.service.indexOfCommitted()
      if (idx !== -1) {
        root.themeIndex = idx
        var cur = root.service.themes[idx]
        if (cur) {
          root.service.fetchRoles(cur.displayName || cur.id, cur.path || "")
        }
      }
    }
    root.focusSection = "themes"
    window.visible = true
    Qt.callLater(function() {
      if (panelScope) panelScope.forceActiveFocus()
      if (themeList && root.themeIndex >= 0) themeList.ensureVisible(root.themeIndex)
    })
  }

  function close() {
    closingFromHost = true
    if (root.service && root.service.previewActive) root.service.cancelPreview()
    window.visible = false
    closingFromHost = false
  }

  function requestClose() {
    if (root.service && root.service.previewActive) root.service.cancelPreview()
    window.visible = false
    if (root.shell && typeof root.shell.hide === "function") {
      root.shell.hide("goblin.cursor-switcher")
    }
  }

  function summon(payloadJson) { open(payloadJson) }
  function hide() { requestClose() }
  function toggle() { if (opened) requestClose(); else open() }

  Connections {
    target: root.service
    function onThemesChangedByScan() {
      if (root.service && root.themeIndex >= root.service.themes.length) {
        root.themeIndex = Math.max(0, root.service.themes.length - 1)
      }
    }
  }

  FloatingWindow {
    id: window
    title: "Cursor Theme"
    color: "transparent"
    visible: false
    implicitWidth: Style.space(1040)
    implicitHeight: Style.space(560)
    minimumSize: Qt.size(Style.space(800), Style.space(480))

    onVisibleChanged: {
      if (!visible && !root.closingFromHost && root.shell && typeof root.shell.hide === "function") {
        root.shell.hide("goblin.cursor-switcher")
      }
    }

    Rectangle {
      id: backdrop
      anchors.fill: parent
      radius: Style.cornerRadius
      color: Color.popups.background
      border.color: Color.popups.border
      border.width: 1

      FocusScope {
        id: panelScope
        anchors.fill: parent
        focus: true

        Keys.onEscapePressed: function(event) {
          event.accepted = true
          root.requestClose()
        }

        Keys.onTabPressed: function(event) {
          event.accepted = true
          root.focusSection = (root.focusSection === "themes" ? "sizes" : "themes")
        }

        Keys.onBacktabPressed: function(event) {
          event.accepted = true
          root.focusSection = (root.focusSection === "themes" ? "sizes" : "themes")
        }

        Keys.onUpPressed: function(event) {
          event.accepted = true
          if (root.focusSection === "themes" && root.service && root.service.themes.length > 0) {
            root.themeIndex = Math.max(0, root.themeIndex - 1)
            themeList.ensureVisible(root.themeIndex)
            var t = root.service.themes[root.themeIndex]
            if (t) {
              root.service.commitTheme(t)
            }
          }
        }

        Keys.onDownPressed: function(event) {
          event.accepted = true
          if (root.focusSection === "themes" && root.service && root.service.themes.length > 0) {
            root.themeIndex = Math.min(root.service.themes.length - 1, root.themeIndex + 1)
            themeList.ensureVisible(root.themeIndex)
            var t = root.service.themes[root.themeIndex]
            if (t) {
              root.service.commitTheme(t)
            }
          }
        }

        Keys.onLeftPressed: function(event) {
          if (root.focusSection === "sizes" && root.service) {
            event.accepted = true
            var prev = Model.prevSize(root.service.committedSize)
            root.service.commitSize(prev)
          }
        }

        Keys.onRightPressed: function(event) {
          if (root.focusSection === "sizes" && root.service) {
            event.accepted = true
            var next = Model.nextSize(root.service.committedSize)
            root.service.commitSize(next)
          }
        }

        Keys.onReturnPressed: function(event) {
          event.accepted = true
          if (root.service && root.service.themes[root.themeIndex]) {
            root.service.commitTheme(root.service.themes[root.themeIndex])
          }
        }

        Keys.onSpacePressed: function(event) {
          event.accepted = true
          if (root.service && root.service.themes[root.themeIndex]) {
            root.service.commitTheme(root.service.themes[root.themeIndex])
          }
        }

        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_R && !(event.modifiers & Qt.ControlModifier)) {
            event.accepted = true
            if (root.service) root.service.refresh(true)
          }
        }

        Item {
          id: contentArea
          anchors.fill: parent
          anchors.margins: Style.space(20)

          // Header Row: Title and Import Button
          Item {
            id: headerRow
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: Style.space(36)

            Text {
              id: headerTitle
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              text: "Cursor Theme"
              color: Color.popups.text
              font.family: Style.font.family
              font.pixelSize: Style.font.title
              font.bold: true
            }

            // Import Button (anchored right)
            Rectangle {
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              height: Style.space(32)
              radius: Style.cornerRadius
              color: importMouse.containsMouse ? Style.hoverFillFor(Color.popups.text, Color.accent) : Style.normalFillFor(Color.popups.text, Color.accent)
              border.color: importMouse.containsMouse ? Style.hoverBorderFor(Color.popups.text, Color.accent) : Style.normalBorderFor(Color.popups.text, Color.accent)
              border.width: 1
              implicitWidth: importLabel.implicitWidth + Style.space(18)

              Row {
                id: importLabel
                anchors.centerIn: parent
                spacing: Style.space(5)

                Text {
                  text: "󰋺"
                  color: Color.accent
                  font.family: Style.font.family
                  font.pixelSize: Style.font.body
                }

                Text {
                  text: "Import"
                  color: Color.popups.text
                  font.family: Style.font.family
                  font.pixelSize: Style.font.bodySmall
                  font.bold: true
                }
              }

              MouseArea {
                id: importMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: importDialog.open()
              }
            }
          }

          // Error Message Banner (if any)
          Text {
            id: errorBanner
            visible: Boolean(root.service && root.service.lastError !== "")
            anchors.top: headerRow.bottom
            anchors.topMargin: Style.space(6)
            anchors.left: parent.left
            anchors.right: parent.right
            text: root.service ? root.service.lastError : ""
            color: Color.urgent
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }

          // Main 2-Column Split Pane
          Item {
            id: splitBody
            anchors.top: errorBanner.visible ? errorBanner.bottom : headerRow.bottom
            anchors.topMargin: Style.space(14)
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom

            // Left Column: Cursor Themes List (~38% width)
            Item {
              id: leftPane
              anchors.top: parent.top
              anchors.bottom: parent.bottom
              anchors.left: parent.left
              width: Math.max(Style.space(240), Math.min(Style.space(340), Math.round(parent.width * 0.35)))

              Text {
                id: listHeader
                anchors.top: parent.top
                anchors.left: parent.left
                text: "Cursor Themes"
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                font.bold: true
              }

              ThemeListView {
                id: themeList
                anchors.top: listHeader.bottom
                anchors.topMargin: Style.space(8)
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                themes: root.service ? root.service.themes : []
                committedIndex: root.service ? root.service.indexOfCommitted() : -1
                cursorIndex: root.themeIndex
                cursorActive: root.focusSection === "themes"

                onThemeActivated: function(theme, index) {
                  root.themeIndex = index
                  root.focusSection = "themes"
                  root.service.commitTheme(theme)
                }

                onThemeHovered: function(theme, index, hovered) {
                  if (hovered && root.service) {
                    root.themeIndex = index
                    root.service.fetchRoles(theme.displayName || theme.id, theme.path || "")
                  }
                }
              }
            }

            // Divider Line
            Rectangle {
              id: dividerLine
              anchors.top: parent.top
              anchors.bottom: parent.bottom
              anchors.left: leftPane.right
              anchors.leftMargin: Style.space(14)
              width: 1
              color: Util.alpha(Color.popups.text, 0.1)
            }

            // Right Column: Preview, Size Stepper, Metadata & Actions (~62% width)
            CursorPreviewPane {
              id: previewPane
              anchors.top: parent.top
              anchors.bottom: parent.bottom
              anchors.left: dividerLine.right
              anchors.leftMargin: Style.space(14)
              anchors.right: parent.right
              theme: (root.service && root.service.themes && root.themeIndex >= 0 && root.themeIndex < root.service.themes.length) ? root.service.themes[root.themeIndex] : (root.service ? root.service.committedTheme : null)
              committedSize: root.service ? root.service.committedSize : 16
              previewRoles: root.service ? root.service.currentRoles : ({})
              sizeCursorActive: root.focusSection === "sizes"

              onSizeActivated: function(size) {
                root.focusSection = "sizes"
                root.service.commitSize(size)
              }

              onRemoveThemeRequested: function(theme) {
                root.service.removeImportedTheme(theme)
              }
            }
          }
        }

        // Success notification banner
        Rectangle {
          id: successPill
          visible: opacity > 0
          opacity: 0
          anchors.bottom: parent.bottom
          anchors.horizontalCenter: parent.horizontalCenter
          anchors.bottomMargin: Style.space(16)
          z: 40
          width: successRow.implicitWidth + Style.space(24)
          height: Style.space(34)
          radius: height / 2
          color: Util.alpha(Color.popups.background, 0.95)
          border.color: Color.accent
          border.width: 1

          Behavior on opacity { NumberAnimation { duration: 150 } }

          Timer {
            id: successTimer
            interval: 3500
            onTriggered: successPill.opacity = 0
          }

          Row {
            id: successRow
            anchors.centerIn: parent
            spacing: Style.space(8)

            Text {
              text: "✓"
              color: Color.accent
              font.family: Style.font.family
              font.pixelSize: Style.font.bodySmall
              font.bold: true
            }

            Text {
              id: successLabel
              text: "Theme imported successfully"
              color: Color.popups.text
              font.family: Style.font.family
              font.pixelSize: Style.font.bodySmall
              font.bold: true
            }
          }
        }

        Connections {
          target: root.service
          function onImportCompleted(theme, message) {
            successLabel.text = message || ("Imported " + (theme ? theme.displayName : "theme"))
            successPill.opacity = 1.0
            successTimer.restart()
          }
        }
      }

      // In-App Import Modal Dialog
      ImportDialog {
        id: importDialog
        anchors.fill: parent
        service: root.service
        z: 50
        onClosed: {
          if (panelScope) panelScope.forceActiveFocus()
        }
      }
    }
  }
}

