"""paste.py against fake hyprctl / wl-copy / notify-send.

Each fake appends one JSON line per call to a log, so the tests read back
exactly what would have reached Hyprland and the clipboard. Nothing touches
the real desktop.

    python3 -m unittest discover -s tests/paste
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
PASTE = os.path.join(ROOT, "paste.py")
CLI = os.path.join(ROOT, "bin", "slingshot")

FAKE = textwrap.dedent("""\
    #!{python}
    import json, os, sys
    name = os.path.basename(sys.argv[0])
    stdin = sys.stdin.read() if name == "wl-copy" else ""
    with open(os.environ["FAKE_LOG"], "a") as f:
        f.write(json.dumps({{"cmd": name, "args": sys.argv[1:], "stdin": stdin}}) + "\\n")
    if name == "hyprctl" and sys.argv[1:] == ["-j", "clients"]:
        print(os.environ["FAKE_CLIENTS"])
    elif name == "hyprctl" and sys.argv[1:] == ["-j", "monitors"]:
        print(os.environ["FAKE_MONITORS"])
    elif name == "hyprctl" and sys.argv[1:] == ["-j", "activewindow"]:
        print(os.environ.get("FAKE_ACTIVE", "{{}}"))
    """)

MONITORS = [{"activeWorkspace": {"id": 3}, "specialWorkspace": {"id": 0}},
            {"activeWorkspace": {"id": 5}, "specialWorkspace": {"id": 0}}]
FOOT = {"address": "0xaa", "class": "foot", "tags": ["default-opacity*", "terminal*"], "workspace": {"id": 3}}
CHROME = {"address": "0xbb", "class": "google-chrome", "tags": ["chromium-based-browser*"], "workspace": {"id": 5}}
CUSTOM_TERM = {"address": "0xcc", "class": "Alacritty", "tags": [], "workspace": {"id": 3}}
HIDDEN = {"address": "0xdd", "class": "slack", "tags": [], "workspace": {"id": 7}}


class FakeDesktop(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="slingshot-paste-")
        self.addCleanup(shutil.rmtree, self.dir)
        self.log = os.path.join(self.dir, "log.jsonl")
        for name in ("hyprctl", "wl-copy", "notify-send"):
            p = os.path.join(self.dir, name)
            with open(p, "w") as f:
                f.write(FAKE.format(python=sys.executable))
            os.chmod(p, 0o755)

    def env(self, clients=(FOOT, CHROME, CUSTOM_TERM, HIDDEN), **extra):
        return dict(os.environ,
                   FAKE_LOG=self.log,
                   FAKE_CLIENTS=json.dumps(list(clients)),
                   FAKE_MONITORS=json.dumps(MONITORS),
                   SLINGSHOT_HYPRCTL=os.path.join(self.dir, "hyprctl"),
                   SLINGSHOT_WLCOPY=os.path.join(self.dir, "wl-copy"),
                   SLINGSHOT_NOTIFY=os.path.join(self.dir, "notify-send"),
                   **extra)

    def calls(self):
        if not os.path.exists(self.log):
            return []
        with open(self.log) as f:
            return [json.loads(line) for line in f]

    def run_paste(self, path, address, clients=(FOOT, CHROME, CUSTOM_TERM, HIDDEN)):
        subprocess.run([sys.executable, PASTE, path, address, "0"], env=self.env(clients), check=True, timeout=10)
        return self.calls()

    def dispatches(self, calls):
        return [c["args"][1] for c in calls if c["cmd"] == "hyprctl" and c["args"][0] == "dispatch"]

    def copies(self, calls):
        return [(c["args"], c["stdin"]) for c in calls if c["cmd"] == "wl-copy"]


class PasteHelper(FakeDesktop):
    def test_terminal_gets_the_quoted_path_and_ctrl_shift_v(self):
        calls = self.run_paste("/home/me/Pictures/my shot.png", "0xaa")
        self.assertEqual(self.copies(calls), [([], "'/home/me/Pictures/my shot.png'")])
        d = self.dispatches(calls)
        self.assertEqual(d[0], 'hl.dsp.focus({ window = "address:0xaa" })')
        self.assertEqual(d[1], 'hl.dsp.send_key_state({ mods = "CTRL + SHIFT", key = "V", state = "down", window = "address:0xaa" })')
        self.assertEqual(d[2], 'hl.dsp.send_key_state({ mods = "CTRL + SHIFT", key = "V", state = "up", window = "address:0xaa" })')

    def test_plain_path_is_not_quoted(self):
        calls = self.run_paste("/home/me/Downloads/report.pdf", "0xaa")
        self.assertEqual(self.copies(calls), [([], "/home/me/Downloads/report.pdf")])

    def test_terminal_class_without_the_tag_still_counts(self):
        calls = self.run_paste("/tmp/a.png", "0xcc")
        self.assertEqual(self.copies(calls), [([], "/tmp/a.png")])
        self.assertIn('mods = "CTRL + SHIFT"', self.dispatches(calls)[1])

    def test_app_gets_the_file_and_ctrl_v(self):
        calls = self.run_paste("/home/me/Pictures/it's 100%.png", "0xbb")
        self.assertEqual(self.copies(calls),
                         [(["--type", "text/uri-list"], "file:///home/me/Pictures/it's%20100%25.png\r\n")])
        d = self.dispatches(calls)
        self.assertEqual(d[0], 'hl.dsp.focus({ window = "address:0xbb" })')
        self.assertIn('mods = "CTRL", key = "V", state = "down", window = "address:0xbb"', d[1])
        self.assertIn('state = "up"', d[2])

    def test_window_on_a_hidden_workspace_only_copies(self):
        calls = self.run_paste("/tmp/a.png", "0xdd")
        self.assertEqual(self.copies(calls), [(["--type", "text/uri-list"], "file:///tmp/a.png\r\n")])
        self.assertEqual(self.dispatches(calls), [])
        self.assertTrue(any(c["cmd"] == "notify-send" for c in calls))

    def test_closed_window_only_copies(self):
        calls = self.run_paste("/tmp/a.png", "0xee")
        self.assertEqual(self.dispatches(calls), [])
        self.assertEqual(len(self.copies(calls)), 1)

    def test_malformed_address_never_reaches_hyprland(self):
        calls = self.run_paste("/tmp/a.png", 'x" }) evil')
        self.assertEqual(self.dispatches(calls), [])
        self.assertFalse(any(c["cmd"] == "hyprctl" for c in calls))


class SlingshotCli(FakeDesktop):
    def setUp(self):
        super().setUp()
        self.downloads = os.path.join(self.dir, "Downloads")
        os.mkdir(self.downloads)
        # name -> age in seconds; newest first is c, b, a.
        for name, age in [("a.pdf", 30), ("b.png", 20), ("c d.txt", 10), (".hidden", 1),
                          ("big.iso", 5), ("big.iso.crdownload", 5), ("half.zip.part", 2)]:
            p = os.path.join(self.downloads, name)
            with open(p, "w") as f:
                f.write("x")
            t = 1_800_000_000 - age
            os.utime(p, (t, t))
        os.mkdir(os.path.join(self.downloads, "newest-dir"))

    def cli(self, *args, active=FOOT):
        env = self.env(SLINGSHOT_DOWNLOADS=self.downloads, FAKE_ACTIVE=json.dumps(active))
        return subprocess.run([sys.executable, CLI, *args], env=env, capture_output=True, text=True, timeout=10)

    def test_list_matches_the_dropdown_filtering(self):
        out = self.cli("list", "downloads").stdout.split("\n")
        self.assertEqual([os.path.basename(p) for p in out if p], ["c d.txt", "b.png", "a.pdf"])

    def test_paste_newest_into_the_focused_terminal(self):
        self.assertEqual(self.cli("paste", "downloads").returncode, 0)
        calls = self.calls()
        self.assertEqual(self.copies(calls), [([], shlex_quote(os.path.join(self.downloads, "c d.txt")))])
        self.assertIn('window = "address:0xaa"', self.dispatches(calls)[0])

    def test_paste_nth_into_the_focused_app(self):
        self.assertEqual(self.cli("paste", "downloads", "3", active=CHROME).returncode, 0)
        uri = "file://" + os.path.join(self.downloads, "a.pdf")
        self.assertEqual(self.copies(self.calls()), [(["--type", "text/uri-list"], uri + "\r\n")])

    def test_past_the_end_notifies_and_pastes_nothing(self):
        self.assertEqual(self.cli("paste", "downloads", "4").returncode, 1)
        calls = self.calls()
        self.assertEqual(self.copies(calls), [])
        self.assertTrue(any(c["cmd"] == "notify-send" for c in calls))

    def test_no_focused_window_copies_instead(self):
        self.assertEqual(self.cli("paste", "downloads", active={}).returncode, 0)
        calls = self.calls()
        self.assertEqual(self.dispatches(calls), [])
        self.assertEqual(len(self.copies(calls)), 1)

    def test_bad_arguments(self):
        for args in [(), ("paste",), ("paste", "music"), ("paste", "downloads", "0"), ("paste", "downloads", "x")]:
            self.assertEqual(self.cli(*args).returncode, 2, args)

    def test_partial_suffixes_match_model_js(self):
        with open(os.path.join(ROOT, "Model.js")) as f:
            js = re.search(r"PARTIAL_SUFFIXES = (\[.*?\])", f.read()).group(1)
        with open(CLI) as f:
            py = re.search(r"PARTIAL_SUFFIXES = (\[.*?\])", f.read()).group(1)
        self.assertEqual(json.loads(js), json.loads(py))


def shlex_quote(s):
    import shlex
    return shlex.quote(s)


if __name__ == "__main__":
    unittest.main()
