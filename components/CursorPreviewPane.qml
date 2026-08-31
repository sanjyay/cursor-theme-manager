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
  signal removeThemeRequested(var theme)

  readonly property var roleList: [
    { key: "default", label: "Default" },
    { key: "pointer", label: "Pointer" },
    { key: "text",    label: "Text" },
    { key: "move",    label: "Move" },
    { key: "resize",  label: "Resize" },
    { key: "wait",    label: "Wait" }
  ]

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
      spacing: Style.space(16)

      // Right Header: Preview Title
      Text {
        text: "Cursor Theme Preview"
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

        readonly property int columns: Model.previewColumns(width, cardWidth, columnSpacing, paddingHorizontal)

        Grid {
          id: roleGrid
          anchors.centerIn: parent
          columns: previewContainer.columns
          columnSpacing: previewContainer.columnSpacing
          rowSpacing: previewContainer.rowSpacing

          Repeater {
            model: root.roleList
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
                color: roleMouse.containsMouse ? Util.alpha(Color.accent, 0.12) : Util.alpha(Color.popups.text, 0.06)
                border.color: roleMouse.containsMouse ? Color.accent : Util.alpha(Color.popups.text, 0.14)
                border.width: 1

                readonly property string rolePath: root.previewRoles ? String(root.previewRoles[roleCol.modelData.key] || "") : ""
                readonly property string effectivePath: rolePath

                Image {
                  id: roleImg
                  anchors.centerIn: parent
                  width: Style.space(48)
                  height: Style.space(48)
                  source: iconBox.effectivePath !== "" ? "file://" + iconBox.effectivePath : ""
                  fillMode: Image.PreserveAspectFit
                  asynchronous: true
                  smooth: true
                  visible: source !== ""
                }

                Text {
                  visible: !roleImg.visible
                  anchors.centerIn: parent
                  text: "—"
                  color: Color.muted
                  font.family: Style.font.family
                  font.pixelSize: Style.font.body
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

      // Metadata / Details Card
      Rectangle {
        id: detailsCard
        width: parent.width
        implicitHeight: detailsCol.implicitHeight + Style.space(24)
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
          anchors.margins: Style.space(12)
          spacing: Style.space(8)

          Item {
            width: parent.width
            height: Style.space(26)

            Row {
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              spacing: Style.space(8)

              Text {
                text: root.theme ? (root.theme.displayName || root.theme.id) : "No theme selected"
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.body
                font.bold: true
              }

              Text {
                visible: Boolean(root.theme && root.theme.subtitle)
                text: "•  " + (root.theme ? root.theme.subtitle : "")
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
              }
            }

            // Remove Button for Imported themes
            Rectangle {
              id: removeBtn
              visible: Boolean(root.theme && (root.theme.imported === true || root.theme.sourceType === "imported"))
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              height: Style.space(26)
              radius: Style.cornerRadius - 2
              color: removeMouse.containsMouse ? Util.alpha(Color.urgent, 0.25) : Util.alpha(Color.urgent, 0.12)
              border.color: Util.alpha(Color.urgent, 0.4)
              border.width: 1
              implicitWidth: removeLabel.implicitWidth + Style.space(14)

              Row {
                id: removeLabel
                anchors.centerIn: parent
                spacing: Style.space(4)
                Text {
                  text: "󰆴"
                  color: Color.urgent
                  font.family: Style.font.family
                  font.pixelSize: Style.font.caption
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
                  if (root.theme) root.removeThemeRequested(root.theme)
                }
              }
            }
          }

          // Details items
          Row {
            spacing: Style.space(24)

            Column {
              spacing: Style.space(2)
              Text {
                text: "Format"
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.caption - 1
              }
              Text {
                text: root.theme ? (root.theme.formats && root.theme.formats.length === 2 ? "Hyprcursor + XCursor" : (root.theme.formats && root.theme.formats[0] === "hyprcursor" ? "Hyprcursor" : "XCursor")) : "—"
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
              }
            }

            Column {
              spacing: Style.space(2)
              Text {
                text: "Source"
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.caption - 1
              }
              Text {
                text: root.theme ? (root.theme.imported ? "Imported locally" : (root.theme.bundled ? "Bundled" : "System")) : "—"
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
              }
            }

            Column {
              visible: Boolean(root.theme && root.theme.license && root.theme.license !== "Unknown")
              spacing: Style.space(2)
              Text {
                text: "License"
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.caption - 1
              }
              Text {
                text: root.theme ? root.theme.license : "—"
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
              }
            }
          }
        }
      }
    }
  }
}
