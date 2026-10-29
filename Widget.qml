pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

// Slingshot bar widget: a tray icon that opens the newest files in your
// Downloads and Pictures folders, ready to drag onto any app.
//
//   omarchy-shell supercleanse.slingshot toggle | open | close
//
// Layout: Widget.qml (bar icon, state, actions) -> DropdownWindow.qml (the
// popup surface, drag-aware) -> Content.qml (the body, renderable on its own)
// -> FileRow.qml (one file, the drag source). FolderFeed.qml keeps each
// folder's list current; Model.js holds the pure logic.
Panel {
  id: root
  moduleName: "supercleanse.slingshot"
  ipcTarget: "supercleanse.slingshot"

  readonly property int maxItems: Model.clampInt(root.setting("maxItems", 12), 5, 30, 12)
  readonly property bool showIndicator: root.setting("showIndicator", true) !== false
  readonly property bool thumbnails: root.setting("thumbnails", true) !== false
  readonly property string homePath: Quickshell.env("HOME") || ""

  property string downloadsDir: ""
  property string picturesDir: ""
  // The folder shown. Until the user picks one, each open shows whichever
  // folder holds the newest file; a manual pick sticks for the session.
  property string currentFolder: "downloads"
  property string manualFolder: ""

  property bool dragging: false
  property real now: Date.now()
  property real seenAt: Date.now()
  property bool fresh: false
  property int cursorIndex: -1
  property string copiedPath: ""
  // Last real window, tracked while the dropdown is closed. Opening the
  // panel takes keyboard focus, so a query started after `opened` flips
  // sees the layer shell instead of the app the user was in.
  property string focusedAddress: ""
  property string pasteTarget: ""
  readonly property string pasteHelper: Model.localPath(Qt.resolvedUrl("paste.py"))

  readonly property var currentFeed: root.currentFolder === "pictures" ? pictures : downloads
  readonly property var currentFiles: root.currentFeed.files
  readonly property var newestFile: {
    var d = downloads.files.length ? downloads.files[0] : null
    var p = pictures.files.length ? pictures.files[0] : null
    if (!d) return p
    if (!p) return d
    return p.mtime > d.mtime ? p : d
  }

  function setFolder(key, manual) {
    if (key !== "downloads" && key !== "pictures") return
    if (manual) root.manualFolder = key
    if (root.currentFolder === key) return
    root.currentFolder = key
    root.cursorIndex = -1
    root.copiedPath = ""
  }

  function noteFocus(ev) {
    if (root.opened || !ev) return
    if (ev.cleared) root.focusedAddress = ""
    else if (ev.address) root.focusedAddress = ev.address
  }

  // Freeze the tracked window at the moment the dropdown opens. This runs
  // synchronously inside onOpenedChanged, before a later focus-clear event
  // from the panel can be read.
  function capturePasteTarget() {
    root.pasteTarget = root.focusedAddress
  }

  function moveCursor(dy) {
    root.cursorIndex = Model.moveCursor(root.cursorIndex, dy, root.currentFiles.length)
  }

  function cursorPath() {
    var f = root.currentFiles[root.cursorIndex]
    return f ? f.path : ""
  }

  function copyFile(path) {
    if (!path) return
    Quickshell.execDetached(Model.clipboardCommand(path))
    root.copiedPath = path
    copiedCloseTimer.restart()
  }

  // Click: close the dropdown and let paste.py wait out the close, then
  // refocus the remembered window and paste into it. With no window to aim
  // at (an empty workspace), a click copies instead.
  function pasteFile(path) {
    if (!path) return
    if (!root.pasteTarget) { root.copyFile(path); return }
    Quickshell.execDetached(Model.pasteCommand(root.pasteHelper, path, 350, root.pasteTarget))
    root.close()
  }

  function openFile(path) {
    if (!path) return
    Quickshell.execDetached(Model.openCommand(path))
    root.close()
  }

  function openFolder() {
    var dir = root.currentFeed.path
    if (!dir) return
    Quickshell.execDetached(Model.openCommand(dir))
    root.close()
  }

  function handleDragFinished(path, dropAction) {
    root.dragging = false
    // A drop that some app accepted ends the job; a canceled drag (Esc, or
    // released over nothing) leaves the dropdown open to try again.
    if (dropAction !== Qt.IgnoreAction) root.close()
  }

  function updateFresh() {
    if (!root.showIndicator || root.opened) { root.fresh = false; return }
    var newest = root.newestFile ? root.newestFile.mtime : 0
    var left = Model.freshRemaining(newest, root.seenAt, Date.now(), 60000)
    root.fresh = left > 0
    if (left > 0) {
      freshTimer.interval = Math.max(1000, Math.round(left))
      freshTimer.restart()
    }
  }

  onNewestFileChanged: updateFresh()
  onShowIndicatorChanged: updateFresh()
  onCurrentFilesChanged: root.now = Date.now()

  onOpenedChanged: {
    if (root.opened) {
      root.now = Date.now()
      root.fresh = false
      root.cursorIndex = -1
      root.copiedPath = ""
      root.capturePasteTarget()
      downloads.recheck()
      pictures.recheck()
      if (root.manualFolder === "")
        root.currentFolder = Model.defaultFolder(downloads.newestMtime, pictures.newestMtime)
    } else {
      root.seenAt = Date.now()
      root.dragging = false
      copiedCloseTimer.stop()
    }
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  // Folders come from the XDG user-dirs config, read once at load.
  Process {
    id: userDirs
    running: true
    command: ["sh", "-c", "xdg-user-dir DOWNLOAD; xdg-user-dir PICTURES"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var dirs = Model.parseUserDirs(text, root.homePath)
        root.downloadsDir = dirs.downloads
        root.picturesDir = dirs.pictures
      }
    }
    // xdg-user-dir missing entirely: StdioCollector still reports an empty
    // stream, which parseUserDirs maps to the xdg-user-dirs default names.
  }

  // One shot at startup, so the first click has a target before any focus
  // event has arrived.
  Process {
    id: focusSeed
    running: true
    command: ["hyprctl", "-j", "activewindow"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var info = Model.parseActiveWindow(text)
        root.noteFocus({ address: info.address, cleared: info.address === "" })
      }
    }
  }

  // Hyprland socket2. Only activewindow lines are printed. Updates stop
  // while the dropdown is open, so the panel taking focus cannot replace
  // the window the paste is aimed at.
  Process {
    id: focusWatch
    running: true
    command: ["python3", "-u", "-c", "import os, socket, sys\nsig = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '')\nruntime = os.environ.get('XDG_RUNTIME_DIR', '')\nif not sig or not runtime:\n    sys.exit(0)\ns = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\ns.connect(runtime + '/hypr/' + sig + '/.socket2.sock')\nf = s.makefile('rb')\nwhile True:\n    line = f.readline()\n    if not line:\n        break\n    if line.startswith(b'activewindow'):\n        sys.stdout.buffer.write(line)\n        sys.stdout.flush()\n"]
    stdout: SplitParser {
      onRead: function(line) {
        root.noteFocus(Model.parseFocusLine(line))
      }
    }
    onExited: focusRestart.restart()
  }

  Timer {
    id: focusRestart
    interval: 1000
    onTriggered: if (!focusWatch.running) focusWatch.running = true
  }

  // Watched while open, and while closed only for the "new file" dot.
  FolderFeed {
    id: downloads
    path: root.downloadsDir
    active: root.opened || root.showIndicator
    maxItems: root.maxItems
  }

  FolderFeed {
    id: pictures
    path: root.picturesDir
    active: root.opened || root.showIndicator
    maxItems: root.maxItems
  }

  // Keeps "2m ago" honest while the dropdown is open; idle when closed.
  Timer {
    interval: 30000
    repeat: true
    running: root.opened
    onTriggered: root.now = Date.now()
  }

  Timer {
    id: freshTimer
    onTriggered: root.updateFresh()
  }

  // Click-to-copy shows "Copied" on the row for a beat, then gets out of the way.
  Timer {
    id: copiedCloseTimer
    interval: 650
    onTriggered: root.close()
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\u{F011D}"   // md-tray_arrow_up
    tooltipText: root.fresh && root.newestFile ? "New: " + root.newestFile.name : "Recent downloads and pictures"
    onPressed: function(b) { root.toggle() }

    // New-file dot: a file arrived in the last minute and you haven't looked.
    Rectangle {
      visible: root.fresh
      width: Style.space(6)
      height: width
      radius: width / 2
      color: Color.accent
      x: Math.round(parent.width / 2 + Style.space(4))
      y: Math.round(parent.height / 2 - Style.space(9))
    }
  }

  DropdownWindow {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    dragging: root.dragging
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(360))
    contentHeight: panel.fittedContentHeight(content.implicitHeight, Style.space(680))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onMoveRequested: function(dx, dy) {
        if (dx !== 0) root.setFolder(dx < 0 ? "downloads" : "pictures", true)
        else root.moveCursor(dy)
      }
      onActivateRequested: root.pasteFile(root.cursorPath())
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t >= "0" && t <= "9" && t.length === 1) {
          var f = root.currentFiles[t === "0" ? 9 : Number(t) - 1]
          if (f) root.pasteFile(f.path)
        }
        else if (t === "c" || t === "C") root.copyFile(root.cursorPath())
        else if (t === "o" || t === "O") root.openFile(root.cursorPath())
        else if (t === "f" || t === "F") root.openFolder()
        else if (t === "d" || t === "D") root.setFolder("downloads", true)
        else if (t === "p" || t === "P") root.setFolder("pictures", true)
      }

      Content {
        id: content
        anchors.fill: parent
        folder: root.currentFolder
        folderPath: root.currentFeed.path
        homePath: root.homePath
        files: root.currentFiles
        folderState: root.currentFeed.folderState
        now: root.now
        cursorIndex: root.cursorIndex
        copiedPath: root.copiedPath
        thumbnails: root.thumbnails
        foreground: root.bar ? root.bar.foreground : Color.foreground
        fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
        onFolderRequested: function(key) { root.setFolder(key, true) }
        onCopyRequested: function(path) { root.copyFile(path) }
        onOpenRequested: function(path) { root.openFile(path) }
        onPasteRequested: function(path) { root.pasteFile(path) }
        onOpenFolderRequested: root.openFolder()
        onRowHovered: function(index) { root.cursorIndex = index }
        onDragStarted: function(path) { root.dragging = true }
        onDragFinished: function(path, dropAction) { root.handleDragFinished(path, dropAction) }
      }
    }
  }
}
