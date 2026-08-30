import QtQuick
import QtQuick.Controls
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
    if (shell && typeof shell.hide === "function") shell.hide("goblin.cursor-switcher")
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
      var theme = null
      for (var i = 0; service && i < service.themes.length; i++) {
        var candidate = service.themes[i]
        if (candidate.hyprcursor === requested.theme || candidate.xcursor === requested.theme) { theme = candidate; break }
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
        theme = null
        for (var i = 0; i < service.themes.length; i++) {
          var candidate = service.themes[i]
          if (candidate.hyprcursor === requested.theme || candidate.xcursor === requested.theme) { theme = candidate; break }
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
    title: "Cursor"
    color: Color.popups.background
    implicitWidth: Math.min(Style.space(620), 760)
    implicitHeight: Math.min(Style.space(560), 700)
    minimumSize: Qt.size(Math.min(Style.space(500), 560), Math.min(Style.space(420), 480))

    onVisibleChanged: {
      if (!visible && !root.closingFromHost) {
        if (root.service) root.service.cancelPreview()
        if (root.shell && typeof root.shell.hide === "function") root.shell.hide("goblin.cursor-switcher")
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
      onTextKey: function(text) { if (text === "r" || text === "R") root.service.refresh(true) }

      Column {
        anchors.fill: parent
        anchors.margins: Style.space(22)
        spacing: Style.space(12)

        Item {
          width: parent.width
          height: Math.max(title.implicitHeight, active.implicitHeight)
          Text {
            id: title
            anchors.left: parent.left
            text: "Cursor"
            color: Color.popups.text
            font.family: Style.font.family
            font.pixelSize: Style.font.title
            font.bold: true
          }
          Text {
            id: active
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: root.service && root.service.committedTheme
              ? root.service.committedTheme.displayName + "  ·  " + root.service.committedSize
              : "Loading…"
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
          }
        }

        Text {
          visible: root.service && root.service.lastError !== ""
          width: parent.width
          text: root.service ? root.service.lastError : ""
          color: Color.urgent
          font.family: Style.font.family
          font.pixelSize: Style.font.bodySmall
          wrapMode: Text.WordWrap
        }

        CursorGrid {
          id: grid
          width: parent.width
          height: parent.height - y - sizeRow.implicitHeight - footer.implicitHeight - parent.spacing * 2
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

        Row {
          id: sizeRow
          spacing: Style.space(16)
          anchors.left: parent.left

          Text {
            id: sizesHeader
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

        Item {
          id: footer
          width: parent.width
          implicitHeight: Math.max(status.implicitHeight, hint.implicitHeight)
          Text {
            id: status
            anchors.left: parent.left
            text: root.service ? root.service.statusText : "Service unavailable"
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
          }
          Text {
            id: hint
            anchors.right: parent.right
            text: "Arrows navigate  ·  Tab switches  ·  Enter applies  ·  Esc closes"
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
          }
        }
      }
    }
  }
}
