import QtQuick
import Qt.labs.folderlistmodel
import Quickshell
import Quickshell.Io
import "Model.js" as Model

// The newest files in one folder, kept current without polling.
//
// Qt's FolderListModel lists the folder on a worker thread and watches it
// with inotify (QFileSystemWatcher), so a new screenshot or a finished
// download (the browser renames "x.part" to "x") shows up on its own. When
// `active` is false the model is pointed at nothing and holds no watch.
//
// FolderListModel cannot tell an empty folder from one it cannot read, so a
// one-line probe runs whenever the path changes and each time the dropdown
// opens (`recheck()`).
Item {
  id: feed

  property string path: ""
  property bool active: true
  property int maxItems: 12

  // [{ name, path, mtime (ms), size }], newest first.
  property var files: []
  readonly property real newestMtime: files.length > 0 ? files[0].mtime : 0
  // "loading" | "ready" | "missing" | "unreadable"
  property string folderState: "loading"
  property bool readable: false

  visible: false

  function recheck() {
    if (feed.path === "") return
    if (probe.running) { probe.pending = true; return }
    // Set imperatively: a binding on `command` may not have caught up with a
    // path change by the time onPathChanged runs.
    probe.command = Model.probeCommand(feed.path)
    probe.running = true
  }

  function rebuild() {
    if (!feed.readable || !feed.active) {
      feed.files = []
      return
    }
    // The model is sorted newest first; the extra margin leaves room for
    // partial downloads and their placeholders, which pickRecent drops.
    var n = Math.min(model.count, feed.maxItems * 3 + 20)
    var entries = []
    for (var i = 0; i < n; i++) {
      var modified = model.get(i, "fileModified")
      entries.push({
        name: model.get(i, "fileName"),
        path: model.get(i, "filePath"),
        mtime: modified ? modified.getTime() : 0,
        size: model.get(i, "fileSize"),
        isDir: model.get(i, "fileIsDir")
      })
    }
    feed.files = Model.pickRecent(entries, feed.maxItems)
    if (model.status === FolderListModel.Ready) feed.folderState = "ready"
  }

  onPathChanged: {
    feed.readable = false
    feed.folderState = "loading"
    feed.files = []
    recheck()
  }
  onActiveChanged: if (active) recheck(); else rebuild()
  onMaxItemsChanged: debounce.restart()

  FolderListModel {
    id: model
    folder: feed.active && feed.readable && feed.path !== "" ? Model.fileUri(feed.path) : ""
    showDirs: false
    showDotAndDotDot: false
    showHidden: false
    showOnlyReadable: false
    sortField: FolderListModel.Time
    sortReversed: false

    onCountChanged: debounce.restart()
    onStatusChanged: debounce.restart()
    onRowsInserted: debounce.restart()
    onRowsRemoved: debounce.restart()
    onDataChanged: debounce.restart()
    onModelReset: debounce.restart()
    onLayoutChanged: debounce.restart()
  }

  // Bursts of directory events (a download finishing, a screenshot tool
  // writing then renaming) collapse into one rebuild.
  Timer {
    id: debounce
    interval: 120
    onTriggered: feed.rebuild()
  }

  Process {
    id: probe
    property bool pending: false
    onExited: function(exitCode) {
      var next = Model.probeState(exitCode)
      feed.readable = next === "ready"
      if (next !== "ready") {
        feed.folderState = next
        feed.files = []
      } else if (feed.folderState !== "ready") {
        feed.folderState = "loading"
      }
      debounce.restart()
      if (probe.pending) {
        probe.pending = false
        feed.recheck()
      }
    }
  }
}
