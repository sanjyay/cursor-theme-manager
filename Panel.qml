import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "components"
import "CursorModel.js" as Model
import "ThemeCursorMappings.js" as Mappings

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
    if (service) {
      service.refreshIfStale()
      themeIndex = Math.max(0, service.indexOfCommitted())
    }
    focusSection = "themes"
    window.visible = true
    Qt.callLater(function() { keyCatcher.forceActiveFocus(); grid.ensureVisible(themeIndex) })
  }

  function close() {
    closingFromHost = true
    if (service) service.cancelPreview()
    window.visible = false
    closingFromHost = false
  }

  function toggle() { if (opened) requestClose(); else open("") }

  function requestClose() {
    if (service) service.cancelPreview()
    if (shell && typeof shell.hide === "function") shell.hide("sanjyay.cursor-switcher")
    else window.visible = false
  }

  function moveCursor(dx, dy) {
    if (!service || !service.ready) return
    if (focusSection === "themes") {
      if (dy !== 0) themeIndex += dy * grid.columns
      else themeIndex += dx
      themeIndex = Math.max(0, Math.min(service.themes.length - 1, themeIndex))
      grid.ensureVisible(themeIndex)
    } else {
      var step = dx !== 0 ? dx : dy
      if (step < 0 && Model.canDecreaseSize(service.committedSize)) {
        service.commitSize(Model.prevSize(service.committedSize))
      } else if (step > 0 && Model.canIncreaseSize(service.committedSize)) {
        service.commitSize(Model.nextSize(service.committedSize))
      }
    }
  }

  function activateCursor() {
    if (!service || !service.ready) return
    if (focusSection === "themes" && service.themes[themeIndex]) {
      service.commitTheme(service.themes[themeIndex])
    }
  }

  function applyTheme(arg) {
    try {
      var requested = JSON.parse(String(arg || "{}"))
      var theme = service ? Model.findTheme(service.themes, requested.theme || requested) : null
      if (!theme && service) {
        for (var i = 0; i < service.themes.length; i++) {
          var candidate = service.themes[i]
          if (candidate.hyprcursor === requested.theme || candidate.xcursor === requested.theme || candidate.displayName === requested.theme || candidate.id === requested.theme) {
            theme = candidate
            break
          }
        }
      }
      if (!theme) return "unknown theme"
      service.enqueueApply(theme, requested.size || service.committedSize, "commit")
      return "ok"
    } catch (error) { return "invalid json" }
  }

  function restore() { if (service) service.restoreConfigured(); return "ok" }
  function preview(arg) {
    try {
      var requested = JSON.parse(String(arg || "{}"))
      var theme = service.committedTheme
      if (requested.theme) {
        theme = service ? Model.findTheme(service.themes, requested.theme) : null
        if (!theme && service) {
          for (var i = 0; i < service.themes.length; i++) {
            var candidate = service.themes[i]
            if (candidate.hyprcursor === requested.theme || candidate.xcursor === requested.theme || candidate.displayName === requested.theme || candidate.id === requested.theme) {
              theme = candidate
              break
            }
          }
        }
      }
      if (!theme) return "unknown theme"
      service.requestPreview(theme, requested.size || service.committedSize)
      return "ok"
    } catch (error) { return "invalid json" }
  }
  function cancelPreview() { if (service) service.cancelPreview(); return "ok" }
  function refresh() { if (service) service.refresh(true); return "ok" }
  function status() { return service ? service.statusText : "service unavailable" }
  function panelState(arg) { return opened ? "open" : "closed" }

  FloatingWindow {
    id: window
    visible: false
    title: "Cursor Theme Switcher"
    color: Color.popups.background
    implicitWidth: Math.min(Style.space(680), 820)
    implicitHeight: Math.min(Style.space(580), 720)
    minimumSize: Qt.size(Math.min(Style.space(520), 580), Math.min(Style.space(420), 480))

    onVisibleChanged: {
      if (!visible && !root.closingFromHost) {
        if (root.service) root.service.cancelPreview()
        if (root.shell && typeof root.shell.hide === "function") root.shell.hide("sanjyay.cursor-switcher")
      }
    }

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onMoveRequested: function(dx, dy) { root.moveCursor(dx, dy) }
      onActivateRequested: root.activateCursor()
      onCloseRequested: root.requestClose()
      onTabRequested: function(direction) {
        root.focusSection = root.focusSection === "themes" ? "sizes" : "themes"
      }
      onTextKey: function(text) {
        if (text === "r" || text === "R") {
          if (root.service) root.service.refresh(true)
        } else if (text === "m" || text === "M") {
          if (root.service) root.service.setMode("manual")
        } else if (text === "f" || text === "F") {
          if (root.service) root.service.setMode("follow-omarchy")
        } else if (text === "i" || text === "I") {
          if (root.service) root.service.chooseAndImportFile()
        }
      }

      Column {
        anchors.fill: parent
        anchors.margins: Style.space(20)
        spacing: Style.space(10)

        // Header Row: Title, Mode Segmented Buttons, Import Action
        Row {
          width: parent.width
          spacing: Style.space(12)

          Text {
            id: title
            anchors.verticalCenter: parent.verticalCenter
            text: "Cursor Theme Switcher"
            color: Color.popups.text
            font.family: Style.font.family
            font.pixelSize: Style.font.title
            font.bold: true
          }

          Item { width: Style.space(10); height: 1 }

          // Segmented Mode Toggle: [ Manual ] [ Follow Theme ]
          Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            height: Style.space(32)
            radius: Style.cornerRadius
            color: Style.alpha(Color.popups.text, 0.08)
            border.color: Style.alpha(Color.popups.text, 0.15)
            border.width: 1
            implicitWidth: modeRow.implicitWidth + Style.space(6)

            Row {
              id: modeRow
              anchors.centerIn: parent
              spacing: Style.space(3)

              Rectangle {
                property bool active: root.service && root.service.mode === "manual"
                height: Style.space(26)
                radius: Style.cornerRadius - 2
                color: active ? Color.accent : "transparent"
                implicitWidth: manualLabel.implicitWidth + Style.space(14)

                Text {
                  id: manualLabel
                  anchors.centerIn: parent
                  text: "Manual"
                  color: parent.active ? Color.popups.background : Color.popups.text
                  font.family: Style.font.family
                  font.pixelSize: Style.font.bodySmall
                  font.bold: parent.active
                }

                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  onClicked: if (root.service) root.service.setMode("manual")
                }
              }

              Rectangle {
                property bool active: root.service && root.service.mode === "follow-omarchy"
                height: Style.space(26)
                radius: Style.cornerRadius - 2
                color: active ? Color.accent : "transparent"
                implicitWidth: followLabel.implicitWidth + Style.space(14)

                Text {
                  id: followLabel
                  anchors.centerIn: parent
                  text: "Follow Theme"
                  color: parent.active ? Color.popups.background : Color.popups.text
                  font.family: Style.font.family
                  font.pixelSize: Style.font.bodySmall
                  font.bold: parent.active
                }

                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  onClicked: if (root.service) root.service.setMode("follow-omarchy")
                }
              }
            }
          }

          Item { width: 1; height: 1; Layout.fillWidth: true }

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
              onClicked: if (root.service) root.service.chooseAndImportFile()
            }
          }
        }

        // Follow Mode Active Banner
        Rectangle {
          visible: root.service && root.service.mode === "follow-omarchy"
          width: parent.width
          height: Style.space(32)
          radius: Style.cornerRadius
          color: Style.alpha(Color.accent, 0.12)
          border.color: Style.alpha(Color.accent, 0.3)
          border.width: 1

          Row {
            anchors.fill: parent
            anchors.leftMargin: Style.space(12)
            anchors.rightMargin: Style.space(12)
            spacing: Style.space(8)

            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: "󰉼 Active Omarchy Theme:"
              color: Color.accent
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              font.bold: true
            }

            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: root.service ? root.service.currentOmarchyThemeDisplay : ""
              color: Color.popups.text
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              font.bold: true
            }

            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: "→ Click any cursor below to set mapping"
              color: Color.muted
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
            }
          }
        }

        // Error message banner
        Text {
          visible: root.service && root.service.lastError !== ""
          width: parent.width
          text: root.service ? root.service.lastError : ""
          color: Color.urgent
          font.family: Style.font.family
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.WordWrap
        }

        // Main Cursor Grid
        CursorGrid {
          id: grid
          width: parent.width
          height: parent.height - y - bottomBar.implicitHeight - parent.spacing
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
            if (hovered) {
              root.themeIndex = index
              root.focusSection = "themes"
            }
          }
        }

        // Bottom Controls Bar (Sizes + Actions)
        Row {
          id: bottomBar
          width: parent.width
          spacing: Style.space(16)

          Row {
            id: sizeRow
            spacing: Style.space(12)
            anchors.verticalCenter: parent.verticalCenter

            Text {
              anchors.verticalCenter: parent.verticalCenter
              text: "CURSOR SIZE"
              color: Color.muted
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              font.bold: true
            }

            SizeSelector {
              id: sizeSelector
              anchors.verticalCenter: parent.verticalCenter
              sizes: root.service ? root.service.sizes : []
              committedSize: root.service ? root.service.committedSize : 16
              cursorActive: root.focusSection === "sizes"
              onSizeActivated: function(size) {
                root.focusSection = "sizes"
                root.service.commitSize(size)
              }
            }
          }

          Item { width: Style.space(10); height: 1 }

          // Remove button for selected imported theme
          Rectangle {
            id: removeBtn
            property var curTheme: (root.service && root.service.themes) ? root.service.themes[root.themeIndex] : null
            visible: curTheme && (curTheme.imported === true || curTheme.sourceType === "imported")
            anchors.verticalCenter: parent.verticalCenter
            height: Style.space(28)
            radius: Style.cornerRadius - 2
            color: removeMouse.containsMouse ? Style.alpha(Color.urgent, 0.25) : Style.alpha(Color.urgent, 0.12)
            border.color: Style.alpha(Color.urgent, 0.4)
            border.width: 1
            implicitWidth: removeLabel.implicitWidth + Style.space(16)

            Row {
              id: removeLabel
              anchors.centerIn: parent
              spacing: Style.space(4)
              Text {
                text: "󰆴"
                color: Color.urgent
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
              }
              Text {
                text: "Remove Theme"
                color: Color.urgent
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                font.bold: true
              }
            }

            MouseArea {
              id: removeMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: {
                if (root.service && removeBtn.curTheme) {
                  root.service.removeImportedTheme(removeBtn.curTheme)
                }
              }
            }
          }

          Item { width: 1; height: 1; Layout.fillWidth: true }

          // Status text / hint
          Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.service ? root.service.statusText : ""
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
          }
        }
      }
    }
  }
}
