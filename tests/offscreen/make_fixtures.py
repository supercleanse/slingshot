#!/usr/bin/env python3
"""Build a fake home for the offscreen harness. Test data only; never shipped.

    make_fixtures.py <fake-home>

Creates <fake-home>/.config/user-dirs.dirs pointing at Downloads and Pictures
folders full of canned files with staged modification times, plus the edge
cases Slingshot must hide: a hidden file, a directory, a partial download,
and the empty placeholder Firefox writes beside "<name>.part". Large sizes are
sparse files, so nothing real is written to disk. Images are tiny generated
PNGs (pure Python, no dependencies) so thumbnails have something to load.
"""
from __future__ import annotations

import os
import struct
import sys
import time
import zlib
from pathlib import Path

MIN, HOUR, DAY = 60, 3600, 86400


def png(path: Path, w: int, h: int, paint) -> None:
    rows = bytearray()
    for y in range(h):
        rows.append(0)
        for x in range(w):
            rows.extend(paint(x, y))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))


def screenshot(x: int, y: int) -> tuple[int, int, int]:
    # A dark editor window with a title bar and a few "lines of code".
    if y < 14:
        return (48, 52, 64)
    if 30 < y < 150 and 20 < x < 300 and (y // 12) % 2 == 0 and x < 60 + (y * 7) % 220:
        return (122, 162, 247) if (y // 12) % 3 else (230, 142, 13)
    return (26, 27, 38)


def chart(x: int, y: int) -> tuple[int, int, int]:
    bars = [60, 110, 85, 140, 120]
    i = x // 64
    if i < len(bars) and x % 64 > 12 and y > 180 - bars[i]:
        return (230, 142, 13)
    return (240, 240, 236)


def mountains(x: int, y: int) -> tuple[int, int, int]:
    ridge = 120 - abs((x % 160) - 80) * 0.9
    if y > ridge + 40:
        return (40, 60, 70)
    if y > ridge:
        return (90, 110, 125)
    t = y / 200
    return (int(250 - 90 * t), int(180 - 40 * t), int(120 + 80 * t))


def sunset(x: int, y: int) -> tuple[int, int, int]:
    dx, dy = x - 120, y - 110
    if y > 120:
        return (40, 90, 140)
    if dx * dx + dy * dy < 40 * 40:
        return (250, 200, 90)
    return (240, 140, 100)


SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="240" height="160" viewBox="0 0 240 160">
<rect width="240" height="160" fill="#eff1f5"/>
<rect x="20" y="20" width="80" height="40" rx="6" fill="#1e66f5"/>
<rect x="140" y="100" width="80" height="40" rx="6" fill="#e68e0d"/>
<path d="M100 40 C 130 40, 130 120, 140 120" stroke="#4c4f69" stroke-width="4" fill="none"/>
</svg>
"""


def put(path: Path, age: int, size: int | None = None, content: bytes | None = None) -> None:
    if content is not None:
        path.write_bytes(content)
    elif not path.exists():
        path.touch()
    if size is not None:
        os.truncate(path, size)
    t = time.time() - age
    os.utime(path, (t, t))


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    home = Path(sys.argv[1])
    dl, pics = home / "Downloads", home / "Pictures"
    for d in (home / ".config", dl, pics, home / "Empty"):
        d.mkdir(parents=True, exist_ok=True)
    (home / ".config" / "user-dirs.dirs").write_text(
        'XDG_DOWNLOAD_DIR="$HOME/Downloads"\nXDG_PICTURES_DIR="$HOME/Pictures"\n'
    )

    # Pictures: the newest file overall at start, so the dropdown opens here.
    png(pics / "Screenshot 2026-10-21 at 14.32.07.png", 320, 200, screenshot)
    put(pics / "Screenshot 2026-10-21 at 14.32.07.png", 2 * MIN)
    png(pics / "Screenshot 2026-10-21 at 13.10.55.png", 320, 200, chart)
    put(pics / "Screenshot 2026-10-21 at 13.10.55.png", 1 * HOUR + 5 * MIN)
    png(pics / "wallpaper-mountains.png", 320, 200, mountains)
    put(pics / "wallpaper-mountains.png", 2 * DAY)
    put(pics / "diagram.svg", 6 * DAY, content=SVG.encode())
    put(pics / "IMG_2041.HEIC", 9 * DAY, size=3_100_000)

    # Downloads: ordinary files, oldest to newest.
    put(dl / "song.flac", 40 * DAY, size=31_000_000)
    put(dl / "archive.tar.gz", 20 * DAY, size=48_500_000)
    put(dl / "dataset.csv", 12 * DAY, size=640_000)
    put(dl / "notes.md", 4 * DAY, content=b"# notes\n")
    png(dl / "sunset été ⛵.png", 240, 200, sunset)
    put(dl / "sunset été ⛵.png", 3 * DAY)
    put(dl / "omarchy-3.2.iso", 30 * HOUR, size=2_254_857_830)
    put(dl / "invoice #4412.pdf", 5 * HOUR, size=184_320)
    put(dl / "Q3 board deck (final).pdf", 2 * HOUR, size=2_516_582)

    # Things Slingshot must never list, all newer than everything above.
    put(dl / "big-video.mkv", 1 * MIN, size=0)                 # Firefox placeholder
    put(dl / "big-video.mkv.part", 1 * MIN, size=512_000_000)  # in progress
    put(dl / "Unconfirmed 81723.crdownload", 30, size=9_000_000)
    put(dl / ".hidden-config", 20, content=b"x")
    (dl / "a-folder").mkdir(exist_ok=True)

    # Edge-case folders for the state checks.
    (home / "Locked").mkdir(exist_ok=True)
    (home / "Locked").chmod(0)
    print(f"fixtures in {home}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
