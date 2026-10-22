#!/usr/bin/env bash
# Renders Slingshot offscreen and runs its end-to-end checks. Quickshell runs
# with QT_QPA_PLATFORM=offscreen, a fake HOME (make_fixtures.py), and a private
# XDG_RUNTIME_DIR, with no WAYLAND_DISPLAY or Hyprland socket in reach: no
# window maps, nothing under your real home is read or written, and the live
# omarchy-shell is never contacted.
#
# Usage: tests/offscreen/render.sh --fake-data <out-dir>
#
# --fake-data is required on purpose: everything on screen comes from the
# canned fixtures. There is no mode that renders your real folders.
set -euo pipefail

usage() { echo "usage: $0 --fake-data <out-dir>" >&2; exit 2; }
[[ $# -eq 2 && "$1" == "--fake-data" ]] || usage
OUT=$(realpath -m "$2")
mkdir -p "$OUT"

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SHELL_KIT=${OMARCHY_PATH:-/usr/share/omarchy}/shell
command -v quickshell >/dev/null || { echo "quickshell not found" >&2; exit 1; }
[[ -d "$SHELL_KIT/Commons" && -d "$SHELL_KIT/Ui" ]] || { echo "Omarchy shell kit not found at $SHELL_KIT" >&2; exit 1; }

WORK="$OUT/.work"
cleanup() {
  chmod -R u+rwx "$WORK" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT
cleanup
mkdir -p "$WORK/stage/Ui" "$WORK/runtime"
chmod 700 "$WORK/runtime"

# Stage: the kit and the plugin side by side (Quickshell resolves qs.* from
# the config root), with DropdownWindow swapped for an inline stub. The stage
# holds symlinks, so it lives here, never inside the plugin folder.
STAGE="$WORK/stage"
ln -s "$SHELL_KIT/Commons" "$STAGE/Commons"
for f in "$SHELL_KIT"/Ui/*; do ln -s "$f" "$STAGE/Ui/$(basename "$f")"; done
for f in Model.js Widget.qml Content.qml FileRow.qml FolderFeed.qml; do ln -s "$ROOT/$f" "$STAGE/$f"; done
cp "$ROOT/tests/offscreen/DropdownWindowStub.qml" "$STAGE/DropdownWindow.qml"
cp "$ROOT/tests/offscreen/harness.qml" "$STAGE/shell.qml"

FAKE_HOME="$WORK/home"
python3 "$ROOT/tests/offscreen/make_fixtures.py" "$FAKE_HOME" >/dev/null

LOG="$OUT/harness.log"
set +e
env -u WAYLAND_DISPLAY -u DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u QS_CONFIG_PATH -u DBUS_SESSION_BUS_ADDRESS -u QT_QPA_PLATFORMTHEME -u QT_STYLE_OVERRIDE \
  QT_QPA_PLATFORM=offscreen \
  HOME="$FAKE_HOME" \
  XDG_CONFIG_HOME="$FAKE_HOME/.config" \
  XDG_CACHE_HOME="$WORK/cache" \
  XDG_STATE_HOME="$WORK/state" \
  XDG_DATA_HOME="$WORK/data" \
  XDG_RUNTIME_DIR="$WORK/runtime" \
  SLINGSHOT_SHOT_DIR="$OUT" \
  timeout 90 quickshell -p "$STAGE/shell.qml" >"$LOG" 2>&1
rc=$?
set -e
sed -i 's/\x1b\[[0-9;]*m//g' "$LOG"

ERRORS="ERROR|Failed to load|is not a type|Cannot assign|ReferenceError|TypeError|Unable to assign|is not defined|is not a function|Type error"
status=0
if grep -qE "$ERRORS" "$LOG"; then
  echo "render: QML errors (see $LOG):" >&2
  grep -E "$ERRORS" "$LOG" >&2
  status=1
fi
grep -E "CHECK (ok|FAIL)" "$LOG" | sed 's/^.*CHECK /  /' || true
if ! grep -q "HARNESS DONE failures=0" "$LOG"; then
  echo "render: harness did not finish cleanly (exit $rc); see $LOG" >&2
  status=1
fi
count=$(ls "$OUT"/*.png 2>/dev/null | wc -l)
echo "render: $count PNG(s) in $OUT"
exit $status
