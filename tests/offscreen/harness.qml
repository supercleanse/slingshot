import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Offscreen harness -- run ONLY through tests/offscreen/render.sh, which sets
// QT_QPA_PLATFORM=offscreen, a fake HOME built by make_fixtures.py, and a
// private runtime dir. Never ships, never maps a window.
//
// It loads the real Widget.qml (with DropdownWindow swapped for an inline
// stub), lets the real FolderFeed/xdg-user-dir path read the fake folders,
// then walks a script: checks print "CHECK ok|FAIL <name>", screenshots land
// in $SLINGSHOT_SHOT_DIR as <name>.png.
ShellRoot {
  id: shell

  readonly property string shotDir: Quickshell.env("SLINGSHOT_SHOT_DIR") || "/tmp"
  readonly property string home: Quickshell.env("HOME")
  property int failures: 0
  property int step: 0
  property var widget: loader.item

  readonly property var dark: ({ background: "#121212", foreground: "#bebebe", accent: "#e68e0d", urgent: "#a55555", muted: "#333333" })
  readonly property var light: ({ background: "#eff1f5", foreground: "#4c4f69", accent: "#1e66f5", urgent: "#d20f39", muted: "#acb0be" })

  function theme(p) {
    Color.background = p.background
    Color.foreground = p.foreground
    Color.accent = p.accent
    Color.urgent = p.urgent
    Color.muted = p.muted
  }

  function check(name, ok, detail) {
    if (ok) console.info("CHECK ok " + name)
    else { shell.failures++; console.info("CHECK FAIL " + name + (detail ? ": " + detail : "")) }
  }

  function names(list) {
    var out = []
    for (var i = 0; i < list.length; i++) out.push(list[i].name)
    return out.join(" | ")
  }

  function shot(item, name, next) {
    item.grabToImage(function(result) {
      var out = shell.shotDir + "/" + name + ".png"
      if (!result.saveToFile(out)) shell.check("save " + name, false, out)
      else console.info("harness: wrote " + out)
      next()
    })
  }

  PluginBarApi {
    id: barApi
    pluginId: "supercleanse.slingshot"
    moduleName: "supercleanse.slingshot"
    foreground: Color.popups.text
    barForeground: Color.bar.text
    background: Color.bar.background
    urgent: Color.urgent
    fontFamily: Style.font.family
    barSize: Style.bar.sizeHorizontal
    position: "top"
  }

  Process {
    id: touchNew
    command: ["sh", "-c", "printf '%%PDF-1.4 fake\\n' > \"$1/Downloads/quarterly-report.pdf\"", "harness", shell.home]
  }

  FloatingWindow {
    visible: true
    implicitWidth: 560
    implicitHeight: 760
    color: Color.background

    Item {
      id: stage
      width: 560
      height: 760

      Rectangle { anchors.fill: parent; color: Qt.darker(Color.background, 1.02) }

      Rectangle {
        id: barStrip
        width: parent.width
        height: Style.bar.sizeHorizontal + 4
        color: Color.bar.background

        Text {
          anchors.centerIn: parent
          text: "Tue 14:34"
          color: Color.bar.text
          font.family: Style.font.family
          font.pixelSize: Style.font.body
        }
        Text {
          anchors.left: parent.left
          anchors.leftMargin: 12
          anchors.verticalCenter: parent.verticalCenter
          text: "\u{F08C7}   1  2  3"
          color: Color.bar.text
          font.family: Style.font.family
          font.pixelSize: Style.font.body
        }

        Loader {
          id: loader
          x: 360
          y: 2
          source: "Widget.qml"
          onLoaded: {
            item.bar = barApi
            item.settings = ({})
          }
        }
      }
    }
  }

  // The script. Each entry: [delay before, action]. Actions call next() when done.
  readonly property var script: [
    [600, function(next) {
      Style.fontFamily = "JetBrainsMono Nerd Font"
      shell.theme(shell.dark)
      next()
    }],
    [2600, function(next) {
      var w = shell.widget
      shell.check("widget loaded", !!w)
      shell.check("xdg downloads dir", w.downloadsDir === shell.home + "/Downloads", w.downloadsDir)
      shell.check("xdg pictures dir", w.picturesDir === shell.home + "/Pictures", w.picturesDir)
      shell.check("newest overall is the screenshot", w.newestFile && w.newestFile.name === "Screenshot 2026-10-21 at 14.32.07.png", w.newestFile ? w.newestFile.name : "none")
      shell.check("no dot for files that predate the shell", w.fresh === false)
      shell.shot(barStrip, "bar-idle", next)
    }],
    [100, function(next) { touchNew.running = true; next() }],
    [1800, function(next) {
      var w = shell.widget
      shell.check("live refresh picked up a new download", w.newestFile && w.newestFile.name === "quarterly-report.pdf", w.newestFile ? w.newestFile.name : "none")
      shell.check("new-file dot is on", w.fresh === true)
      shell.shot(barStrip, "bar-fresh", next)
    }],
    [100, function(next) { shell.widget.open(); next() }],
    [1500, function(next) {
      var w = shell.widget
      shell.check("opened", w.opened === true)
      shell.check("dot clears on open", w.fresh === false)
      shell.check("default folder follows the newest file", w.currentFolder === "downloads", w.currentFolder)
      var expect = "quarterly-report.pdf | Q3 board deck (final).pdf | invoice #4412.pdf | omarchy-3.2.iso | sunset été ⛵.png | notes.md | dataset.csv | archive.tar.gz | song.flac"
      shell.check("downloads list: order and filtering", shell.names(w.currentFiles) === expect, shell.names(w.currentFiles))
      shell.check("folder state ready", w.currentFeed.folderState === "ready", w.currentFeed.folderState)
      shell.shot(stage, "dark-downloads", next)
    }],
    [100, function(next) { shell.widget.setFolder("pictures", true); shell.widget.cursorIndex = 1; next() }],
    [1500, function(next) {
      var w = shell.widget
      shell.check("manual pick sticks", w.manualFolder === "pictures")
      var expect = "Screenshot 2026-10-21 at 14.32.07.png | Screenshot 2026-10-21 at 13.10.55.png | wallpaper-mountains.png | diagram.svg | IMG_2041.HEIC"
      shell.check("pictures list", shell.names(w.currentFiles) === expect, shell.names(w.currentFiles))
      shell.shot(stage, "dark-pictures", next)
    }],
    [100, function(next) { shell.widget.copiedPath = shell.widget.currentFiles[0].path; shell.widget.cursorIndex = 0; next() }],
    [300, function(next) { shell.shot(stage, "dark-copied", next) }],
    [100, function(next) { shell.widget.copiedPath = ""; shell.widget.cursorIndex = 1; shell.theme(shell.light); next() }],
    [700, function(next) { shell.shot(stage, "light-pictures", next) }],
    [100, function(next) { shell.widget.setFolder("downloads", true); shell.widget.cursorIndex = -1; next() }],
    [1200, function(next) { shell.shot(stage, "light-downloads", next) }],
    [100, function(next) { shell.theme(shell.dark); shell.widget.settings = ({ maxItems: 5 }); next() }],
    [600, function(next) {
      shell.check("maxItems setting caps the list", shell.widget.currentFiles.length === 5, String(shell.widget.currentFiles.length))
      shell.widget.settings = ({})
      shell.widget.picturesDir = shell.home + "/Empty"
      shell.widget.setFolder("pictures", true)
      next()
    }],
    [1200, function(next) {
      var w = shell.widget
      shell.check("empty folder state", w.currentFeed.folderState === "ready" && w.currentFiles.length === 0, w.currentFeed.folderState + " " + w.currentFiles.length)
      shell.shot(stage, "dark-empty", next)
    }],
    [100, function(next) { shell.widget.picturesDir = shell.home + "/NoSuchFolder"; next() }],
    [1000, function(next) {
      shell.check("missing folder state", shell.widget.currentFeed.folderState === "missing", shell.widget.currentFeed.folderState)
      shell.shot(stage, "dark-missing", next)
    }],
    [100, function(next) { shell.widget.picturesDir = shell.home + "/Locked"; next() }],
    [1000, function(next) {
      shell.check("unreadable folder state", shell.widget.currentFeed.folderState === "unreadable", shell.widget.currentFeed.folderState)
      shell.shot(stage, "dark-unreadable", next)
    }],
    [100, function(next) {
      shell.widget.close()
      shell.check("closed", shell.widget.opened === false)
      next()
    }]
  ]

  Timer {
    id: runner
    property var pending: null
    running: true
    interval: shell.script[0][0]
    onTriggered: {
      if (shell.step >= shell.script.length) {
        console.info("HARNESS DONE failures=" + shell.failures)
        Qt.quit()
        return
      }
      var action = shell.script[shell.step][1]
      shell.step++
      action(function() {
        if (shell.step < shell.script.length) runner.interval = shell.script[shell.step][0]
        else runner.interval = 50
        runner.restart()
      })
    }
  }
}
