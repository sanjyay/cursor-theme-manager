import QtQuick
import QtQuick.Controls
import qs.Commons
import "../CursorModel.js" as Model

Item {
  id: root

  property var service: null
  property bool active: false
  property var selectedEntry: null
  property string modalError: ""
  property int selectedIndex: -1

  signal closed()

  visible: opacity > 0
  opacity: active ? 1.0 : 0.0
  Behavior on opacity {
    NumberAnimation { duration: 140; easing.type: Easing.OutQuad }
  }

  readonly property var shortcuts: [
    { label: "Downloads", path: "~/Downloads", icon: "󰉍" },
    { label: "Home", path: "~", icon: "󰋜" },
    { label: "User Cursors", path: "~/.local/share/icons", icon: "󰆧" },
    { label: "Legacy Cursors", path: "~/.icons", icon: "󰆧" },
    { label: "System", path: "/usr/share/icons", icon: "󰒋" }
  ]

  function open() {
    selectedEntry = null
    selectedIndex = -1
    modalError = ""
    active = true
    if (service) {
      service.browseDirectory(service.browserPath || "~/Downloads")
    }
    Qt.callLater(function() {
      importScope.forceActiveFocus()
    })
  }

  function close() {
    active = false
    selectedEntry = null
    selectedIndex = -1
    modalError = ""
    root.closed()
  }

  function importCurrent() {
    if (!selectedEntry || !service) return
    if (selectedEntry.is_archive || selectedEntry.is_theme_dir) {
      modalError = ""
      service.importTheme(selectedEntry.path)
    } else if (selectedEntry.is_dir) {
      service.browseDirectory(selectedEntry.path)
      selectedEntry = null
      selectedIndex = -1
    }
  }

  Connections {
    target: root.service
    function onImportCompleted(theme, message) {
      root.close()
    }
    function onImportFailed(error) {
      root.modalError = Model.sanitizeString(error, 256) || "Failed to import cursor theme"
    }
    function onBrowserEntriesChanged() {
      root.selectedEntry = null
      root.selectedIndex = -1
    }
  }

  // Backdrop Dimming
  Rectangle {
    anchors.fill: parent
    color: Util.alpha("#000000", 0.65)

    MouseArea {
      anchors.fill: parent
      onClicked: root.close()
    }
  }

  FocusScope {
    id: importScope
    anchors.fill: parent
    focus: true

    Keys.onEscapePressed: function(event) {
      event.accepted = true
      root.close()
    }

    Keys.onReturnPressed: function(event) {
      event.accepted = true
      root.importCurrent()
    }

    Keys.onUpPressed: function(event) {
      event.accepted = true
      if (fileListView.count > 0) {
        var next = Math.max(0, root.selectedIndex - 1)
        root.selectedIndex = next
        root.selectedEntry = fileListView.model[next]
        fileListView.positionViewAtIndex(next, ListView.Contain)
      }
    }

    Keys.onDownPressed: function(event) {
      event.accepted = true
      if (fileListView.count > 0) {
        var next = Math.min(fileListView.count - 1, root.selectedIndex + 1)
        root.selectedIndex = next
        root.selectedEntry = fileListView.model[next]
        fileListView.positionViewAtIndex(next, ListView.Contain)
      }
    }

    Keys.onPressed: function(event) {
      if (event.key === Qt.Key_Backspace) {
        event.accepted = true
        if (root.service && root.service.browserCanGoUp) {
          root.service.browseDirectory(root.service.browserParent)
        }
      }
    }

    // Modal Dialog Box
    Rectangle {
      id: dialogBox
      anchors.centerIn: parent
      width: Math.min(parent.width - Style.space(24), Style.space(680))
      height: Math.min(parent.height - Style.space(24), Style.space(450))
      radius: Style.cornerRadius
      color: Color.popups.background
      border.color: Color.popups.border
      border.width: 1
      clip: true

      MouseArea {
        anchors.fill: parent
      }

      Column {
        anchors.fill: parent
        anchors.margins: Style.space(16)
        spacing: Style.space(12)

        // ── 1. Dialog Header ───────────────────────────────────────────────
        Item {
          width: parent.width
          height: Style.space(28)

          Row {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(8)

            Text {
              text: "󰋺"
              textFormat: Text.PlainText
              color: Color.accent
              font.family: Style.font.family
              font.pixelSize: Style.font.title
            }

            Text {
              text: "Import Cursor Theme"
              textFormat: Text.PlainText
              color: Color.popups.text
              font.family: Style.font.family
              font.pixelSize: Style.font.title
              font.bold: true
            }
          }

          // Close "✕" Button
          Rectangle {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: Style.space(26)
            height: Style.space(26)
            radius: width / 2
            color: closeMouse.containsMouse ? Util.alpha(Color.popups.text, 0.12) : "transparent"

            Text {
              anchors.centerIn: parent
              text: "✕"
              textFormat: Text.PlainText
              color: Color.muted
              font.family: Style.font.family
              font.pixelSize: Style.font.bodySmall
            }

            MouseArea {
              id: closeMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.close()
            }
          }
        }

        // Divider
        Rectangle {
          width: parent.width
          height: 1
          color: Util.alpha(Color.popups.text, 0.08)
        }

        // ── 2. Two-Column Split (Shortcuts vs File Browser) ────────────────
        Item {
          width: parent.width
          height: parent.height - Style.space(130)

          // Left Shortcuts Sidebar
          Item {
            id: shortcutsPane
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            width: Math.max(Style.space(110), Math.min(Style.space(150), Math.round(parent.width * 0.25)))

            Column {
              anchors.fill: parent
              spacing: Style.space(4)

              Text {
                text: "PLACES"
                textFormat: Text.PlainText
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.caption - 1
                font.bold: true
                bottomPadding: Style.space(4)
              }

              Repeater {
                model: root.shortcuts

                Rectangle {
                  required property var modelData
                  required property int index

                  width: parent.width
                  height: Style.space(30)
                  radius: Style.cornerRadius - 2

                  readonly property bool isCurrent: root.service && (root.service.browserPath === modelData.path || (modelData.path === "~/Downloads" && root.service.browserPath.indexOf("/Downloads") !== -1) || (modelData.path === "~/.local/share/icons" && root.service.browserPath.indexOf(".local/share/icons") !== -1))

                  color: isCurrent
                    ? Style.selectedFillFor(Color.popups.text, Color.accent)
                    : (placeMouse.containsMouse ? Style.hoverFillFor(Color.popups.text, Color.accent) : "transparent")
                  border.color: isCurrent ? Color.accent : "transparent"
                  border.width: 1

                  Row {
                    anchors.fill: parent
                    anchors.leftMargin: Style.space(8)
                    anchors.rightMargin: Style.space(8)
                    spacing: Style.space(6)

                    Text {
                      anchors.verticalCenter: parent.verticalCenter
                      text: modelData.icon
                      textFormat: Text.PlainText
                      color: isCurrent ? Color.accent : Color.muted
                      font.family: Style.font.family
                      font.pixelSize: Style.font.bodySmall
                    }

                    Text {
                      anchors.verticalCenter: parent.verticalCenter
                      width: parent.width - Style.space(24)
                      text: modelData.label
                      textFormat: Text.PlainText
                      color: isCurrent ? Color.popups.text : (placeMouse.containsMouse ? Color.popups.text : Color.muted)
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                      font.bold: isCurrent
                      elide: Text.ElideRight
                    }
                  }

                  MouseArea {
                    id: placeMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      if (root.service) {
                        root.service.browseDirectory(modelData.path)
                      }
                    }
                  }
                }
              }
            }
          }

          // Vertical Separator
          Rectangle {
            id: splitDivider
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.left: shortcutsPane.right
            anchors.leftMargin: Style.space(10)
            width: 1
            color: Util.alpha(Color.popups.text, 0.08)
          }

          // Right File Explorer Pane
          Item {
            id: filePane
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.left: splitDivider.right
            anchors.leftMargin: Style.space(10)
            anchors.right: parent.right

            // Breadcrumbs & Up Toolbar
            Item {
              id: navBar
              anchors.top: parent.top
              anchors.left: parent.left
              anchors.right: parent.right
              height: Style.space(32)

              // Up button [⏶]
              Rectangle {
                id: upBtn
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: Style.space(32)
                height: Style.space(28)
                radius: Style.cornerRadius - 2
                enabled: Boolean(root.service && root.service.browserCanGoUp)
                opacity: enabled ? 1.0 : 0.35
                color: upMouse.containsMouse && enabled ? Style.hoverFillFor(Color.popups.text, Color.accent) : Util.alpha(Color.popups.text, 0.06)
                border.color: Util.alpha(Color.popups.text, 0.12)
                border.width: 1

                Text {
                  anchors.centerIn: parent
                  text: "󰁝"
                  textFormat: Text.PlainText
                  color: Color.popups.text
                  font.family: Style.font.family
                  font.pixelSize: Style.font.body
                }

                MouseArea {
                  id: upMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: upBtn.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                  onClicked: {
                    if (root.service && root.service.browserCanGoUp) {
                      root.service.browseDirectory(root.service.browserParent)
                    }
                  }
                }
              }

              // Path display / Breadcrumbs container
              Rectangle {
                anchors.left: upBtn.right
                anchors.leftMargin: Style.space(6)
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                height: Style.space(28)
                radius: Style.cornerRadius - 2
                color: Util.alpha(Color.popups.text, 0.04)
                border.color: Util.alpha(Color.popups.text, 0.1)
                border.width: 1
                clip: true

                Flickable {
                  anchors.fill: parent
                  anchors.leftMargin: Style.space(8)
                  anchors.rightMargin: Style.space(8)
                  contentWidth: breadcrumbRow.implicitWidth
                  contentHeight: height
                  boundsBehavior: Flickable.StopAtBounds
                  flickableDirection: Flickable.HorizontalFlick

                  Row {
                    id: breadcrumbRow
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Style.space(4)

                    Repeater {
                      model: root.service ? root.service.browserBreadcrumbs : []

                      Row {
                        required property var modelData
                        required property int index

                        spacing: Style.space(4)

                        Rectangle {
                          height: Style.space(20)
                          radius: Style.cornerRadius - 3
                          color: crumbMouse.containsMouse ? Util.alpha(Color.accent, 0.2) : "transparent"
                          implicitWidth: crumbText.implicitWidth + Style.space(8)

                          Text {
                            id: crumbText
                            anchors.centerIn: parent
                            text: modelData.name || ""
                            textFormat: Text.PlainText
                            color: crumbMouse.containsMouse ? Color.accent : Color.popups.text
                            font.family: Style.font.family
                            font.pixelSize: Style.font.caption
                            font.bold: true
                          }

                          MouseArea {
                            id: crumbMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                              if (root.service) root.service.browseDirectory(modelData.path)
                            }
                          }
                        }

                        Text {
                          visible: index < (root.service ? root.service.browserBreadcrumbs.length - 1 : 0)
                          anchors.verticalCenter: parent.verticalCenter
                          text: "/"
                          textFormat: Text.PlainText
                          color: Color.muted
                          font.family: Style.font.family
                          font.pixelSize: Style.font.caption
                        }
                      }
                    }
                  }
                }
              }
            }

            // Entries List
            Rectangle {
              anchors.top: navBar.bottom
              anchors.topMargin: Style.space(6)
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.bottom: parent.bottom
              radius: Style.cornerRadius - 2
              color: Util.alpha(Color.popups.text, 0.02)
              border.color: Util.alpha(Color.popups.text, 0.1)
              border.width: 1
              clip: true

              ListView {
                id: fileListView
                anchors.fill: parent
                anchors.margins: 2
                model: root.service ? root.service.browserEntries : []
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Rectangle {
                  id: fileRow
                  required property var modelData
                  required property int index

                  readonly property bool isSelected: root.selectedIndex === index || (root.selectedEntry && root.selectedEntry.path === modelData.path)

                  width: fileListView.width
                  height: Style.space(32)
                  radius: Style.cornerRadius - 2
                  color: isSelected
                    ? Style.selectedFillFor(Color.popups.text, Color.accent)
                    : (rowMouse.containsMouse ? Style.hoverFillFor(Color.popups.text, Color.accent) : "transparent")
                  border.color: isSelected ? Color.accent : "transparent"
                  border.width: 1

                  Row {
                    anchors.fill: parent
                    anchors.leftMargin: Style.space(8)
                    anchors.rightMargin: Style.space(8)
                    spacing: Style.space(8)

                    // Icon
                    Text {
                      anchors.verticalCenter: parent.verticalCenter
                      text: modelData.is_theme_dir ? "🎨" : (modelData.is_archive ? "📦" : "📁")
                      textFormat: Text.PlainText
                      font.pixelSize: Style.font.bodySmall
                    }

                    // Name
                    Text {
                      anchors.verticalCenter: parent.verticalCenter
                      width: Math.max(1, parent.width - Style.space(120))
                      text: modelData.name || ""
                      textFormat: Text.PlainText
                      color: isSelected ? Color.popups.text : (rowMouse.containsMouse ? Color.popups.text : (modelData.is_theme_dir || modelData.is_archive ? Color.popups.text : Color.muted))
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption
                      font.bold: isSelected || modelData.is_theme_dir
                      elide: Text.ElideRight
                      maximumLineCount: 1
                    }

                    // Theme Badge
                    Rectangle {
                      visible: Boolean(modelData.is_theme_dir)
                      anchors.verticalCenter: parent.verticalCenter
                      height: Style.space(18)
                      radius: Style.cornerRadius - 3
                      color: Util.alpha(Color.accent, 0.25)
                      border.color: Util.alpha(Color.accent, 0.6)
                      border.width: 1
                      implicitWidth: themeBadgeText.implicitWidth + Style.space(8)

                      Text {
                        id: themeBadgeText
                        anchors.centerIn: parent
                        text: "Theme"
                        textFormat: Text.PlainText
                        color: Color.accent
                        font.family: Style.font.family
                        font.pixelSize: Style.font.caption - 2
                        font.bold: true
                      }
                    }

                    // Size / Type label
                    Text {
                      anchors.verticalCenter: parent.verticalCenter
                      text: modelData.size_str || ""
                      textFormat: Text.PlainText
                      color: Color.muted
                      font.family: Style.font.family
                      font.pixelSize: Style.font.caption - 1
                    }
                  }

                  MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      root.selectedIndex = index
                      root.selectedEntry = modelData
                    }
                    onDoubleClicked: {
                      root.selectedIndex = index
                      root.selectedEntry = modelData
                      root.importCurrent()
                    }
                  }
                }

                // Empty folder hint
                Text {
                  visible: fileListView.count === 0 && !(root.service && root.service.browserLoading)
                  anchors.centerIn: parent
                  text: (root.service && root.service.browserError) ? root.service.browserError : "No cursor archives or folders found"
                  textFormat: Text.PlainText
                  color: Color.muted
                  font.family: Style.font.family
                  font.pixelSize: Style.font.bodySmall
                }
              }
            }
          }
        }

        // Divider
        Rectangle {
          width: parent.width
          height: 1
          color: Util.alpha(Color.popups.text, 0.08)
        }

        // ── 3. Footer Toolbar & Error Display ──────────────────────────────
        Item {
          width: parent.width
          height: Style.space(36)

          // Info / Error text on left
          Row {
            anchors.left: parent.left
            anchors.right: buttonRow.left
            anchors.rightMargin: Style.space(12)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(6)

            Text {
              visible: root.modalError !== ""
              text: "⚠"
              textFormat: Text.PlainText
              color: Color.urgent
              font.pixelSize: Style.font.bodySmall
            }

            Text {
              width: parent.width - 24
              text: root.modalError !== ""
                ? root.modalError
                : "Supported: *.tar.gz, *.tar.xz, *.tar.bz2, *.zip, and cursor folders"
              textFormat: Text.PlainText
              color: root.modalError !== "" ? Color.urgent : Color.muted
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              font.bold: root.modalError !== ""
              elide: Text.ElideRight
              maximumLineCount: 1
            }
          }

          // Action Buttons on right
          Row {
            id: buttonRow
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(8)

            // Cancel Button
            Rectangle {
              width: cancelLabel.implicitWidth + Style.space(20)
              height: Style.space(32)
              radius: Style.cornerRadius - 2
              color: cancelMouse.containsMouse ? Util.alpha(Color.popups.text, 0.12) : Util.alpha(Color.popups.text, 0.06)
              border.color: Util.alpha(Color.popups.text, 0.14)
              border.width: 1

              Text {
                id: cancelLabel
                anchors.centerIn: parent
                text: "Cancel"
                textFormat: Text.PlainText
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                font.bold: true
              }

              MouseArea {
                id: cancelMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.close()
              }
            }

            // Import Button
            Rectangle {
              id: importBtn
              readonly property bool canImport: Boolean(root.selectedEntry && (root.selectedEntry.is_archive || root.selectedEntry.is_theme_dir) && !(root.service && root.service.importing))

              width: importBtnLabel.implicitWidth + Style.space(20)
              height: Style.space(32)
              radius: Style.cornerRadius - 2
              opacity: canImport ? 1.0 : 0.45
              color: canImport && importBtnMouse.containsMouse ? Color.accent : (canImport ? Util.alpha(Color.accent, 0.85) : Util.alpha(Color.popups.text, 0.08))
              border.color: canImport ? Color.accent : "transparent"
              border.width: 1

              Row {
                id: importBtnLabel
                anchors.centerIn: parent
                spacing: Style.space(6)

                Text {
                  text: root.service && root.service.importing ? "…" : "󰋺"
                  textFormat: Text.PlainText
                  color: importBtn.canImport ? Color.popups.background : Color.muted
                  font.family: Style.font.family
                  font.pixelSize: Style.font.bodySmall
                }

                Text {
                  text: root.service && root.service.importing ? "Importing…" : "Import"
                  textFormat: Text.PlainText
                  color: importBtn.canImport ? Color.popups.background : Color.muted
                  font.family: Style.font.family
                  font.pixelSize: Style.font.bodySmall
                  font.bold: true
                }
              }

              MouseArea {
                id: importBtnMouse
                anchors.fill: parent
                enabled: importBtn.canImport
                hoverEnabled: true
                cursorShape: importBtn.canImport ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: root.importCurrent()
              }
            }
          }
        }
      }
    }
    // Loading Overlay inside ImportDialog
    Rectangle {
      id: loadingOverlay
      anchors.fill: dialogBox
      radius: Style.cornerRadius
      color: Util.alpha(Color.popups.background, 0.94)
      border.color: Color.popups.border
      border.width: 1
      visible: opacity > 0
      opacity: (root.service && root.service.importing) ? 1.0 : 0.0
      Behavior on opacity { NumberAnimation { duration: 150 } }
      z: 100

      MouseArea {
        anchors.fill: parent
      }

      Column {
        anchors.centerIn: parent
        spacing: Style.space(16)

        Item {
          anchors.horizontalCenter: parent.horizontalCenter
          width: Style.space(48)
          height: Style.space(48)

          Text {
            id: spinnerIcon
            anchors.centerIn: parent
            text: "󰑮"
            textFormat: Text.PlainText
            color: Color.accent
            font.family: Style.font.family
            font.pixelSize: Style.space(36)

            RotationAnimation on rotation {
              loops: Animation.Infinite
              from: 0
              to: 360
              duration: 1100
              running: loadingOverlay.visible
            }
          }
        }

        Column {
          anchors.horizontalCenter: parent.horizontalCenter
          spacing: Style.space(6)

          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Importing Cursor Theme…"
            textFormat: Text.PlainText
            color: Color.popups.text
            font.family: Style.font.family
            font.pixelSize: Style.font.title
            font.bold: true
          }

          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: (root.service && root.service.importTargetName) ? root.service.importTargetName : "Extracting and preparing cursor files…"
            textFormat: Text.PlainText
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            elide: Text.ElideRight
            maximumLineCount: 1
          }
        }
      }
    }
  }
}
