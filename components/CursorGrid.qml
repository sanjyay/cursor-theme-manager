import QtQuick
import QtQuick.Controls
import qs.Commons

Flickable {
  id: root
  property var themes: []
  property int committedIndex: -1
  property int cursorIndex: 0
  property bool cursorActive: true
  readonly property int columns: 3
  signal themeActivated(var theme, int index)
  signal themeHovered(var theme, int index, bool active)

  contentWidth: width
  contentHeight: grid.implicitHeight
  clip: true
  boundsBehavior: Flickable.StopAtBounds
  flickableDirection: Flickable.VerticalFlick
  ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

  function ensureVisible(index) {
    if (index < 0 || index >= repeater.count) return
    Qt.callLater(function() {
      var item = repeater.itemAt(index)
      if (!item) return
      var top = item.y
      var bottom = top + item.height
      if (top < root.contentY) root.contentY = top
      else if (bottom > root.contentY + root.height) root.contentY = bottom - root.height
    })
  }

  Grid {
    id: grid
    width: parent.width
    columns: root.columns
    columnSpacing: Style.space(8)
    rowSpacing: Style.space(8)

    Repeater {
      id: repeater
      model: root.themes
      delegate: CursorCard {
        required property int index
        required property var modelData
        width: (grid.width - grid.columnSpacing * (grid.columns - 1)) / grid.columns
        theme: modelData
        selected: index === root.committedIndex
        hasCursor: root.cursorActive && index === root.cursorIndex
        onActivated: root.themeActivated(modelData, index)
        onHovered: function(active) { root.themeHovered(modelData, index, active) }
      }
    }
  }
}
