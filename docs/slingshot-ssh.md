# slingshot-ssh

`slingshot-ssh` is a drop-in replacement for `ssh` that makes file drag-and-drop
work across an SSH session. Drag a screenshot onto foot while you are logged in
to the MacBook, and the file is copied to the Mac and the Mac's path is typed
instead of your local one, so Claude Code (or anything else) running there can
open it.

It is one Python 3 file with no dependencies beyond the standard library:
`bin/slingshot-ssh`.

## How it works

When you drop a file on foot, foot pastes the file's local path into the
terminal. Over SSH that path means nothing on the other machine.

`slingshot-ssh` runs the real `ssh` inside a small pseudo-terminal and relays
bytes both ways. It watches what you type for a paste made up entirely of paths
to files that exist on this machine. When it sees one, it:

1. uploads each file over the SSH connection you already have open (OpenSSH
   connection sharing, so there is no second password or 2FA prompt),
2. saves it in `~/Downloads/Slingshot` on the remote host, adding `-2`, `-3`, ...
   to the name instead of ever overwriting a file,
3. types the remote paths in place of the local ones, quoted the same way the
   original was, and wrapped in the same bracketed-paste markers.

Anything that is not entirely existing local files passes through byte for
byte: typing, ordinary pastes, a paste of a directory, a path that does not
exist, or a mix of a path and other words.

If an upload takes longer than 300 ms, a desktop notification (`notify-send`)
says so. Notifications go to the desktop rather than the terminal so they can
never scribble over a full-screen program like herdr or vim. Press Ctrl-C while
an upload is running to cancel it; the original paste goes through.

If an upload fails, or the files are over the size limit (200 MB by default),
the original paste goes through unchanged and a notification explains why.

### When it stays out of the way

`slingshot-ssh` simply runs `ssh` with your arguments, unchanged, whenever the
session is not interactive:

- stdin or stdout is not a terminal (pipes, scripts, `git`, `rsync`, `scp`),
- a remote command is given (`ssh host uptime`), unless you also force a tty
  with `-t` or `RequestTTY=yes`, as in `ssh -t macbook herdr`,
- any of `-N -W -O -Q -G -V -f -n -T -s`, or `-o` options such as
  `RequestTTY=no` or `SessionType=none`,
- the arguments cannot be parsed with certainty (an unknown option, a missing
  value), or `ssh -G` fails or takes more than three seconds,
- `SLINGSHOT_SSH_DISABLE=1` is set.

### Connection sharing

For interactive sessions it adds
`-o ControlMaster=auto -o ControlPath=$XDG_RUNTIME_DIR/slingshot-ssh/cm-%C -o ControlPersist=120`.
It skips this if you passed `-S`, `ControlPath`, or `ControlMaster` yourself,
or if your `~/.ssh/config` already turns on connection sharing for that host;
uploads then use your setup. Uploads run with `BatchMode=yes` and never read
from your terminal, so they can't steal keystrokes or show a password prompt in
the middle of your session.

With `ControlPersist=120`, the shared connection stays up for two minutes after
you log out, so reconnecting in that window is instant.

## Install and opt in

Put `bin/slingshot-ssh` on your `PATH` (for example, symlink it into
`~/.local/bin`). To use it every time you type `ssh`, add this to `~/.bashrc`:

```bash
# Route interactive ssh through slingshot-ssh (drag-and-drop file upload).
# Non-interactive uses (commands, pipes, -N, -W, ...) pass straight to ssh.
if command -v slingshot-ssh >/dev/null 2>&1; then
  ssh() { slingshot-ssh "$@"; }
fi
```

Bash completion for `ssh` keeps working, since the command is still named
`ssh`. To bypass it once, run `command ssh ...` or
`SLINGSHOT_SSH_DISABLE=1 ssh ...`.

Symlinking `slingshot-ssh` as `ssh` earlier on `PATH` also works: it finds the
real `ssh` by skipping itself.

## Configuration

Optional, in `~/.config/slingshot/config.toml` (or `$XDG_CONFIG_HOME/slingshot/`):

```toml
[ssh]
remote_dir = "~/Downloads/Slingshot"   # where dropped files land on the remote
max_size_mb = 200                       # larger drops pass through untouched
notify = true                           # notify-send for slow/failed uploads
```

Environment variables override the file:

| Variable | Meaning |
|:--|:--|
| `SLINGSHOT_REMOTE_DIR` | remote drop dir (`~/...` is expanded on the remote) |
| `SLINGSHOT_MAX_SIZE_MB` | size limit for one drop, all files together |
| `SLINGSHOT_NOTIFY=0` | never call `notify-send` |
| `SLINGSHOT_SSH_DISABLE=1` | run plain `ssh` |
| `SLINGSHOT_SSH_BIN` | path of the real `ssh` (default: first `ssh` on `PATH` that is not this script) |
| `SLINGSHOT_CONFIG` | config file path |
| `SLINGSHOT_SSH_DEBUG` | append a debug log to this file |

`slingshot-ssh --slingshot-help` and `--slingshot-version` print help and the
version.

## What foot sends on a drop

Checked against the foot 1.28.0 source (`selection.c`, `decode_one_uri` and
`begin_receive_clipboard`):

- foot prefers `text/uri-list` for a drop. Each `file://` URI on the local host
  becomes its percent-decoded path; other URIs are pasted as-is.
- Several files are joined with a single space.
- On the normal screen (a shell prompt), each path is wrapped in single quotes:
  `'/home/me/Pictures/shot.png' '/home/me/a b.txt'`.
- On the alternate screen (herdr, vim, Claude Code), paths are not quoted, even
  when they contain spaces: `/home/me/a b.txt /home/me/c.txt`.
- A `'` in a file name becomes `\'` in both cases. Inside single quotes that is
  not valid shell quoting, so `slingshot-ssh` understands foot's form as well as
  the POSIX form `'\''`.
- The drop is wrapped in `ESC[200~ ... ESC[201~` when the program has turned on
  bracketed paste, and is not wrapped otherwise.

`slingshot-ssh` therefore handles single, double, and backslash quoting,
`file://` URIs, and unquoted paths with spaces. For the unquoted case it splits
on spaces and picks the longest existing file names. Paths separated by spaces,
tabs, or newlines all work. Without bracketed paste, a drop is recognized when
the whole path list arrives in one read, which is how a terminal writes a paste.

Nothing depends on foot itself. Inside a local herdr pane, herdr forwards the
paste to the pane (re-wrapping it in bracketed paste if the pane asked for it),
and `slingshot-ssh` sees the same bytes.

## herdr --remote

`herdr --remote <target>` runs `ssh` by name for a non-interactive bridge, with
its own generated config and control socket (`[remote] manage_ssh_config`). Even
with `slingshot-ssh` installed as `ssh` on `PATH`, that connection carries a
remote command with no terminal, so it would pass straight through. herdr's
remote mode has its own clipboard-image upload (`keys.remote_image_paste`,
default `ctrl+v`). For dragging files, run `slingshot-ssh macbook` and start
`herdr` on the Mac instead.

## Known gaps

- Directories are not uploaded; a drop that includes one passes through.
- Paths must be absolute (or `~/...` or `file://`), which is always true for
  terminal drops.
- A file name containing a newline is not supported (the paste passes through).
- If the start marker `ESC[200~` is split right after its first byte, with the
  ESC arriving in a read by itself, the paste passes through unchanged. A lone
  ESC is forwarded at once so the Esc key never lags in vim. Terminals write the
  marker in one piece, so this does not happen in practice.
- While an upload runs, your keystrokes are held and sent after the remote
  paths, so they stay in order. Ctrl-C cancels the upload.
- The ssh escape `~^Z` suspends `slingshot-ssh` itself (ssh inside the
  pseudo-terminal cannot stop itself). Other `~` escapes such as `~.` work as
  usual.
- No progress bar for large files, only the notification.

## Tests

```bash
python3 -m unittest discover -s tests/ssh -t tests/ssh
```

These cover argument parsing, paste detection, rewriting, and an end-to-end
run of the proxy through a pseudo-terminal against a fake `ssh`
(`tests/ssh/fake_ssh.py`), which runs the real upload script against a temp
dir. They never open windows or notifications: `notify-send` is replaced by a
stub on `PATH`.

A smoke test against a real host is skipped unless you ask for it:

```bash
SLINGSHOT_REAL_HOST=macbook python3 -m unittest discover -s tests/ssh -t tests/ssh
```

It needs non-interactive key login. It drops one small temp file, checks the
bytes on the remote, then deletes only that file and closes the shared
connection it opened.
