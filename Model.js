.pragma library

// Pure helpers for the Slingshot bar widget and dropdown. No QML types here,
// so filtering, sorting, formatting and URI encoding can be tested with
// `node --test tests/js` apart from the layout.

// Files still being written by a browser or downloader. Hidden files are
// excluded separately (and the folder model never lists them anyway).
var PARTIAL_SUFFIXES = [".part", ".crdownload", ".download", ".tmp"]

// Formats Qt can decode with the image plugins Omarchy ships. Anything else
// gets a file-type glyph instead of a thumbnail.
var IMAGE_EXTS = ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "tif", "tiff", "ico", "tga", "jp2"]

// Nerd Font (Material Design) glyphs, by file kind.
var GLYPHS = {
  image: "\u{F0EB0}",     // md-file_image_outline
  video: "\u{F0E2C}",     // md-file_video_outline
  audio: "\u{F0E2A}",     // md-file_music_outline
  pdf: "\u{F0226}",       // md-file_pdf_box
  archive: "\u{F0FFA}",   // md-zip_box_outline
  code: "\u{F102B}",      // md-file_code_outline
  sheet: "\u{F0C7F}",     // md-file_table_outline
  doc: "\u{F09EE}",       // md-file_document_outline
  slides: "\u{F1035}",    // md-file_powerpoint_outline
  disk: "\u{F02CA}",      // md-harddisk
  package: "\u{F03D7}",   // md-package_variant_closed
  file: "\u{F0224}"       // md-file_outline
}

var KIND_BY_EXT = {
  png: "image", jpg: "image", jpeg: "image", gif: "image", webp: "image", bmp: "image",
  svg: "image", tif: "image", tiff: "image", ico: "image", tga: "image", jp2: "image",
  heic: "image", heif: "image", avif: "image", jxl: "image", raw: "image", cr2: "image", nef: "image",
  mp4: "video", mkv: "video", webm: "video", mov: "video", avi: "video", m4v: "video",
  mp3: "audio", wav: "audio", flac: "audio", ogg: "audio", opus: "audio", m4a: "audio", aac: "audio",
  pdf: "pdf",
  zip: "archive", tar: "archive", gz: "archive", tgz: "archive", bz2: "archive", xz: "archive",
  zst: "archive", "7z": "archive", rar: "archive",
  js: "code", ts: "code", py: "code", rb: "code", go: "code", rs: "code", c: "code", h: "code",
  cpp: "code", java: "code", php: "code", sh: "code", qml: "code", json: "code", yaml: "code",
  yml: "code", toml: "code", html: "code", css: "code", sql: "code", xml: "code",
  csv: "sheet", tsv: "sheet", xls: "sheet", xlsx: "sheet", ods: "sheet",
  doc: "doc", docx: "doc", odt: "doc", rtf: "doc", txt: "doc", md: "doc", log: "doc", epub: "doc",
  ppt: "slides", pptx: "slides", odp: "slides", key: "slides",
  iso: "disk", img: "disk", dmg: "disk", qcow2: "disk",
  deb: "package", rpm: "package", appimage: "package", flatpak: "package", exe: "package", msi: "package"
}

function extOf(name) {
  var s = String(name || "")
  var dot = s.lastIndexOf(".")
  if (dot <= 0 || dot === s.length - 1) return ""
  return s.slice(dot + 1).toLowerCase()
}

function isHidden(name) {
  return String(name || "").charAt(0) === "."
}

function isPartial(name) {
  var lower = String(name || "").toLowerCase()
  for (var i = 0; i < PARTIAL_SUFFIXES.length; i++) {
    var suf = PARTIAL_SUFFIXES[i]
    if (lower.length > suf.length && lower.slice(-suf.length) === suf) return true
  }
  return false
}

function kindFor(name) {
  return KIND_BY_EXT[extOf(name)] || "file"
}

function glyphFor(name) {
  return GLYPHS[kindFor(name)] || GLYPHS.file
}

function isThumbnailable(name) {
  return IMAGE_EXTS.indexOf(extOf(name)) !== -1
}

// entries: [{ name, path, mtime (ms), size, isDir }] in any order.
// Returns the newest `max` regular files, newest first. Skips directories,
// hidden files, partial downloads, and the empty placeholder Firefox writes
// under the final name while "<name>.part" is still downloading.
function pickRecent(entries, max) {
  var list = Array.isArray(entries) ? entries : []
  var limit = Math.max(0, Math.floor(Number(max) || 0))
  var names = {}
  for (var i = 0; i < list.length; i++) {
    if (list[i] && list[i].name) names[String(list[i].name).toLowerCase()] = true
  }
  var kept = []
  for (var j = 0; j < list.length; j++) {
    var e = list[j]
    if (!e || !e.name || !e.path || e.isDir) continue
    var name = String(e.name)
    if (isHidden(name) || isPartial(name)) continue
    var lower = name.toLowerCase()
    var downloading = false
    for (var k = 0; k < PARTIAL_SUFFIXES.length; k++) {
      if (names[lower + PARTIAL_SUFFIXES[k]]) { downloading = true; break }
    }
    if (downloading) continue
    kept.push({
      name: name,
      path: String(e.path),
      mtime: Number(e.mtime) || 0,
      size: Math.max(0, Number(e.size) || 0)
    })
  }
  kept.sort(function(a, b) {
    if (b.mtime !== a.mtime) return b.mtime - a.mtime
    return a.name < b.name ? -1 : (a.name > b.name ? 1 : 0)
  })
  return kept.slice(0, limit)
}

var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

function relativeTime(mtimeMs, nowMs) {
  var t = Number(mtimeMs) || 0
  var now = Number(nowMs) || 0
  if (t <= 0) return ""
  var s = Math.floor((now - t) / 1000)
  if (s < 45) return "just now"               // includes small clock skew into the future
  var m = Math.round(s / 60)
  if (m < 60) return Math.max(1, m) + "m ago"
  var h = Math.floor(s / 3600)
  if (h < 24) return h + "h ago"
  var d = Math.floor(s / 86400)
  if (d < 2) return "yesterday"
  if (d < 7) return d + "d ago"
  var date = new Date(t)
  var label = MONTHS[date.getMonth()] + " " + date.getDate()
  if (date.getFullYear() !== new Date(now).getFullYear()) label += ", " + date.getFullYear()
  return label
}

function formatSize(bytes) {
  var b = Math.max(0, Number(bytes) || 0)
  if (b < 1024) return b + " B"
  var units = ["KB", "MB", "GB", "TB"]
  var v = b / 1024
  var u = 0
  while (v >= 1024 && u < units.length - 1) { v /= 1024; u++ }
  var text = v < 10 ? v.toFixed(1) : String(Math.round(v))
  if (text.slice(-2) === ".0") text = text.slice(0, -2)
  return text + " " + units[u]
}

// file:// URI for an absolute path. Each segment is percent-encoded as UTF-8
// (spaces, #, %, ?, non-ASCII), and the slashes stay as they are.
function fileUri(path) {
  var p = String(path || "")
  return "file://" + p.split("/").map(function(seg) { return encodeURIComponent(seg) }).join("/")
}

// text/uri-list payload (RFC 2483): one URI per line, CRLF line endings.
function uriList(paths) {
  var list = Array.isArray(paths) ? paths : [paths]
  var out = ""
  for (var i = 0; i < list.length; i++) out += fileUri(list[i]) + "\r\n"
  return out
}

// What a dragged row offers. A terminal takes the plain path; a file manager,
// browser or chat app takes the URI list and gets the file itself.
function dragMimeData(path) {
  var p = String(path || "")
  return {
    "text/uri-list": uriList([p]),
    "text/plain;charset=utf-8": p,
    "text/plain": p
  }
}

// Click-to-copy: put the file on the clipboard as a file (text/uri-list), so
// Ctrl+Shift+V in a terminal pastes the path and Ctrl+V in a file manager or
// browser pastes the file. The URI travels as an argument, never as shell text.
function clipboardCommand(path) {
  return ["sh", "-c", "printf '%s\\r\\n' \"$1\" | wl-copy --type text/uri-list", "slingshot-copy", fileUri(path)]
}

function openCommand(path) {
  return ["xdg-open", String(path || "")]
}

// The probe used to tell an empty folder from one that is missing or blocked.
// Exit 0 = readable, 2 = missing, 3 = not readable.
function probeCommand(dir) {
  return ["sh", "-c", "[ -d \"$1\" ] || exit 2; [ -r \"$1\" ] && [ -x \"$1\" ] || exit 3; exit 0", "slingshot-probe", String(dir || "")]
}

function probeState(exitCode) {
  if (exitCode === 0) return "ready"
  if (exitCode === 2) return "missing"
  return "unreadable"
}

// Output of `xdg-user-dir DOWNLOAD; xdg-user-dir PICTURES`. xdg-user-dir
// answers $HOME for a directory the user never configured; that would list
// the whole home folder, so it falls back to the xdg-user-dirs default name.
function parseUserDirs(text, home) {
  var h = String(home || "").replace(/\/+$/, "")
  var lines = String(text || "").split("\n").map(function(l) { return l.trim() })
  function pick(value, fallbackName) {
    if (!value || value.charAt(0) !== "/" || value.replace(/\/+$/, "") === h) return h + "/" + fallbackName
    return value.replace(/\/+$/, "") || "/"
  }
  return { downloads: pick(lines[0], "Downloads"), pictures: pick(lines[1], "Pictures") }
}

function homeRelative(path, home) {
  var p = String(path || "")
  var h = String(home || "").replace(/\/+$/, "")
  if (h !== "" && (p === h || p.indexOf(h + "/") === 0)) return "~" + p.slice(h.length)
  return p
}

function folderLabel(key) {
  return key === "pictures" ? "Pictures" : "Downloads"
}

// Opening the dropdown without a manual pick shows whichever folder holds the
// newest file; ties go to Downloads.
function defaultFolder(downloadsNewest, picturesNewest) {
  return (Number(picturesNewest) || 0) > (Number(downloadsNewest) || 0) ? "pictures" : "downloads"
}

// The "new file" dot: a file newer than the last time the dropdown was seen,
// and younger than windowMs. Returns the ms left to show it, or 0.
function freshRemaining(newestMtime, seenAt, nowMs, windowMs) {
  var t = Number(newestMtime) || 0
  if (t <= (Number(seenAt) || 0)) return 0
  var left = (Number(windowMs) || 0) - ((Number(nowMs) || 0) - t)
  return left > 0 ? left : 0
}

function clampInt(value, lo, hi, fallback) {
  var n = Math.round(Number(value))
  if (!isFinite(n)) return fallback
  return Math.max(lo, Math.min(hi, n))
}

function moveCursor(index, delta, count) {
  if (count <= 0) return -1
  if (index < 0) return delta < 0 ? count - 1 : 0
  return Math.max(0, Math.min(count - 1, index + delta))
}
