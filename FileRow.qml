pragma ComponentBehavior: Bound
import QtQuick
import qs.Commons
import qs.Ui
import "Model.js" as Model

// One file in the dropdown: thumbnail or type glyph, name, age and size.
//
// The row is a drag source for other apps. Past a small threshold a left
// drag starts a real Wayland drag (Drag.Automatic, so Qt runs QDrag::exec)
// that offers text/uri-list plus the plain path. The drag is started by hand
// from onPositionChanged rather than bound to MouseArea.drag.active: the
// release happens in another client, and a binding would leave the drag
// state stuck until the next press.
//
// Left click pastes the file into the window that had focus before the
// dropdown opened, middle click opens it, right click copies it. Visuals follow
// the Omarchy CursorSurface contract: the panel owns the cursor, hover only
// moves it.
CursorSurface {
  id: row

  required property var file
  property real now: Date.now()
  property bool copied: false
  property bool thumbnails: true
  // 1-10 shows the number key that pastes this row (10 shows as 0); 0 hides it.
  property int number: 0
  property string fontFamily: Style.font.family

  signal copyRequested()
  signal openRequested()
  signal pasteRequested()
  signal dragStarted()
  signal dragFinished(int dropAction)
  signal hoverEntered()

  readonly property string filePath: file ? String(file.path) : ""
  readonly property string fileName: file ? String(file.name) : ""
  readonly property bool wantsThumb: row.thumbnails && Model.isThumbnailable(row.fileName)
  readonly property bool thumbReady: thumb.status === Image.Ready
  readonly property bool dragging: mouse.dragging
  readonly property color dim: Qt.darker(row.foreground, 1.5)

  implicitHeight: Math.max(thumbBox.height, info.implicitHeight) + Style.space(10)
  opacity: mouse.dragging ? 0.55 : 1.0

  Behavior on opacity { NumberAnimation { duration: 120 } }

  Item {
    id: content
    anchors.fill: parent
    anchors.leftMargin: Style.space(6)
    anchors.rightMargin: Style.space(10)

    Rectangle {
      id: thumbBox
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      width: Style.space(34)
      height: width
      radius: Style.cornerRadius
      color: Qt.rgba(row.foreground.r, row.foreground.g, row.foreground.b, row.thumbReady ? 0 : 0.06)
      clip: true

      Image {
        id: thumb
        anchors.fill: parent
        visible: row.thumbReady
        // The mtime query busts Qt's pixmap cache when a file is replaced
        // under the same name; the local-file loader ignores it otherwise.
        source: row.wantsThumb ? Model.fileUri(row.filePath) + "?v=" + Math.round(row.file.mtime || 0) : ""
        sourceSize.width: Math.round(width * 2)
        sourceSize.height: Math.round(height * 2)
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        smooth: true
        mipmap: true
      }

      Text {
        anchors.centerIn: parent
        visible: !row.thumbReady
        textFormat: Text.PlainText
        text: Model.glyphFor(row.fileName)
        color: row.foreground
        font.family: row.fontFamily
        font.pixelSize: Style.font.heading + Style.space(2)
      }
    }

    Text {
      id: numberLabel
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      visible: row.number > 0
      textFormat: Text.PlainText
      text: row.number === 10 ? "0" : String(row.number)
      color: row.dim
      font.family: row.fontFamily
      font.pixelSize: Style.font.caption
    }

    Column {
      id: info
      anchors.left: thumbBox.right
      anchors.leftMargin: Style.space(10)
      anchors.right: parent.right
      anchors.rightMargin: numberLabel.visible ? numberLabel.implicitWidth + Style.space(8) : 0
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(2)

      Text {
        width: parent.width
        textFormat: Text.PlainText
        text: row.fileName
        color: row.foreground
        elide: Text.ElideMiddle
        font.family: row.fontFamily
        font.pixelSize: Style.font.body
      }

      Text {
        width: parent.width
        textFormat: Text.PlainText
        text: row.copied
          ? "\u{F012C}  Copied to clipboard"
          : Model.relativeTime(row.file ? row.file.mtime : 0, row.now) + "  ·  " + Model.formatSize(row.file ? row.file.size : 0)
        color: row.copied ? row.foreground : row.dim
        elide: Text.ElideRight
        font.family: row.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }

  // Invisible drag source. It never moves; it only carries the Drag
  // attached properties, so the row stays put while the file travels.
  Item {
    id: dragSource
    Drag.dragType: Drag.Automatic
    Drag.supportedActions: Qt.CopyAction
    Drag.proposedAction: Qt.CopyAction
    Drag.mimeData: Model.dragMimeData(row.filePath)
    Drag.hotSpot.x: Style.space(17)
    Drag.hotSpot.y: Style.space(17)
    Drag.onDragFinished: function(dropAction) {
      mouse.dragging = false
      mouse.armed = false
      row.dragFinished(dropAction)
    }
  }

  MouseArea {
    id: mouse
    anchors.fill: parent
    hoverEnabled: true
    preventStealing: true
    acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
    cursorShape: dragging ? Qt.ClosedHandCursor : Qt.PointingHandCursor

    property bool armed: false
    property bool dragging: false
    property real pressX: 0
    property real pressY: 0

    onContainsMouseChanged: if (containsMouse) row.hoverEntered()

    onPressed: function(event) {
      armed = event.button === Qt.LeftButton
      pressX = event.x
      pressY = event.y
      // The drag image is the thumbnail (or glyph) as it looks right now.
      if (armed) thumbBox.grabToImage(function(result) { dragSource.Drag.imageSource = result.url })
    }

    onPositionChanged: function(event) {
      if (!armed || dragging || !pressed) return
      var dx = event.x - pressX
      var dy = event.y - pressY
      if (dx * dx + dy * dy < Style.space(6) * Style.space(6)) return
      dragging = true
      row.dragStarted()
      // With Drag.Automatic this hands off to the platform drag; on Wayland
      // the compositor owns the pointer until the drop or cancel.
      dragSource.Drag.active = true
    }

    onReleased: armed = false
    onCanceled: armed = false

    onClicked: function(event) {
      if (dragging) return
      if (event.button === Qt.MiddleButton) row.openRequested()
      else if (event.button === Qt.RightButton) row.copyRequested()
      else row.pasteRequested()
    }
  }
}
