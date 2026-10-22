#!/usr/bin/env bash
# Slingshot plugin checks. Never opens a window on your desktop.
#   1. omarchy-plugin-validate on the repo (it is the plugin)
#   2. Model.js unit tests (node --test)
#   3. offscreen render + end-to-end checks against fake folders
#      (output in ${SLINGSHOT_RENDER_DIR:-/tmp/slingshot-render})
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
status=0

echo "== omarchy-plugin-validate =="
if command -v omarchy-plugin-validate >/dev/null; then
  omarchy-plugin-validate . && echo "manifest: valid" || status=1
else
  echo "omarchy-plugin-validate not found; skipping"
fi

echo
echo "== Model.js (node --test) =="
if command -v node >/dev/null; then
  node --test tests/js || status=1
else
  echo "node not found; skipping" >&2; status=1
fi

echo
echo "== Offscreen render =="
tests/offscreen/render.sh --fake-data "${SLINGSHOT_RENDER_DIR:-/tmp/slingshot-render}" || status=1

echo
[[ $status -eq 0 ]] && echo "all passed" || echo "FAILED"
exit $status
