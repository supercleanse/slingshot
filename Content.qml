pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui
import "Model.js" as Model

// The dropdown body only: no processes, no file system access, no windows.
// Everything it wants done goes out as a signal, so the offscreen harness
// (tests/offscreen) can render it with canned data in light and dark themes.
Item {
  id: root

  property string folder: "downloads"            // "downloads" | "pictures"
  property string folderPath: ""
  property string homePath: ""
  property var files: []                          // [{ name, path, mtime, size }]
  property string folderState: "ready"            // "loading" | "ready" | "missing" | "unreadable"
  property real now: Date.now()
  property int cursorIndex: -1
  property string copiedPath: ""
  property bool thumbnails: true
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  signal folderRequested(string key)
  signal copyRequested(string path)
  signal openRequested(string path)
  signal pasteRequested(string path)
  signal openFolderRequested()
  signal dragStarted(string path)
  signal dragFinished(string path, int dropAction)
  signal rowHovered(int index)

  readonly property string folderName: Model.folderLabel(root.folder)
  readonly property string shortPath: Model.homeRelative(root.folderPath, root.homePath)
  readonly property bool showList: root.folderState === "ready" && root.files.length > 0
  readonly property color dim: Qt.darker(root.foreground, 1.5)

  implicitWidth: Style.space(360)
  implicitHeight: layout.implicitHeight

  ColumnLayout {
    id: layout
    anchors.fill: parent
    spacing: Style.space(10)

    // ---------- Folder switch ----------
    Row {
      id: tabs
      Layout.fillWidth: true
      spacing: Style.space(6)
      readonly property real cellWidth: (width - spacing) / 2

      Repeater {
        model: [
          { key: "downloads", label: "Downloads", icon: "\u{F01DA}" },   // md-download
          { key: "pictures", label: "Pictures", icon: "\u{F0976}" }       // md-image_outline
        ]
        delegate: Button {
          required property var modelData
          width: tabs.cellWidth
          text: modelData.label
          iconText: modelData.icon
          bordered: true
          selected: root.folder === modelData.key
          foreground: root.foreground
          fontFamily: root.fontFamily
          onClicked: root.folderRequested(modelData.key)
        }
      }
    }

    // ---------- Section header: LATEST · ~/Downloads ----------
    Item {
      Layout.fillWidth: true
      implicitHeight: Math.max(sectionLabel.implicitHeight, pathLabel.implicitHeight)

      PanelSectionHeader {
        id: sectionLabel
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        text: "LATEST"
        foreground: root.foreground
        fontFamily: root.fontFamily
      }

      Text {
        id: pathLabel
        anchors.left: sectionLabel.right
        anchors.leftMargin: Style.space(12)
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        horizontalAlignment: Text.AlignRight
        textFormat: Text.PlainText
        text: root.shortPath
        color: root.dim
        elide: Text.ElideMiddle
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }
    }

    // ---------- File list ----------
    Flickable {
      id: list
      visible: root.showList
      Layout.fillWidth: true
      Layout.fillHeight: true
      Layout.minimumHeight: Math.min(rows.implicitHeight, Style.space(120))
      Layout.preferredHeight: rows.implicitHeight
      contentWidth: width
      contentHeight: rows.implicitHeight
      // Only scroll when the panel had to cap its height; rows block flick
      // stealing so a vertical drag always leaves as a file drag.
      interactive: contentHeight > height + 1
      boundsBehavior: Flickable.StopAtBounds
      clip: true

      Column {
        id: rows
        width: list.width
        spacing: Style.space(2)

        Repeater {
          model: root.showList ? root.files : []
          delegate: FileRow {
            required property var modelData
            required property int index
            width: rows.width
            file: modelData
            now: root.now
            copied: root.copiedPath !== "" && root.copiedPath === modelData.path
            thumbnails: root.thumbnails
            number: index < 10 ? index + 1 : 0
            hasCursor: root.cursorIndex === index
            foreground: root.foreground
            fontFamily: root.fontFamily
            onHoverEntered: root.rowHovered(index)
            onCopyRequested: root.copyRequested(modelData.path)
            onOpenRequested: root.openRequested(modelData.path)
            onPasteRequested: root.pasteRequested(modelData.path)
            onDragStarted: root.dragStarted(modelData.path)
            onDragFinished: function(dropAction) { root.dragFinished(modelData.path, dropAction) }
          }
        }
      }
    }

    // ---------- Empty / loading / error ----------
    Column {
      id: emptyState
      visible: !root.showList
      Layout.fillWidth: true
      topPadding: Style.space(18)
      bottomPadding: Style.space(18)
      spacing: Style.space(8)

      readonly property string glyph: root.folderState === "missing" ? "\u{F0B9E}"     // md-folder_remove_outline
        : root.folderState === "unreadable" ? "\u{F0DCD}"                               // md-folder_alert_outline
        : root.folderState === "loading" ? "\u{F0997}"                                  // md-progress_download
        : "\u{F1294}"                                                                   // md-tray
      readonly property string title: root.folderState === "missing" ? root.shortPath + " doesn't exist"
        : root.folderState === "unreadable" ? "Can't read " + root.shortPath
        : root.folderState === "loading" ? "Looking in " + root.shortPath + "…"
        : "Nothing in " + root.shortPath + " yet"
      readonly property string detail: root.folderState === "missing" ? "Set it in ~/.config/user-dirs.dirs, or create the folder."
        : root.folderState === "unreadable" ? "Its permissions don't let you list it."
        : root.folderState === "loading" ? ""
        : (root.folder === "pictures" ? "Screenshots and saved images land here." : "Finished downloads land here.")

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        textFormat: Text.PlainText
        text: emptyState.glyph
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.display
      }
      Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        textFormat: Text.PlainText
        text: emptyState.title
        color: root.foreground
        elide: Text.ElideMiddle
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
      }
      Text {
        width: parent.width
        visible: emptyState.detail !== ""
        horizontalAlignment: Text.AlignHCenter
        textFormat: Text.PlainText
        text: emptyState.detail
        color: root.dim
        wrapMode: Text.WordWrap
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }
    }

    // ---------- Hint + footer ----------
    Text {
      Layout.fillWidth: true
      visible: root.showList
      textFormat: Text.PlainText
      text: "Click or 1–0 to paste · Right-click to copy · Or drag"
      color: root.dim
      horizontalAlignment: Text.AlignHCenter
      elide: Text.ElideRight
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    PanelSeparator {
      Layout.fillWidth: true
      foreground: root.foreground
    }

    Button {
      Layout.fillWidth: true
      leftAlign: true
      enabled: root.folderState !== "missing"
      opacity: enabled ? 1.0 : 0.4
      iconText: "\u{F0DCF}"   // md-folder_open_outline
      text: "Open " + root.folderName + " in file browser"
      foreground: root.foreground
      fontFamily: root.fontFamily
      onClicked: root.openFolderRequested()
    }
  }
}
