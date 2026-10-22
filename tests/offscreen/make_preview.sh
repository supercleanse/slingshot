#!/usr/bin/env bash
# Composes preview.png from the offscreen renders (canned fixture data only):
# the Pictures list in a dark theme beside the Downloads list in a light one.
#
#   tests/offscreen/render.sh --fake-data <out-dir>
#   tests/offscreen/make_preview.sh <out-dir>
set -euo pipefail
OUT=$(realpath "${1:?usage: $0 <out-dir>}")
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
command -v magick >/dev/null || { echo "ImageMagick (magick) is required" >&2; exit 1; }
for f in dark-pictures light-downloads; do
  [[ -f "$OUT/$f.png" ]] || { echo "missing $OUT/$f.png; run render.sh first" >&2; exit 1; }
done
magick \
  \( "$OUT/dark-pictures.png" -crop 400x640+160+0 +repage \) \
  \( -size 24x640 xc:"#0b0b0b" \) \
  \( "$OUT/light-downloads.png" -crop 400x640+160+0 +repage \) \
  +append "$ROOT/preview.png"
echo "wrote $ROOT/preview.png"
