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
  property var hoveredTheme: null
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
      root.shell.hide("sanjyay.cursor-theme-manager")
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
    title: "Cursor Theme Manager"
    color: "transparent"
    visible: false
    implicitWidth: Style.space(1040)
    implicitHeight: Style.space(560)
    minimumSize: Qt.size(Style.space(800), Style.space(480))

    onVisibleChanged: {
      if (!visible && !root.closingFromHost && root.shell && typeof root.shell.hide === "function") {
        root.shell.hide("sanjyay.cursor-theme-manager")
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

          // Header Row: Title, Integration Button, and Import Button
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
              text: "Cursor Theme Manager"
              textFormat: Text.PlainText
              color: Color.popups.text
              font.family: Style.font.family
              font.pixelSize: Style.font.title
              font.bold: true
            }

            // Right actions row (Integration Settings + Import)
            Row {
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(10)

              // Desktop Integration Button
              Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                height: Style.space(32)
                radius: Style.cornerRadius
                color: integrationMouse.containsMouse ? Style.hoverFillFor(Color.popups.text, Color.accent) : Style.normalFillFor(Color.popups.text, Color.accent)
                border.color: integrationMouse.containsMouse ? Style.hoverBorderFor(Color.popups.text, Color.accent) : Style.normalBorderFor(Color.popups.text, Color.accent)
                border.width: 1
                implicitWidth: integrationLabel.implicitWidth + Style.space(18)

                Row {
                  id: integrationLabel
                  anchors.centerIn: parent
                  spacing: Style.space(5)

                  Text {
                    text: root.service && root.service.integrationInstalled ? "✓" : "⚙"
                    textFormat: Text.PlainText
                    color: root.service && root.service.integrationInstalled ? Color.accent : Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Text {
                    text: "Integration"
                    textFormat: Text.PlainText
                    color: Color.popups.text
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    font.bold: true
                  }
                }

                MouseArea {
                  id: integrationMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: integrationModal.open()
                }
              }

              // Import Button
              Rectangle {
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
                    textFormat: Text.PlainText
                    color: Color.accent
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                  }

                  Text {
                    text: "Import"
                    textFormat: Text.PlainText
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
            textFormat: Text.PlainText
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

            // Left Column: Cursor Themes List (~35% width)
            Item {
              id: leftPane
              anchors.top: parent.top
              anchors.bottom: parent.bottom
              anchors.left: parent.left
              width: Math.max(Style.space(240), Math.min(Style.space(340), Math.round(parent.width * 0.35)))

              ThemeListView {
                id: themeList
                anchors.fill: parent
                themes: root.service ? root.service.themes : []
                committedTheme: root.service ? root.service.committedTheme : null
                committedIndex: root.service ? root.service.indexOfCommitted() : -1
                cursorIndex: root.themeIndex
                cursorActive: root.focusSection === "themes"

                onThemeActivated: function(theme, index) {
                  root.hoveredTheme = null
                  root.themeIndex = index
                  root.focusSection = "themes"
                  root.service.commitTheme(theme)
                }

                onThemeHovered: function(theme, active) {
                  root.hoveredTheme = active ? theme : null
                  if (active && theme && root.service) {
                    root.service.fetchRoles(theme.displayName || theme.id, theme.path || "")
                  } else if (!active && root.service) {
                    var cur = (root.service.themes && root.themeIndex >= 0 && root.themeIndex < root.service.themes.length) ? root.service.themes[root.themeIndex] : root.service.committedTheme
                    if (cur) {
                      root.service.fetchRoles(cur.displayName || cur.id, cur.path || "")
                    }
                  }
                }

                onOpenFolderRequested: function(theme) {
                  if (root.service) root.service.openThemeFolder(theme)
                }

                onRenameThemeRequested: function(theme) {
                  renameDialog.open(theme)
                }

                onRemoveThemeRequested: function(theme) {
                  if (root.service) root.service.removeImportedTheme(theme)
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

            // Right Column: Preview, Size Stepper, Metadata & Actions (~65% width)
            CursorPreviewPane {
              id: previewPane
              anchors.top: parent.top
              anchors.bottom: parent.bottom
              anchors.left: dividerLine.right
              anchors.leftMargin: Style.space(14)
              anchors.right: parent.right
              theme: root.hoveredTheme || ((root.service && root.service.themes && root.themeIndex >= 0 && root.themeIndex < root.service.themes.length) ? root.service.themes[root.themeIndex] : (root.service ? root.service.committedTheme : null))
              committedSize: root.service ? root.service.committedSize : 16
              previewRoles: {
                if (!root.service) return ({})
                var activeTheme = previewPane.theme
                if (activeTheme) {
                  var name = activeTheme.displayName || activeTheme.id
                  if (root.service.rolesCache && root.service.rolesCache[name]) {
                    return root.service.rolesCache[name]
                  }
                  if (name && root.service.rolesCache && root.service.rolesCache[name.toLowerCase()]) {
                    return root.service.rolesCache[name.toLowerCase()]
                  }
                }
                return root.service.currentRoles || ({})
              }
              sizeCursorActive: root.focusSection === "sizes"

              onSizeActivated: function(size) {
                root.focusSection = "sizes"
                root.service.commitSize(size)
              }

              onOpenFolderRequested: function(theme) {
                if (root.service) root.service.openThemeFolder(theme)
              }

              onRenameThemeRequested: function(theme) {
                renameDialog.open(theme)
              }

              onRemoveThemeRequested: function(theme) {
                if (root.service) root.service.removeImportedTheme(theme)
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
              textFormat: Text.PlainText
              color: Color.accent
              font.family: Style.font.family
              font.pixelSize: Style.font.bodySmall
              font.bold: true
            }

            Text {
              id: successLabel
              text: "Theme imported successfully"
              textFormat: Text.PlainText
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

      // In-App Rename Modal Dialog
      RenameDialog {
        id: renameDialog
        anchors.fill: parent
        service: root.service
        z: 50
        onClosed: {
          if (panelScope) panelScope.forceActiveFocus()
        }
      }

      // Optional Desktop Integration Modal Dialog
      Item {
        id: integrationModal
        anchors.fill: parent
        z: 60
        visible: opacity > 0
        opacity: active ? 1.0 : 0.0
        property bool active: false
        Behavior on opacity { NumberAnimation { duration: 140 } }

        function open() {
          active = true
          if (root.service) root.service.checkIntegrationStatus()
        }

        function close() {
          active = false
          if (panelScope) panelScope.forceActiveFocus()
        }

        Rectangle {
          anchors.fill: parent
          color: Util.alpha("#000000", 0.65)
          MouseArea {
            anchors.fill: parent
            onClicked: integrationModal.close()
          }
        }

        Rectangle {
          id: integrationCard
          anchors.centerIn: parent
          width: Math.min(parent.width - Style.space(32), Style.space(560))
          implicitHeight: intCol.implicitHeight + Style.space(36)
          radius: Style.cornerRadius
          color: Color.popups.background
          border.color: Color.popups.border
          border.width: 1
          clip: true

          MouseArea { anchors.fill: parent }

          Column {
            id: intCol
            anchors.fill: parent
            anchors.margins: Style.space(18)
            spacing: Style.space(12)

            Row {
              width: parent.width
              spacing: Style.space(8)

              Text {
                text: "⚙"
                textFormat: Text.PlainText
                color: Color.accent
                font.family: Style.font.family
                font.pixelSize: Style.font.title
              }

              Text {
                text: "Optional Desktop Integration"
                textFormat: Text.PlainText
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.title
                font.bold: true
              }
            }

            Text {
              width: parent.width
              text: "This optional feature registers Cursor Theme Manager with your desktop environment so it can be launched from the application launcher and preserves restoration cleanup support."
              textFormat: Text.PlainText
              color: Color.popups.text
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }

            Rectangle {
              width: parent.width
              implicitHeight: pathCol.implicitHeight + Style.space(16)
              radius: Style.cornerRadius - 2
              color: Util.alpha(Color.popups.text, 0.03)
              border.color: Util.alpha(Color.popups.text, 0.1)
              border.width: 1

              Column {
                id: pathCol
                anchors.fill: parent
                anchors.margins: Style.space(8)
                spacing: Style.space(4)

                Text {
                  text: "Installs the following files upon consent:"
                  textFormat: Text.PlainText
                  color: Color.muted
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption - 1
                  font.bold: true
                }

                Text {
                  text: "• ~/.local/share/applications/omarchy-cursor-switcher.desktop"
                  textFormat: Text.PlainText
                  color: Color.popups.text
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption - 1
                }
                Text {
                  text: "• ~/.local/bin/omarchy-cursor-switcher"
                  textFormat: Text.PlainText
                  color: Color.popups.text
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption - 1
                }
                Text {
                  text: "• ~/.local/share/omarchy-cursor-switcher/omarchy-cursor-switcher-cleanup"
                  textFormat: Text.PlainText
                  color: Color.popups.text
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption - 1
                }
                Text {
                  text: "• ~/.local/share/icons/hicolor/scalable/apps/omarchy-cursor-switcher.svg"
                  textFormat: Text.PlainText
                  color: Color.popups.text
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption - 1
                }
              }
            }

            // Status Row
            Row {
              spacing: Style.space(8)

              Text {
                text: "Status:"
                textFormat: Text.PlainText
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                font.bold: true
              }

              Text {
                text: root.service && root.service.integrationInstalled ? "Installed & Active" : "Not Installed (Plugin runs locally)"
                textFormat: Text.PlainText
                color: root.service && root.service.integrationInstalled ? Color.accent : Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                font.bold: true
              }
            }

            // Error banner if any
            Text {
              visible: Boolean(root.service && root.service.integrationError)
              text: root.service ? root.service.integrationError : ""
              textFormat: Text.PlainText
              color: Color.urgent
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
              width: parent.width
            }

            // Button Row
            Row {
              anchors.right: parent.right
              spacing: Style.space(8)

              Rectangle {
                width: closeIntLabel.implicitWidth + Style.space(20)
                height: Style.space(32)
                radius: Style.cornerRadius - 2
                color: closeIntMouse.containsMouse ? Util.alpha(Color.popups.text, 0.12) : Util.alpha(Color.popups.text, 0.06)
                border.color: Util.alpha(Color.popups.text, 0.14)
                border.width: 1

                Text {
                  id: closeIntLabel
                  anchors.centerIn: parent
                  text: "Close"
                  textFormat: Text.PlainText
                  color: Color.popups.text
                  font.family: Style.font.family
                  font.pixelSize: Style.font.bodySmall
                  font.bold: true
                }

                MouseArea {
                  id: closeIntMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: integrationModal.close()
                }
              }

              Rectangle {
                id: intActionBtn
                readonly property bool isInstalled: Boolean(root.service && root.service.integrationInstalled)
                width: intActionLabel.implicitWidth + Style.space(20)
                height: Style.space(32)
                radius: Style.cornerRadius - 2
                color: isInstalled
                  ? (intActionMouse.containsMouse ? Util.alpha(Color.urgent, 0.25) : Util.alpha(Color.urgent, 0.15))
                  : (intActionMouse.containsMouse ? Color.accent : Util.alpha(Color.accent, 0.85))
                border.color: isInstalled ? Color.urgent : Color.accent
                border.width: 1

                Text {
                  id: intActionLabel
                  anchors.centerIn: parent
                  text: intActionBtn.isInstalled ? "Remove Integration" : "Install Integration"
                  textFormat: Text.PlainText
                  color: intActionBtn.isInstalled ? Color.urgent : Color.popups.background
                  font.family: Style.font.family
                  font.pixelSize: Style.font.bodySmall
                  font.bold: true
                }

                MouseArea {
                  id: intActionMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    if (intActionBtn.isInstalled) {
                      if (root.service) root.service.removeIntegration()
                    } else {
                      if (root.service) root.service.installIntegration()
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
