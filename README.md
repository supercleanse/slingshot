# Slingshot

Your newest downloads and screenshots, one click away, for the
[Omarchy](https://omarchy.org) bar.

Slingshot puts a tray icon in the bar. Click it and a dropdown lists the
latest files in your Downloads or Pictures folder, with thumbnails for
images. Drag any file straight out onto another app:

- **a terminal** (foot, Ghostty, Alacritty, Kitty) gets the file's path typed
  at the cursor, which is how you hand a screenshot to Claude Code or any other
  CLI;
- **a browser or chat app** attaches the file;
- **a file manager** copies it.

Or click a file to put it on the clipboard as a file, then paste wherever you
like.

![Slingshot in a dark and a light theme](preview.png)

## What it does

- **Bar icon.** A tray glyph that toggles the dropdown. A small accent dot
  shows when a new file landed in the last minute and you haven't looked yet.
- **Downloads | Pictures.** A two-way switch at the top. Until you pick one,
  each open shows whichever folder holds the newest file (Pictures if your
  latest screenshot is newer than your latest download, Downloads otherwise).
  Once you pick a folder by hand, Slingshot stays on it until the shell
  restarts.
- **The list.** The newest 12 regular files (configurable, 5 to 30) by
  modification time, not recursive. Hidden files, folders and downloads still
  in progress (`.part`, `.crdownload`, `.download`, `.tmp`, plus the empty
  placeholder Firefox writes beside a `.part` file) never show. Each row has a
  thumbnail or a file-type glyph, the name (shortened in the middle when long),
  how long ago it changed, and its size.
- **Live.** The list updates by itself as files arrive or get renamed. It uses
  inotify through Qt's folder model, so nothing polls, open or closed.
- **Folders from XDG.** Paths come from `xdg-user-dir DOWNLOAD` and
  `xdg-user-dir PICTURES` (your `~/.config/user-dirs.dirs`), never hard-coded.
  A folder that is missing or unreadable says so instead of looking empty.
- **Footer.** "Open Downloads in file browser" (or Pictures) runs `xdg-open`
  on the folder and closes the dropdown.

### Mouse and keyboard

| In the dropdown | Does |
|---|---|
| Drag a row | Drag the file onto another app |
| Click a row | Copy the file to the clipboard (`text/uri-list`), then close |
| Middle-click a row | Open the file with its default app |
| `j` / `k` or arrows | Move the cursor |
| `Enter` / `Space` | Copy the file under the cursor |
| `o` | Open the file under the cursor |
| `h` / `l`, `d` / `p` | Switch to Downloads / Pictures |
| `f` | Open the folder in your file browser |
| `Tab` | Move to the next bar panel (Omarchy's usual) |
| `Esc` | Close |

The clipboard copy offers the file as `text/uri-list`, so Ctrl+Shift+V in a
terminal pastes its path and Ctrl+V in a file manager or browser pastes the
file itself.

## Install

From the Omarchy plugin catalog, or straight from git:

```bash
omarchy plugin add https://github.com/supercleanse/slingshot
omarchy plugin enable supercleanse.slingshot
```

Plugins land disabled so you can read the code first. Bar widgets start in
the right section; move it with `omarchy bar move` or by dragging it in the
bar.

From a local checkout, `./install.sh` copies the plugin into
`~/.config/omarchy/plugins/supercleanse.slingshot/` (and links
`bin/slingshot-ssh` into `~/.local/bin/` when it is there). Then run
`omarchy plugin enable supercleanse.slingshot`.

Slingshot needs `wl-clipboard` (for click-to-copy), `xdg-user-dirs` and
`xdg-utils`, all present on a stock Omarchy install.

### A keybinding

The widget answers the usual panel IPC:

```bash
omarchy-shell supercleanse.slingshot toggle   # also open, close
```

So in `~/.config/hypr/bindings.lua`, for example:

```lua
o.bind("SUPER + ALT + D", "Slingshot", "omarchy-shell supercleanse.slingshot toggle")
```

### Settings

Set these on the widget's entry in `~/.config/omarchy/shell.json`:

| Key | Default | Meaning |
|---|---|---|
| `maxItems` | `12` | Files to list, 5 to 30 |
| `showIndicator` | `true` | Show the new-file dot. When off, folders are only watched while the dropdown is open. |
| `thumbnails` | `true` | Image thumbnails (off shows a glyph for every file) |

## How the drag works

Each row is a real Wayland drag source (Qt Quick's `Drag.Automatic`). It
offers three types: `text/uri-list` (a percent-encoded `file://` URI ending in
CRLF), `text/plain` and `text/plain;charset=utf-8` (the absolute path). The
only action offered is copy, so no app can move or delete your file.

Omarchy's popups are full-screen overlay surfaces that catch clicks outside
the card to close themselves. Left alone, that overlay would sit above every
app and swallow the drop. Slingshot's popup (`DropdownWindow.qml`, adapted
from Omarchy's `KeyboardPanel`) keeps its surface mapped for the whole drag,
since the drag source has to outlive the drop, but shrinks its input region
to the card and drops its click-catchers on other monitors while a drag is in
flight. After an app accepts the drop the dropdown closes; if you cancel
(Esc, or let go over nothing) it stays open so you can try again.

## SSH drop proxy

Dropping a file on a terminal pastes a local path, which is useless when that
terminal is in an SSH session. `bin/slingshot-ssh` wraps `ssh` so a dropped
local file path is uploaded to the remote host and the remote path is typed
instead. See [docs/slingshot-ssh.md](docs/slingshot-ssh.md).

## Development

```bash
tests/run.sh
```

runs `omarchy-plugin-validate`, the `Model.js` unit tests (`node --test
tests/js`), and an offscreen render: `tests/offscreen/render.sh --fake-data
<dir>` starts Quickshell with `QT_QPA_PLATFORM=offscreen`, a throwaway HOME
full of canned files (`tests/offscreen/make_fixtures.py`), and no Wayland or
Hyprland socket in reach. It loads the real `Widget.qml`, checks folder
discovery, ordering and filtering, live refresh, the new-file dot, the default
folder, and the empty, missing and unreadable states, and writes a PNG per
state. `tests/offscreen/make_preview.sh <dir>` builds `preview.png` from
those renders.

`Content.qml` is the dropdown body with no processes, file access or windows
of its own, so it renders standalone with canned data. External drag and drop
can't be exercised offscreen; check it by hand:

1. Open the dropdown and drag a screenshot onto a foot window: its path
   appears at the prompt and the dropdown closes.
2. Drag a file onto a browser upload field or chat window: it attaches.
3. Drag a file into a file manager: it's copied, and the original stays put.
4. Start a drag and press Esc, or let go over the bar: nothing happens and the
   dropdown stays open.
5. With two monitors, drag a file onto a window on the other one.
6. Click a row, then Ctrl+Shift+V in foot: the path pastes.
7. Save a new screenshot with the dropdown closed: the dot appears, and the
   file is first in the list when you open it.

## Credits

`DropdownWindow.qml` is adapted from `shell/Ui/KeyboardPanel.qml` in
[Omarchy](https://github.com/basecamp/omarchy) (MIT). Glyphs are from Nerd
Fonts (Material Design Icons).

## License

MIT. See [LICENSE](LICENSE).
