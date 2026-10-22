"""End-to-end: drive slingshot-ssh through a pty against a fake ssh."""

import fcntl
import json
import os
import pty
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

from helpers import FAKE_SSH, SCRIPT, drain, read_until, write_stub

S, E = b"\x1b[200~", b"\x1b[201~"


class E2EBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="slingshot-e2e-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.remote_home = os.path.realpath(os.path.join(self.tmp, "remote-home"))
        os.makedirs(self.remote_home)
        self.runtime = os.path.join(self.tmp, "run")
        os.makedirs(self.runtime, mode=0o700)
        self.log = os.path.join(self.tmp, "fake-ssh.log")
        self.notify_log = os.path.join(self.tmp, "notify.log")
        stubs = os.path.join(self.tmp, "stubs")
        os.makedirs(stubs)
        # Never touch the live desktop: a notify-send that only logs.
        write_stub(os.path.join(stubs, "notify-send"),
                   "#!/bin/sh\nprintf '%%s\\n' \"$*\" >> '%s'\n" % self.notify_log)
        self.local = os.path.join(self.tmp, "local files")
        os.makedirs(self.local)
        self.env = {
            "PATH": stubs + os.pathsep + "/usr/local/bin:/usr/bin:/bin",
            "HOME": self.tmp,
            "TERM": "xterm-256color",
            "LANG": "C.UTF-8",
            "XDG_RUNTIME_DIR": self.runtime,
            "SLINGSHOT_SSH_BIN": FAKE_SSH,
            "SLINGSHOT_CONFIG": os.path.join(self.tmp, "no-config.toml"),
            "SLINGSHOT_SSH_DEBUG": os.path.join(self.tmp, "debug.log"),
            "FAKE_SSH_LOG": self.log,
            "FAKE_REMOTE_HOME": self.remote_home,
        }

    def make_file(self, name, data):
        p = os.path.join(self.local, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def spawn(self, *args, rows=30, cols=100, **extra_env):
        env = dict(self.env, **extra_env)
        pid, fd = pty.fork()
        if pid == 0:
            try:
                fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
                os.execve(sys.executable, [sys.executable, SCRIPT] + list(args), env)
            finally:
                os._exit(99)
        self.addCleanup(self._kill, pid)
        self.pid, self.fd = pid, fd
        self.out = read_until(fd, lambda b: b"READY" in b)
        return pid, fd

    def _kill(self, pid):
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except OSError:
            pass

    def entries(self, kind=None):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        return [r for r in rows if kind is None or r["kind"] == kind]

    def received(self):
        return b"".join(bytes.fromhex(r["hex"]) for r in self.entries("input"))

    def wait_received(self, predicate, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            got = self.received()
            if predicate(got):
                return got
            drain(self.fd, quiet=0.05, timeout=0.2)
        self.fail("fake ssh never received expected bytes; got %r" % self.received())

    def finish(self, expect_code=7):
        os.write(self.fd, b"\x04")
        drain(self.fd, quiet=0.3, timeout=5)
        _, status = os.waitpid(self.pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), expect_code)


class TestE2E(E2EBase):
    def test_drop_uploads_and_rewrites(self):
        data = os.urandom(50000) + b"\x00end"
        local = self.make_file("shot one.png", data)
        self.spawn("fakehost")
        paste = S + ("'%s'" % local).encode() + E
        # Split the paste across two writes, including inside the end marker.
        os.write(self.fd, paste[:4])
        time.sleep(0.02)
        os.write(self.fd, paste[4:-3])
        time.sleep(0.02)
        os.write(self.fd, paste[-3:])
        remote = os.path.join(self.remote_home, "Downloads", "Slingshot", "shot one.png")
        expect = S + ("'%s'" % remote).encode() + E
        self.wait_received(lambda got: expect in got)
        with open(remote, "rb") as f:
            self.assertEqual(f.read(), data)
        self.assertNotIn(local.encode(), self.received())

        # Second drop of the same name gets a numbered suffix, never overwrites.
        os.write(self.fd, paste)
        remote2 = os.path.join(self.remote_home, "Downloads", "Slingshot", "shot one-2.png")
        self.wait_received(lambda got: ("'%s'" % remote2).encode() in got)
        with open(remote2, "rb") as f:
            self.assertEqual(f.read(), data)

        # Typing and normal pastes are untouched, in order.
        os.write(self.fd, b"abc")
        os.write(self.fd, S + b"just text /tmp" + E)
        os.write(self.fd, b"\x03")
        self.wait_received(lambda got: got.endswith(b"abc" + S + b"just text /tmp" + E + b"\x03"))
        self.finish(7)

        # The session got multiplexing; uploads reused it, non-interactively.
        argvs = [r["argv"] for r in self.entries("argv")]
        session = [a for a in argvs if "-G" not in a and not a[-1].startswith("sh -c")]
        uploads = [a for a in argvs if a[-1].startswith("sh -c")]
        self.assertEqual(len(session), 1)
        self.assertIn("ControlMaster=auto", session[0])
        cpath = "ControlPath=" + os.path.join(self.runtime, "slingshot-ssh", "cm-%C")
        self.assertIn(cpath, session[0])
        self.assertEqual(session[0][-1], "fakehost")
        self.assertEqual(len(uploads), 2)
        for a in uploads:
            self.assertIn(cpath, a)
            self.assertIn("ControlMaster=no", a)
            self.assertIn("BatchMode=yes", a)
        self.assertFalse(os.path.exists(self.notify_log))

    def test_multiple_files_unquoted_alt_screen_style(self):
        a = self.make_file("a b.txt", b"AAA")
        b = self.make_file("c.txt", b"CCC")
        self.spawn("fakehost")
        os.write(self.fd, S + ("%s %s" % (a, b)).encode() + E)
        base = os.path.join(self.remote_home, "Downloads", "Slingshot")
        expect = S + ("'%s/a b.txt' %s/c.txt" % (base, base)).encode() + E
        self.wait_received(lambda got: expect in got)
        self.finish(7)

    def test_upload_failure_passes_original_and_notifies(self):
        local = self.make_file("x.png", b"data")
        self.spawn("fakehost", FAKE_UPLOAD_FAIL="1")
        paste = S + ("'%s'" % local).encode() + E
        os.write(self.fd, paste + b"z")
        self.wait_received(lambda got: got.endswith(paste + b"z"))
        self.finish(7)
        with open(self.notify_log) as f:
            self.assertIn("upload failed", f.read())

    def test_slow_upload_notifies_and_ctrl_c_cancels(self):
        local = self.make_file("slow.png", b"data")
        self.spawn("fakehost", FAKE_UPLOAD_SLEEP="5")
        paste = S + local.encode() + E
        os.write(self.fd, paste)
        time.sleep(0.2)
        os.write(self.fd, b"q")          # held until the upload settles
        time.sleep(0.4)
        self.assertEqual(self.received(), b"")
        os.write(self.fd, b"\x03")       # cancel
        self.wait_received(lambda got: got == paste + b"q\x03")
        self.finish(7)
        with open(self.notify_log) as f:
            self.assertIn("uploading", f.read())

    def test_size_cap_passes_original(self):
        local = self.make_file("big.bin", b"0" * 3000)
        self.spawn("fakehost", SLINGSHOT_MAX_SIZE_MB="0.001")
        paste = S + local.encode() + E
        os.write(self.fd, paste)
        self.wait_received(lambda got: paste in got)
        self.finish(7)
        self.assertFalse([a for a in self.entries("argv") if a["argv"][-1].startswith("sh -c")])
        with open(self.notify_log) as f:
            self.assertIn("too large", f.read())

    def test_custom_remote_dir(self):
        local = self.make_file("n.txt", b"n")
        self.spawn("fakehost", SLINGSHOT_REMOTE_DIR="~/drops/here")
        os.write(self.fd, S + local.encode() + E)
        remote = os.path.join(self.remote_home, "drops", "here", "n.txt")
        self.wait_received(lambda got: (S + remote.encode() + E) in got)
        self.finish(7)

    def test_window_size_forwarded(self):
        self.spawn("fakehost", rows=30, cols=100)
        os.write(self.fd, b"?")
        read_until(self.fd, lambda b: b"WINSZ 30x100" in b)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 160, 0, 0))
        time.sleep(0.2)
        os.write(self.fd, b"?")
        read_until(self.fd, lambda b: b"WINSZ 50x160" in b)
        self.finish(7)

    def test_escape_ctrl_z_suspends_and_resumes(self):
        self.spawn("fakehost")
        os.write(self.fd, b"\r~\x1a")
        _, st = os.waitpid(self.pid, os.WUNTRACED)
        self.assertTrue(os.WIFSTOPPED(st))
        os.kill(self.pid, signal.SIGCONT)
        os.write(self.fd, b"?")
        read_until(self.fd, lambda b: b"WINSZ" in b)
        self.assertIn(b"\r~\x1a", self.received())
        self.finish(7)

    def test_exit_code_propagates(self):
        self.spawn("fakehost", FAKE_EXIT="42")
        self.finish(42)

    def test_raw_during_session_and_restored_after_exit(self):
        master, slave = os.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        before = termios.tcgetattr(slave)
        self.assertTrue(before[3] & termios.ICANON)
        pid = os.fork()
        if pid == 0:
            try:
                os.setsid()
                fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
                for fd in (0, 1, 2):
                    os.dup2(slave, fd)
                os.execve(sys.executable, [sys.executable, SCRIPT, "fakehost"], self.env)
            finally:
                os._exit(99)
        self.addCleanup(self._kill, pid)
        read_until(master, lambda b: b"READY" in b)
        during = termios.tcgetattr(slave)
        self.assertFalse(during[3] & termios.ICANON)
        self.assertFalse(during[3] & termios.ECHO)
        os.write(master, b"\x04")
        drain(master)
        _, st = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(st), 7)
        self.assertEqual(termios.tcgetattr(slave), before)


class TestPassthrough(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="slingshot-pass-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.log = os.path.join(self.tmp, "fake.log")
        self.env = dict(os.environ, SLINGSHOT_SSH_BIN=FAKE_SSH, FAKE_SSH_LOG=self.log,
                        FAKE_REMOTE_HOME=self.tmp, XDG_RUNTIME_DIR=self.tmp,
                        SLINGSHOT_NOTIFY="0")

    def argvs(self):
        with open(self.log) as f:
            rows = [json.loads(line) for line in f]
        return [r["argv"] for r in rows if r["kind"] == "argv"]

    def test_non_tty_execs_unchanged(self):
        r = subprocess.run([sys.executable, SCRIPT, "fakehost", "-O", "check"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, env=self.env)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.argvs(), [["fakehost", "-O", "check"]])

    def test_disable_env(self):
        pid, fd = pty.fork()
        if pid == 0:
            env = dict(self.env, SLINGSHOT_SSH_DISABLE="1")
            os.execve(sys.executable, [sys.executable, SCRIPT, "fakehost"], env)
        try:
            read_until(fd, lambda b: b"READY" in b)
            os.write(fd, b"\x04")
            drain(fd)
        finally:
            _, st = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(st), 7)
        self.assertEqual(self.argvs(), [["fakehost"]])

    def test_tty_with_command_execs_unchanged(self):
        pid, fd = pty.fork()
        if pid == 0:
            os.execve(sys.executable, [sys.executable, SCRIPT, "fakehost", "-O", "exit"], self.env)
        drain(fd)
        _, st = os.waitpid(pid, 0)
        self.assertEqual(os.waitstatus_to_exitcode(st), 0)
        self.assertEqual(self.argvs(), [["fakehost", "-O", "exit"]])

    def test_version_and_help(self):
        r = subprocess.run([sys.executable, SCRIPT, "--slingshot-version"],
                           stdout=subprocess.PIPE, env=self.env)
        self.assertIn(b"slingshot-ssh", r.stdout)
        r = subprocess.run([sys.executable, SCRIPT, "--slingshot-help"],
                           stdout=subprocess.PIPE, env=self.env)
        self.assertIn(b"SLINGSHOT_REMOTE_DIR", r.stdout)
        self.assertFalse(os.path.exists(self.log))


if __name__ == "__main__":
    unittest.main()
