import QtQuick
import QtQuick.Controls
import qs.Commons
import "../CursorModel.js" as Model

Item {
  id: root
  property var theme: null
  property int committedSize: 16
  property var previewRoles: ({})
  property bool sizeCursorActive: false

  signal sizeActivated(int size)
  signal openFolderRequested(var theme)
  signal renameThemeRequested(var theme)
  signal removeThemeRequested(var theme)

  readonly property var visibleRoles: {
    if (!previewRoles || typeof previewRoles !== "object") return []
    var list = []
    var roleDefs = [
      { key: "default", label: "Default" },
      { key: "pointer", label: "Pointer" },
      { key: "text",    label: "Text" },
      { key: "move",    label: "Move" },
      { key: "resize",  label: "Resize" },
      { key: "wait",    label: "Wait" }
    ]
    var metaObj = previewRoles._meta || {}
    for (var i = 0; i < roleDefs.length; i++) {
      var def = roleDefs[i]
      var p = previewRoles[def.key]
      if (p && typeof p === "string" && p.length > 0) {
        var meta = metaObj[def.key] || {}
        list.push({
          key: def.key,
          label: meta.label || def.label,
          path: p,
          hotspotX: meta.hotspot_x !== undefined ? Number(meta.hotspot_x) : -1.0,
          hotspotY: meta.hotspot_y !== undefined ? Number(meta.hotspot_y) : -1.0
        })
      }
    }
    return list
  }

  Flickable {
    id: flickable
    anchors.fill: parent
    contentWidth: width
    contentHeight: contentCol.implicitHeight
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    flickableDirection: Flickable.VerticalFlick
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    Column {
      id: contentCol
      width: parent.width
      spacing: Style.space(14)

      // Right Header: Preview Title
      Text {
        text: "Cursor Theme Preview"
        textFormat: Text.PlainText
        color: Color.popups.text
        font.family: Style.font.family
        font.pixelSize: Style.font.title
        font.bold: true
      }

      // Responsive Role Preview Container Box
      Rectangle {
        id: previewContainer
        width: parent.width
        implicitHeight: roleGrid.implicitHeight + paddingVertical * 2
        height: implicitHeight
        radius: Style.cornerRadius
        color: Util.alpha(Color.popups.text, 0.04)
        border.color: Util.alpha(Color.popups.text, 0.12)
        border.width: 1

        readonly property real paddingHorizontal: Style.space(16)
        readonly property real paddingVertical: Style.space(14)
        readonly property real cardWidth: Style.space(72)
        readonly property real cardHeight: Style.space(72)
        readonly property real columnSpacing: Style.space(14)
        readonly property real rowSpacing: Style.space(12)

        readonly property int columns: Model.previewColumns(width, cardWidth, columnSpacing, paddingHorizontal, root.visibleRoles.length)

        Grid {
          id: roleGrid
          anchors.centerIn: parent
          columns: previewContainer.columns
          columnSpacing: previewContainer.columnSpacing
          rowSpacing: previewContainer.rowSpacing

          Repeater {
            model: root.visibleRoles
            delegate: Column {
              id: roleCol
              required property int index
              required property var modelData

              spacing: Style.space(6)
              width: previewContainer.cardWidth

              Rectangle {
                id: iconBox
                width: previewContainer.cardWidth
                height: previewContainer.cardHeight
                radius: Style.cornerRadius - 2
                color: roleMouse.containsMouse ? Util.alpha(Color.accent, 0.12) : Util.alpha(Color.popups.text, 0.05)
                border.color: roleMouse.containsMouse ? Color.accent : Util.alpha(Color.popups.text, 0.14)
                border.width: 1

                Item {
                  id: imageBox
                  anchors.centerIn: parent
                  width: Style.space(48)
                  height: Style.space(48)

                  Image {
                    id: roleImg
                    anchors.fill: parent
                    source: roleCol.modelData.path !== "" ? "file://" + roleCol.modelData.path : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    smooth: true
                    visible: source !== ""
                  }

                  // Understated Hotspot Indicator
                  Rectangle {
                    visible: roleMouse.containsMouse && roleCol.modelData.hotspotX >= 0 && roleCol.modelData.hotspotY >= 0
                    x: Math.round(roleCol.modelData.hotspotX * parent.width) - width / 2
                    y: Math.round(roleCol.modelData.hotspotY * parent.height) - height / 2
                    width: 5
                    height: 5
                    radius: 2.5
                    color: Color.accent
                    border.color: Color.popups.background
                    border.width: 1
                    z: 10
                  }
                }

                MouseArea {
                  id: roleMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                }
              }

              Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: roleCol.modelData.label
                textFormat: Text.PlainText
                color: roleMouse.containsMouse ? Color.accent : Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                font.bold: roleMouse.containsMouse
              }
            }
          }
        }
      }

      // Size Stepper Control
      SizeStepper {
        committedSize: root.committedSize
        cursorActive: root.sizeCursorActive
        onSizeActivated: function(size) { root.sizeActivated(size) }
      }

      // Compact Metadata / Details Card
      Rectangle {
        id: detailsCard
        width: parent.width
        implicitHeight: detailsCol.implicitHeight + Style.space(20)
        height: implicitHeight
        radius: Style.cornerRadius
        color: Util.alpha(Color.popups.text, 0.03)
        border.color: Util.alpha(Color.popups.text, 0.1)
        border.width: 1

        Column {
          id: detailsCol
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.top: parent.top
          anchors.margins: Style.space(10)
          spacing: Style.space(6)

          // Line 1: Title & Author / Subtitle
          Row {
            width: parent.width
            spacing: Style.space(8)

            Text {
              text: root.theme ? (root.theme.displayName || root.theme.id || "") : "No theme selected"
              textFormat: Text.PlainText
              color: Color.popups.text
              font.family: Style.font.family
              font.pixelSize: Style.font.body
              font.bold: true
              elide: Text.ElideRight
            }

            Text {
              readonly property string cleanSubtitle: {
                if (!root.theme || !root.theme.subtitle) return ""
                var s = String(root.theme.subtitle).trim()
                if (s === "Unknown" || s === "Imported • Unknown" || s === "System • Unknown" || s === "Imported") return ""
                if (s.indexOf("Imported • ") === 0) {
                  var rest = s.substring(11).trim()
                  return rest === "Unknown" ? "" : rest
                }
                return s
              }
              visible: cleanSubtitle.length > 0
              anchors.verticalCenter: parent.verticalCenter
              text: "• " + cleanSubtitle
              textFormat: Text.PlainText
              color: Color.muted
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              elide: Text.ElideRight
            }
          }

          // Line 2: Format Badges & Context Menu
          Item {
            width: parent.width
            height: Style.space(22)

            // Format Badges on left
            Row {
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(6)

              Repeater {
                model: root.theme && root.theme.formats ? root.theme.formats : ["xcursor"]
                Rectangle {
                  required property var modelData
                  height: Style.space(20)
                  radius: Style.space(3)
                  color: Util.alpha(Color.popups.text, 0.06)
                  border.color: Util.alpha(Color.popups.text, 0.16)
                  border.width: 1
                  implicitWidth: fmtLabel.implicitWidth + Style.space(10)

                  Text {
                    id: fmtLabel
                    anchors.centerIn: parent
                    text: modelData === "hyprcursor" ? "Hyprcursor" : "XCursor"
                    textFormat: Text.PlainText
                    color: Color.popups.text
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption - 2
                  }
                }
              }
            }

            // Context Action Menu Button [⋯] (For Imported Themes)
            Rectangle {
              id: contextBtn
              visible: Boolean(root.theme && (root.theme.imported === true || root.theme.sourceType === "imported"))
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              height: Style.space(20)
              width: Style.space(24)
              radius: Style.space(3)
              color: contextMouse.containsMouse ? Util.alpha(Color.accent, 0.2) : Util.alpha(Color.popups.text, 0.08)
              border.color: Util.alpha(Color.popups.text, 0.18)
              border.width: 1

              Text {
                anchors.centerIn: parent
                text: "⋯"
                textFormat: Text.PlainText
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                font.bold: true
              }

              MouseArea {
                id: contextMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: contextMenu.open()
              }

              Menu {
                id: contextMenu
                y: contextBtn.height + 4
                MenuItem {
                  text: "Open folder"
                  onTriggered: if (root.theme) root.openFolderRequested(root.theme)
                }
                MenuItem {
                  text: "Rename"
                  onTriggered: if (root.theme) root.renameThemeRequested(root.theme)
                }
                MenuItem {
                  text: "Remove"
                  onTriggered: if (root.theme) root.removeThemeRequested(root.theme)
                }
              }
            }
          }
        }
      }
    }
  }
}
