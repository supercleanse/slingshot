"use strict";
const test = require("node:test");
const strict = require("node:assert/strict");
const { fileURLToPath } = require("node:url");
// Values built inside the vm context have foreign prototypes; compare as plain JSON.
const plain = (x) => JSON.parse(JSON.stringify(x === undefined ? null : x));
const assert = Object.assign({}, strict, {
  deepEqual: (a, b, m) => strict.deepEqual(plain(a), plain(b), m),
});
const { loadModelJs } = require("./model_loader");

const Model = loadModelJs();
const NOW = Date.UTC(2026, 9, 21, 18, 0, 0);
const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;
const f = (name, ago, extra) => Object.assign({ name, path: "/home/demo/Downloads/" + name, mtime: NOW - ago, size: 1000, isDir: false }, extra);

test("isPartial catches every in-progress suffix, case-insensitively", () => {
  for (const n of ["a.part", "a.PART", "b.crdownload", "Unconfirmed 1234.crdownload", "c.download", "d.tmp", "x.zip.part"]) {
    assert.equal(Model.isPartial(n), true, n);
  }
  for (const n of ["part", ".part", "report.pdf", "partition.img", "a.tmpl", "download.png"]) {
    assert.equal(Model.isPartial(n), false, n);
  }
});

test("pickRecent: newest first, regular files only, hidden and partial excluded", () => {
  const entries = [
    f("old.pdf", 3 * DAY),
    f(".hidden", 1 * MIN),
    f("folder", 30 * 1000, { isDir: true }),
    f("big.iso.crdownload", 10 * 1000),
    f("screenshot.png", 2 * MIN),
    f("notes.txt", 1 * HOUR),
    f("scratch.tmp", 5 * 1000),
  ];
  const out = Model.pickRecent(entries, 10);
  assert.deepEqual(out.map((e) => e.name), ["screenshot.png", "notes.txt", "old.pdf"]);
  assert.equal(out[0].path, "/home/demo/Downloads/screenshot.png");
});

test("pickRecent: skips the empty placeholder Firefox keeps beside <name>.part", () => {
  const entries = [f("movie.mkv", 1 * MIN, { size: 0 }), f("movie.mkv.part", 1 * MIN, { size: 5e8 }), f("done.zip", 2 * MIN)];
  assert.deepEqual(Model.pickRecent(entries, 5).map((e) => e.name), ["done.zip"]);
});

test("pickRecent: respects the limit, breaks mtime ties by name, survives junk input", () => {
  const entries = [];
  for (let i = 0; i < 30; i++) entries.push(f("file-" + String(i).padStart(2, "0") + ".txt", i * MIN));
  entries.push(f("b-tie.txt", 0), f("a-tie.txt", 0));
  const out = Model.pickRecent(entries, 12);
  assert.equal(out.length, 12);
  assert.deepEqual(out.slice(0, 3).map((e) => e.name), ["a-tie.txt", "b-tie.txt", "file-00.txt"]);
  assert.deepEqual(Model.pickRecent(null, 5), []);
  assert.deepEqual(Model.pickRecent([null, {}, { name: "x" }], 5), []);
  assert.deepEqual(Model.pickRecent(entries, 0), []);
});

test("relativeTime covers seconds through dates", () => {
  assert.equal(Model.relativeTime(NOW - 5 * 1000, NOW), "just now");
  assert.equal(Model.relativeTime(NOW + 30 * 1000, NOW), "just now"); // small clock skew
  assert.equal(Model.relativeTime(NOW - 50 * 1000, NOW), "1m ago");
  assert.equal(Model.relativeTime(NOW - 2 * MIN, NOW), "2m ago");
  assert.equal(Model.relativeTime(NOW - 59 * MIN, NOW), "59m ago");
  assert.equal(Model.relativeTime(NOW - 3 * HOUR, NOW), "3h ago");
  assert.equal(Model.relativeTime(NOW - 30 * HOUR, NOW), "yesterday");
  assert.equal(Model.relativeTime(NOW - 4 * DAY, NOW), "4d ago");
  const tenDays = new Date(NOW - 10 * DAY);
  assert.equal(Model.relativeTime(tenDays.getTime(), NOW), Model.MONTHS[tenDays.getMonth()] + " " + tenDays.getDate());
  const lastYear = new Date(2025, 2, 3, 12).getTime();
  assert.equal(Model.relativeTime(lastYear, NOW), "Mar 3, 2025");
  assert.equal(Model.relativeTime(0, NOW), "");
});

test("formatSize uses binary units with one decimal under 10", () => {
  assert.equal(Model.formatSize(0), "0 B");
  assert.equal(Model.formatSize(999), "999 B");
  assert.equal(Model.formatSize(1024), "1 KB");
  assert.equal(Model.formatSize(1536), "1.5 KB");
  assert.equal(Model.formatSize(820 * 1024), "820 KB");
  assert.equal(Model.formatSize(1.4 * 1024 * 1024), "1.4 MB");
  assert.equal(Model.formatSize(12 * 1024 * 1024), "12 MB");
  assert.equal(Model.formatSize(3.25 * 1024 ** 3), "3.3 GB");
  assert.equal(Model.formatSize(-5), "0 B");
  assert.equal(Model.formatSize("nope"), "0 B");
});

test("fileUri percent-encodes spaces, #, %, ?, and unicode, and round-trips", () => {
  const cases = [
    ["/home/demo/Downloads/plain.txt", "file:///home/demo/Downloads/plain.txt"],
    ["/home/demo/Downloads/Screenshot 2026-10-21 at 9.41.png", "file:///home/demo/Downloads/Screenshot%202026-10-21%20at%209.41.png"],
    ["/home/demo/Downloads/report #3 (final).pdf", "file:///home/demo/Downloads/report%20%233%20(final).pdf"],
    ["/home/demo/Downloads/100% done?.txt", "file:///home/demo/Downloads/100%25%20done%3F.txt"],
    ["/home/demo/Pictures/été ⛵ 日本.jpg", "file:///home/demo/Pictures/%C3%A9t%C3%A9%20%E2%9B%B5%20%E6%97%A5%E6%9C%AC.jpg"],
    ["/home/demo/Downloads/a&b;c=d+e.txt", "file:///home/demo/Downloads/a%26b%3Bc%3Dd%2Be.txt"],
  ];
  for (const [p, uri] of cases) {
    assert.equal(Model.fileUri(p), uri);
    assert.equal(fileURLToPath(Model.fileUri(p)), p, "round-trip " + p);
  }
});

test("uriList and dragMimeData: CRLF-terminated URIs, plain path for terminals", () => {
  assert.equal(Model.uriList(["/a b/c.txt", "/d#e"]), "file:///a%20b/c.txt\r\nfile:///d%23e\r\n");
  const m = Model.dragMimeData("/home/demo/Downloads/my file.png");
  assert.equal(m["text/uri-list"], "file:///home/demo/Downloads/my%20file.png\r\n");
  assert.equal(m["text/plain"], "/home/demo/Downloads/my file.png");
  assert.equal(m["text/plain;charset=utf-8"], "/home/demo/Downloads/my file.png");
});

test("clipboardCommand passes the URI as an argument, never as shell text", () => {
  const cmd = Model.clipboardCommand("/tmp/it's \"quoted\" $(rm -rf).txt");
  assert.deepEqual(cmd.slice(0, 2), ["sh", "-c"]);
  assert.equal(cmd[2], "printf '%s\\r\\n' \"$1\" | wl-copy --type text/uri-list");
  assert.equal(cmd[4], "file:///tmp/it's%20%22quoted%22%20%24(rm%20-rf).txt");
  // Run the same script with wl-copy swapped for cat: one CRLF-terminated URI out.
  const script = cmd[2].replace("wl-copy --type text/uri-list", "cat");
  const out = require("node:child_process").execFileSync("sh", ["-c", script, cmd[3], cmd[4]]);
  assert.equal(out.toString("utf8"), cmd[4] + "\r\n");
  assert.deepEqual(Model.openCommand("/x y"), ["xdg-open", "/x y"]);
});

test("probeState maps the probe's exit codes", () => {
  assert.equal(Model.probeState(0), "ready");
  assert.equal(Model.probeState(2), "missing");
  assert.equal(Model.probeState(3), "unreadable");
  assert.equal(Model.probeState(1), "unreadable");
});

test("parseUserDirs reads xdg-user-dir output and never lists $HOME itself", () => {
  assert.deepEqual(Model.parseUserDirs("/home/demo/Dl\n/home/demo/Pics\n", "/home/demo"), { downloads: "/home/demo/Dl", pictures: "/home/demo/Pics" });
  assert.deepEqual(Model.parseUserDirs("/home/demo\n/home/demo/\n", "/home/demo"), { downloads: "/home/demo/Downloads", pictures: "/home/demo/Pictures" });
  assert.deepEqual(Model.parseUserDirs("", "/home/demo/"), { downloads: "/home/demo/Downloads", pictures: "/home/demo/Pictures" });
  assert.deepEqual(Model.parseUserDirs("relative\n/srv/pics/\n", "/home/demo"), { downloads: "/home/demo/Downloads", pictures: "/srv/pics" });
});

test("homeRelative, folderLabel, defaultFolder", () => {
  assert.equal(Model.homeRelative("/home/demo/Downloads", "/home/demo"), "~/Downloads");
  assert.equal(Model.homeRelative("/home/demonstration/x", "/home/demo"), "/home/demonstration/x");
  assert.equal(Model.folderLabel("pictures"), "Pictures");
  assert.equal(Model.folderLabel("downloads"), "Downloads");
  assert.equal(Model.defaultFolder(NOW - MIN, NOW), "pictures");
  assert.equal(Model.defaultFolder(NOW, NOW - MIN), "downloads");
  assert.equal(Model.defaultFolder(NOW, NOW), "downloads");
  assert.equal(Model.defaultFolder(0, 0), "downloads");
});

test("freshRemaining: only files newer than the last look, inside the window", () => {
  assert.equal(Model.freshRemaining(NOW - 10 * 1000, NOW - MIN, NOW, 60 * 1000), 50 * 1000);
  assert.equal(Model.freshRemaining(NOW - 10 * 1000, NOW - 5 * 1000, NOW, 60 * 1000), 0); // already seen
  assert.equal(Model.freshRemaining(NOW - 2 * MIN, NOW - HOUR, NOW, 60 * 1000), 0);        // too old
  assert.equal(Model.freshRemaining(0, 0, NOW, 60 * 1000), 0);
});

test("kindFor, glyphFor, isThumbnailable", () => {
  assert.equal(Model.kindFor("a.PNG"), "image");
  assert.equal(Model.kindFor("a.tar.gz"), "archive");
  assert.equal(Model.kindFor("Makefile"), "file");
  assert.equal(Model.kindFor(".bashrc"), "file");
  assert.equal(Model.glyphFor("x.pdf"), Model.GLYPHS.pdf);
  assert.equal(Model.glyphFor("x.unknown"), Model.GLYPHS.file);
  assert.equal(Model.isThumbnailable("shot.webp"), true);
  assert.equal(Model.isThumbnailable("photo.heic"), false); // no Qt plugin: glyph instead
  assert.equal(Model.isThumbnailable("doc.pdf"), false);
});

test("clampInt and moveCursor", () => {
  assert.equal(Model.clampInt("40", 5, 30, 12), 30);
  assert.equal(Model.clampInt(undefined, 5, 30, 12), 12);
  assert.equal(Model.clampInt(7.4, 5, 30, 12), 7);
  assert.equal(Model.moveCursor(-1, 1, 5), 0);
  assert.equal(Model.moveCursor(-1, -1, 5), 4);
  assert.equal(Model.moveCursor(4, 1, 5), 4);
  assert.equal(Model.moveCursor(2, -1, 5), 1);
  assert.equal(Model.moveCursor(0, 1, 0), -1);
});
