import QtQuick
import qs.Commons
import qs.Ui

// Harness-only stand-in for DropdownWindow.qml, which is a layer-shell
// PanelWindow and cannot load without a Wayland compositor. It draws the same
// card (BorderSurface, popup colors, border, padding) inline under the bar
// icon, so the harness can grab the real Widget.qml + Content.qml together.
Item {
  id: root

  property Item anchorItem: null
  property var owner: null
  property QtObject bar: null
  property bool open: false
  property bool dragging: false
  property Item focusTarget: null
  property int padding: Style.spacing.popupPadding
  property int contentWidth: Style.space(280)
  property int contentHeight: Style.space(200)
  property var borderSpec: Border.surfaceSpec("popups", "border", Color.popups.border, Math.max(1, Style.space(2)))
  readonly property real verticalContentInset: padding * 2 + Border.top(borderSpec) + Border.bottom(borderSpec)

  default property alias contentItem: holder.children

  function fittedContentWidth(width, cap) {
    var w = Math.max(1, Number(width) || 1)
    return Math.round(cap !== undefined && cap > 0 ? Math.min(w, cap) : w)
  }
  function fittedContentHeight(implicitHeight, cap) {
    var h = Math.max(verticalContentInset, (Number(implicitHeight) || 0) + verticalContentInset)
    return Math.round(cap !== undefined && cap > 0 ? Math.min(h, cap) : h)
  }

  BorderSurface {
    id: card
    visible: root.open
    x: root.anchorItem ? Math.round(root.anchorItem.width / 2 - width / 2) : 0
    y: root.anchorItem ? root.anchorItem.height + Style.gapsOut : 0
    width: root.contentWidth
    height: root.contentHeight
    color: Color.popups.background
    borderSpec: root.borderSpec
    padding: root.padding
    radius: Style.cornerRadius

    Item {
      id: holder
      anchors.fill: parent
      anchors.topMargin: card.contentTopInset
      anchors.rightMargin: card.contentRightInset
      anchors.bottomMargin: card.contentBottomInset
      anchors.leftMargin: card.contentLeftInset
    }
  }
}
