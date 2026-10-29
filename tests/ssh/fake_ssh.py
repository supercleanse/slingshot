#!/usr/bin/env python3
"""A stand-in for ssh used by the end-to-end tests.

- `ssh -G ...`             prints a minimal effective config.
- `ssh ... dest 'sh -c ...'` (the upload command) runs that command with
  /bin/sh locally, with HOME=$FAKE_REMOTE_HOME, so the real remote script is
  exercised against a temp dir. FAKE_UPLOAD_FAIL=1 makes it fail instead;
  FAKE_UPLOAD_SLEEP=N makes it slow. It runs under FAKE_REMOTE_UMASK
  (default 022).
- `ssh [opts] dest`        acts as an interactive remote shell on its pty:
  raw mode, logs every input chunk, answers "?" with the window size and
  exits with $FAKE_EXIT (default 7) on Ctrl-D.

Every invocation appends a JSON line to $FAKE_SSH_LOG.
"""

import fcntl
import json
import os
import struct
import subprocess
import sys
import termios
import tty

LOG = os.environ["FAKE_SSH_LOG"]


def record(kind, **kw):
    kw["kind"] = kind
    kw["pid"] = os.getpid()
    with open(LOG, "a") as f:
        f.write(json.dumps(kw) + "\n")
        f.flush()


def main():
    argv = sys.argv[1:]
    record("argv", argv=argv, isatty=os.isatty(0))
    if "-G" in argv:
        sys.stdout.write("user tester\nhostname fakehost\nport 22\nescapechar ~\n"
                         "controlmaster false\nrequesttty auto\nsessiontype default\n")
        return 0
    if argv and argv[-1].startswith("sh -c '"):
        if os.environ.get("FAKE_UPLOAD_FAIL"):
            sys.stderr.write("fake: Permission denied (publickey).\n")
            return 255
        if os.environ.get("FAKE_UPLOAD_SLEEP"):
            import time
            time.sleep(float(os.environ["FAKE_UPLOAD_SLEEP"]))
        home = os.environ["FAKE_REMOTE_HOME"]
        env = dict(os.environ, HOME=home)
        # A typical permissive remote umask, so the tests see what a private
        # file would become if the script didn't protect it.
        umask = int(os.environ.get("FAKE_REMOTE_UMASK", "022"), 8)
        return subprocess.call(["/bin/sh", "-c", argv[-1]], env=env, cwd=home,
                               preexec_fn=lambda: os.umask(umask))
    if "-O" in argv:
        return 0

    # Interactive "remote shell".
    tty.setraw(0)
    os.write(1, b"READY\r\n")
    while True:
        try:
            data = os.read(0, 4096)
        except OSError:
            break
        if not data:
            break
        record("input", hex=data.hex())
        if b"\x04" in data:
            os.write(1, b"BYE\r\n")
            return int(os.environ.get("FAKE_EXIT", "7"))
        if data == b"?":
            rows, cols, _, _ = struct.unpack(
                "HHHH", fcntl.ioctl(0, termios.TIOCGWINSZ, b"\0" * 8))
            os.write(1, ("WINSZ %dx%d\r\n" % (rows, cols)).encode())
            continue
        os.write(1, b"GOT %d\r\n" % len(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
