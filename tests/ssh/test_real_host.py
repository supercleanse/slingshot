"""Optional smoke test against a real host.

Skipped unless SLINGSHOT_REAL_HOST is set (e.g. SLINGSHOT_REAL_HOST=macbook).
The host must accept non-interactive key auth. The test pastes one small temp
file into an interactive slingshot-ssh session, checks it landed in the remote
drop dir with the right bytes, then deletes ONLY that file and closes the
control master it started.
"""

import os
import pty
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import fcntl
import time
import unittest

from helpers import SCRIPT, drain, write_stub

HOST = os.environ.get("SLINGSHOT_REAL_HOST")


@unittest.skipUnless(HOST, "set SLINGSHOT_REAL_HOST=<ssh destination> to run")
class TestRealHost(unittest.TestCase):
    def test_drop_lands_on_remote(self):
        tmp = tempfile.mkdtemp(prefix="slingshot-real-")
        self.addCleanup(shutil.rmtree, tmp, True)
        runtime = os.path.join(tmp, "run")
        os.makedirs(runtime, mode=0o700)
        stubs = os.path.join(tmp, "stubs")
        os.makedirs(stubs)
        write_stub(os.path.join(stubs, "notify-send"), "#!/bin/sh\nexit 0\n")
        debug_log = os.path.join(tmp, "debug.log")
        token = os.urandom(6).hex()
        name = "slingshot-smoke-%s.txt" % token
        local = os.path.join(tmp, name)
        payload = ("slingshot smoke test %s\n" % token).encode()
        with open(local, "wb") as f:
            f.write(payload)

        env = dict(os.environ, PATH=stubs + os.pathsep + os.environ.get("PATH", ""),
                   XDG_RUNTIME_DIR=runtime, SLINGSHOT_SSH_DEBUG=debug_log,
                   SLINGSHOT_NOTIFY="0", TERM="xterm-256color")
        env.pop("SLINGSHOT_SSH_BIN", None)
        cpath = os.path.join(runtime, "slingshot-ssh", "cm-%C")

        pid, fd = pty.fork()
        if pid == 0:
            try:
                fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
                os.execve(sys.executable, [sys.executable, SCRIPT, HOST], env)
            finally:
                os._exit(99)
        remote_path = None
        try:
            drain(fd, quiet=2.0, timeout=20)       # login banner + prompt
            os.write(fd, b"\x1b[200~'" + local.encode() + b"'\x1b[201~")
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and remote_path is None:
                drain(fd, quiet=0.2, timeout=0.5)
                if os.path.exists(debug_log):
                    with open(debug_log) as f:
                        log = f.read()
                    m = re.search(r"upload ok: \['([^']+)'\]", log)
                    if m:
                        remote_path = m.group(1)
                    elif "upload failed" in log:
                        self.fail(log)
            self.assertIsNotNone(remote_path, "upload never finished")
            self.assertTrue(remote_path.endswith("/Downloads/Slingshot/" + name), remote_path)
            os.write(fd, b"\x15exit\r")             # clear the line, log out
            drain(fd, quiet=1.0, timeout=10)
        finally:
            try:
                os.kill(pid, signal.SIGHUP)
            except OSError:
                pass
            os.waitpid(pid, 0)
            try:
                if remote_path:
                    got = subprocess.run(
                        ["ssh", "-o", "BatchMode=yes", "-o", "ControlPath=" + cpath, HOST,
                         "cat " + shell_quote(remote_path)],
                        stdout=subprocess.PIPE, timeout=30).stdout
                    subprocess.run(
                        ["ssh", "-o", "BatchMode=yes", "-o", "ControlPath=" + cpath, HOST,
                         "rm -f " + shell_quote(remote_path)], timeout=30, check=True)
                    self.assertEqual(got, payload)
            finally:
                subprocess.run(["ssh", "-o", "ControlPath=" + cpath, "-O", "exit", HOST],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)


def shell_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


if __name__ == "__main__":
    unittest.main()
