#!/usr/bin/env python3
"""Paste one file into the window that had focus before the dropdown opened.

    paste.py <path> <window-address> <delay-ms>

Run detached by Widget.qml on a click (or Enter). Opening the dropdown moves
keyboard focus to the panel, so the widget remembers the last real window
while the dropdown is closed and passes its address here.

1. Look the window up. If it is gone, or not on a visible workspace, there is
   nothing sensible to paste into: copy the file and say so.
2. Put the right thing on the clipboard. A terminal (Omarchy's `terminal` tag,
   or a known terminal class) gets the shell-quoted path as plain text, so the
   paste is a path and never a file:// URI with a trailing newline. Anything
   else gets the file as text/uri-list, which browsers, Electron chat apps and
   file managers paste as the file itself.
3. Wait out the dropdown closing, focus the window, and send it the paste
   chord through Hyprland. wtype cannot do this: a virtual keyboard merges
   with whatever modifier is physically held. A chord sent to an unfocused
   window is dropped, so the focus step is required.

SLINGSHOT_HYPRCTL, SLINGSHOT_WLCOPY and SLINGSHOT_NOTIFY swap the external
commands for the tests.
"""

import json
import os
import re
import shlex
import subprocess
import sys
import time
from urllib.parse import quote

HYPRCTL = os.environ.get("SLINGSHOT_HYPRCTL", "hyprctl")
WLCOPY = os.environ.get("SLINGSHOT_WLCOPY", "wl-copy")
NOTIFY = os.environ.get("SLINGSHOT_NOTIFY", "notify-send")

TERMINAL_CLASS = re.compile(r"alacritty|foot|kitty|ghostty|wezterm|konsole|gnome-terminal|ptyxis", re.I)
ADDRESS = re.compile(r"^0x[0-9a-f]+$", re.I)


def run(cmd, data=None):
    try:
        if data is None:
            out = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=3)
            return out.stdout
        subprocess.run(cmd, input=data, text=True, timeout=3)
        return ""
    except (OSError, subprocess.SubprocessError):
        return ""


def hypr_json(what):
    try:
        return json.loads(run([HYPRCTL, "-j", what]) or "null")
    except ValueError:
        return None


def dispatch(lua):
    run([HYPRCTL, "dispatch", lua])


def file_uri(path):
    return "file://" + quote(path, safe="/-_.~!'()*")


def is_terminal(win):
    tags = [str(t).rstrip("*") for t in win.get("tags") or []]
    return "terminal" in tags or bool(TERMINAL_CLASS.search(str(win.get("class") or "")))


def find_target(address):
    """The client dict for `address` when it exists on a visible workspace."""
    if not ADDRESS.match(address or ""):
        return None
    win = next((c for c in hypr_json("clients") or [] if c.get("address") == address), None)
    if not win:
        return None
    visible = set()
    for m in hypr_json("monitors") or []:
        visible.add((m.get("activeWorkspace") or {}).get("id"))
        special = (m.get("specialWorkspace") or {}).get("id")
        if special:
            visible.add(special)
    return win if (win.get("workspace") or {}).get("id") in visible else None


def copy_file(path):
    run([WLCOPY, "--type", "text/uri-list"], file_uri(path) + "\r\n")


def active_address():
    """The focused window's address, or "" (an empty workspace, a panel)."""
    w = hypr_json("activewindow") or {}
    a = str(w.get("address") or "") if isinstance(w, dict) else ""
    return a if ADDRESS.match(a) else ""


def paste(path, address, delay):
    """Paste `path` into the window at `address`; `delay` is in seconds."""
    win = find_target(address)
    if win is None:
        copy_file(path)
        run([NOTIFY, "-a", "Slingshot", "No window to paste into",
             "Copied " + os.path.basename(path) + " to the clipboard instead."])
        return

    if is_terminal(win):
        run([WLCOPY], shlex.quote(path))
        mods = "CTRL + SHIFT"
    else:
        copy_file(path)
        mods = "CTRL"

    time.sleep(delay)
    target = 'window = "address:%s"' % address
    dispatch("hl.dsp.focus({ %s })" % target)
    time.sleep(0.12)
    # Down, a short hold, then up: send_shortcut can leave the modifier stuck.
    for state in ("down", "up"):
        dispatch('hl.dsp.send_key_state({ mods = "%s", key = "V", state = "%s", %s })' % (mods, state, target))
        time.sleep(0.05)


def main(argv):
    if len(argv) != 4:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    path, address, delay_ms = argv[1], argv[2], argv[3]
    try:
        delay = max(0, int(delay_ms)) / 1000
    except ValueError:
        delay = 0.35
    paste(path, address, delay)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
