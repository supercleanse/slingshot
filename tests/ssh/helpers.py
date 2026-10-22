"""Shared helpers for the slingshot-ssh tests."""

import importlib.machinery
import importlib.util
import os
import select
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPT = os.path.join(ROOT, "bin", "slingshot-ssh")
FAKE_SSH = os.path.join(HERE, "fake_ssh.py")

_module = None


def load():
    """Import bin/slingshot-ssh (it has no .py suffix) as a module."""
    global _module
    if _module is None:
        loader = importlib.machinery.SourceFileLoader("slingshot_ssh", SCRIPT)
        spec = importlib.util.spec_from_loader("slingshot_ssh", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        _module = mod
    return _module


def read_until(fd, predicate, timeout=10.0, buf=b""):
    """Read from fd until predicate(buf) is true. Returns buf (raises on timeout)."""
    deadline = time.monotonic() + timeout
    while not predicate(buf):
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("timed out; got %r" % buf[-500:])
        r, _, _ = select.select([fd], [], [], left)
        if fd in r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                if predicate(buf):
                    break
                raise EOFError("EOF; got %r" % buf[-500:])
            buf += chunk
    return buf


def drain(fd, quiet=0.3, timeout=5.0):
    """Read until fd has been quiet for `quiet` seconds."""
    buf = b""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r, _, _ = select.select([fd], [], [], quiet)
        if fd not in r:
            break
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
    return buf


def write_stub(path, body):
    with open(path, "w") as f:
        f.write(body)
    os.chmod(path, 0o755)
