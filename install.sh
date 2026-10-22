#!/usr/bin/env bash
# Install Slingshot from this checkout: copies (never symlinks) the Quickshell
# plugin into ~/.config/omarchy/plugins/supercleanse.slingshot/ and links the
# slingshot-ssh helper into ~/.local/bin when it is present. Safe to re-run.
#
#   ./install.sh            install or update, then ask the shell to rescan
#
# It does not enable the widget. Afterwards:
#   omarchy plugin enable supercleanse.slingshot
#
# (`omarchy plugin add https://github.com/supercleanse/slingshot` is the other
# way in: it clones this repo as the plugin folder directly.)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ID="supercleanse.slingshot"
PLUGIN_DIR="${HOME}/.config/omarchy/plugins/${PLUGIN_ID}"
BIN_DIR="${HOME}/.local/bin"
FILES=(Widget.qml DropdownWindow.qml Content.qml FileRow.qml FolderFeed.qml Model.js LICENSE)

case "${1:-}" in
  -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
  "") ;;
  *) echo "unknown option: $1" >&2; exit 2 ;;
esac

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
for f in manifest.json "${FILES[@]}"; do
  [ -f "${HERE}/${f}" ] || { echo "missing ${HERE}/${f}" >&2; exit 1; }
done
if command -v omarchy-plugin-validate >/dev/null 2>&1; then
  omarchy-plugin-validate "${HERE}" || { echo "manifest failed validation; not installing" >&2; exit 1; }
fi

# The shell's QML engine keeps compiled components keyed by file URL, so a
# hot reload of an unchanged path can keep running the old code. Each install
# lands the QML in a fresh runtime-<stamp>/ directory and points the
# manifest's entry point at it; older runtime dirs are removed.
STAMP="$(date +%Y%m%d-%H%M%S)"
RUNTIME="runtime-${STAMP}"
mkdir -p "${PLUGIN_DIR}"
find "${PLUGIN_DIR}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
mkdir -p "${PLUGIN_DIR}/${RUNTIME}"
for f in "${FILES[@]}"; do
  install -m 0644 "${HERE}/${f}" "${PLUGIN_DIR}/${RUNTIME}/${f}"
done
python3 - "${HERE}/manifest.json" "${PLUGIN_DIR}/manifest.json" "${RUNTIME}" <<'PY'
import json, sys
src, dst, runtime = sys.argv[1:4]
with open(src) as fh:
    manifest = json.load(fh)
manifest["entryPoints"] = {k: runtime + "/" + v for k, v in manifest["entryPoints"].items()}
with open(dst, "w") as fh:
    json.dump(manifest, fh, indent=2)
    fh.write("\n")
PY
echo "plugin  -> ${PLUGIN_DIR} (${RUNTIME})"

# SSH drop proxy (docs/slingshot-ssh.md). Linked, not copied, so it tracks
# this checkout.
if [ -f "${HERE}/bin/slingshot-ssh" ]; then
  mkdir -p "${BIN_DIR}"
  chmod +x "${HERE}/bin/slingshot-ssh"
  ln -sfn "${HERE}/bin/slingshot-ssh" "${BIN_DIR}/slingshot-ssh"
  echo "helper  -> ${BIN_DIR}/slingshot-ssh"
fi

if command -v omarchy-shell >/dev/null 2>&1; then
  omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
fi
echo "done. Enable it with: omarchy plugin enable ${PLUGIN_ID}"
