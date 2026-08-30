import QtQuick
import QtQuick.Controls

ApplicationWindow {
  id: root
  width: 720
  height: 420
  visibility: Window.FullScreen
  title: "Omarchy Banana cursor-role test"
  color: "#242424"
  property int requestedShape: Qt.ArrowCursor

  MouseArea {
    anchors.fill: parent
    cursorShape: root.requestedShape
  }

  Shortcut { sequence: "1"; onActivated: root.requestedShape = Qt.ArrowCursor }
  Shortcut { sequence: "2"; onActivated: root.requestedShape = Qt.PointingHandCursor }
  Shortcut { sequence: "3"; onActivated: root.requestedShape = Qt.IBeamCursor }
  Shortcut { sequence: "4"; onActivated: root.requestedShape = Qt.SizeHorCursor }
  Shortcut { sequence: "5"; onActivated: root.requestedShape = Qt.OpenHandCursor }

  Column {
    anchors.fill: parent
    anchors.margins: 24
    spacing: 16

    Label {
      text: "Move across each zone, or press 1–5; cursor changes are requested by Qt."
      color: "#f2f2f2"
      font.pixelSize: 18
    }

    Row {
      spacing: 12

      Repeater {
        model: [
          { label: "Default", shape: Qt.ArrowCursor, color: "#3b3b3b" },
          { label: "Clickable", shape: Qt.PointingHandCursor, color: "#5b4b20" },
          { label: "Resize", shape: Qt.SizeHorCursor, color: "#304653" },
          { label: "Grab", shape: Qt.OpenHandCursor, color: "#403552" }
        ]

        Rectangle {
          required property var modelData
          width: 154
          height: 120
          radius: 10
          color: modelData.color
          border.color: "#777"

          Label {
            anchors.centerIn: parent
            text: parent.modelData.label
            color: "#fff"
            font.pixelSize: 16
          }

          MouseArea {
            anchors.fill: parent
            cursorShape: parent.modelData.shape
          }
        }
      }
    }

    TextField {
      width: parent.width
      placeholderText: "Text input requests the I-beam cursor"
    }

    Label {
      width: parent.width
      wrapMode: Text.WordWrap
      color: "#c9c9c9"
      text: "Expected: intact banana over Default; peeled banana over Clickable; weighted directional cursor over Resize; open bunch over Grab; I-beam in this field."
    }
  }
}
