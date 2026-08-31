import QtQuick
import QtQuick.Controls
import qs.Commons

Item {
  id: root
  property var service: null
  property var theme: null
  property bool active: false
  property string errorMessage: ""

  signal closed()

  visible: opacity > 0
  opacity: active ? 1.0 : 0.0
  Behavior on opacity { NumberAnimation { duration: 120 } }

  function open(targetTheme) {
    theme = targetTheme
    nameInput.text = targetTheme ? (targetTheme.displayName || targetTheme.id) : ""
    errorMessage = ""
    active = true
    Qt.callLater(function() {
      nameInput.forceActiveFocus()
      nameInput.selectAll()
    })
  }

  function close() {
    active = false
    theme = null
    errorMessage = ""
    root.closed()
  }

  function submit() {
    var newName = nameInput.text.trim()
    if (!newName) {
      errorMessage = "Theme name cannot be empty"
      return
    }
    if (newName.length > 100) {
      errorMessage = "Theme name is too long"
      return
    }
    if (!theme || !service) return
    service.renameImportedTheme(theme, newName)
    root.close()
  }

  // Backdrop
  Rectangle {
    anchors.fill: parent
    color: Util.alpha("#000000", 0.65)
    MouseArea {
      anchors.fill: parent
      onClicked: root.close()
    }
  }

  FocusScope {
    id: renameScope
    anchors.fill: parent
    focus: true

    Keys.onEscapePressed: function(event) {
      event.accepted = true
      root.close()
    }

    Rectangle {
      id: card
      anchors.centerIn: parent
      width: Math.min(parent.width - Style.space(32), Style.space(400))
      height: Style.space(200)
      radius: Style.cornerRadius
      color: Color.popups.background
      border.color: Color.popups.border
      border.width: 1
      clip: true

      MouseArea { anchors.fill: parent }

      Column {
        anchors.fill: parent
        anchors.margins: Style.space(18)
        spacing: Style.space(12)

        Text {
          text: "Rename Cursor Theme"
          color: Color.popups.text
          font.family: Style.font.family
          font.pixelSize: Style.font.title
          font.bold: true
        }

        Rectangle {
          width: parent.width
          height: Style.space(36)
          radius: Style.cornerRadius - 2
          color: Util.alpha(Color.popups.text, 0.05)
          border.color: nameInput.activeFocus ? Color.accent : Util.alpha(Color.popups.text, 0.2)
          border.width: 1

          TextInput {
            id: nameInput
            anchors.fill: parent
            anchors.leftMargin: Style.space(10)
            anchors.rightMargin: Style.space(10)
            verticalAlignment: TextInput.AlignVCenter
            color: Color.popups.text
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            selectByMouse: true
            Keys.onReturnPressed: function(event) {
              event.accepted = true
              root.submit()
            }
          }
        }

        Text {
          visible: root.errorMessage !== ""
          text: root.errorMessage
          color: Color.urgent
          font.family: Style.font.family
          font.pixelSize: Style.font.caption
          font.bold: true
        }

        Item { width: parent.width; height: 1 }

        Row {
          anchors.right: parent.right
          spacing: Style.space(8)

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

          Rectangle {
            width: renameLabel.implicitWidth + Style.space(20)
            height: Style.space(32)
            radius: Style.cornerRadius - 2
            color: renameMouse.containsMouse ? Color.accent : Util.alpha(Color.accent, 0.85)

            Text {
              id: renameLabel
              anchors.centerIn: parent
              text: "Rename"
              color: Color.popups.background
              font.family: Style.font.family
              font.pixelSize: Style.font.bodySmall
              font.bold: true
            }

            MouseArea {
              id: renameMouse
              anchors.fill: parent
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              onClicked: root.submit()
            }
          }
        }
      }
    }
  }
}
