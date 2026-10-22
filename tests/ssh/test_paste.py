import os
import shutil
import tempfile
import unittest
import urllib.parse

from helpers import load

m = load()
S, E = m.PASTE_START, m.PASTE_END


class FileFixture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="slingshot-test-")
        self.addCleanup(shutil.rmtree, self.dir)
        self.a = self.make("a.png")
        self.b = self.make("b.txt")
        self.spaced = self.make("my shot.png")
        self.my = self.make("my")           # decoy prefix of "my shot.png"
        self.quote = self.make("it's.png")
        self.subdir = os.path.join(self.dir, "folder")
        os.mkdir(self.subdir)

    def make(self, name, data=b"x"):
        p = os.path.join(self.dir, name)
        with open(p, "wb") as f:
            f.write(data)
        return p

    def match(self, text, bracketed=True):
        return m.match_paths(text.encode(), bracketed)


class TestMatchPaths(FileFixture):
    def test_single_plain_path(self):
        mt = self.match(self.a)
        self.assertEqual(mt.paths, [self.a])

    def test_foot_normal_screen_single_quoted(self):
        mt = self.match("'%s' '%s'" % (self.spaced, self.b))
        self.assertEqual(mt.paths, [self.spaced, self.b])

    def test_foot_escaped_quote_inside_single_quotes(self):
        # foot 1.28 emits '...it\'s.png' (not POSIX) for a quote in a name
        mt = self.match("'%s'" % self.quote.replace("'", "\\'"))
        self.assertEqual(mt.paths, [self.quote])

    def test_posix_quote_escape(self):
        mt = self.match("'%s'" % self.quote.replace("'", "'\\''"))
        self.assertEqual(mt.paths, [self.quote])

    def test_backslash_escaped_spaces(self):
        mt = self.match(self.spaced.replace(" ", "\\ "))
        self.assertEqual(mt.paths, [self.spaced])

    def test_double_quoted(self):
        mt = self.match('"%s"' % self.spaced)
        self.assertEqual(mt.paths, [self.spaced])

    def test_foot_alt_screen_unquoted_with_spaces(self):
        # On the alternate screen foot pastes raw paths separated by spaces.
        mt = self.match("%s %s %s" % (self.spaced, self.a, self.b))
        self.assertEqual(mt.paths, [self.spaced, self.a, self.b])

    def test_unquoted_prefers_longest_name(self):
        mt = self.match(self.spaced)
        self.assertEqual(mt.paths, [self.spaced])

    def test_unquoted_quote_escape(self):
        mt = self.match(self.quote.replace("'", "\\'") + " " + self.a)
        self.assertEqual(mt.paths, [self.quote, self.a])

    def test_file_uri_percent_decoded(self):
        uri = "file://" + urllib.parse.quote(self.spaced)
        mt = self.match(uri)
        self.assertEqual(mt.paths, [self.spaced])
        mt = self.match("file://localhost" + urllib.parse.quote(self.a))
        self.assertEqual(mt.paths, [self.a])

    def test_foreign_host_uri_rejected(self):
        self.assertIsNone(self.match("file://otherbox" + self.a))

    def test_multiple_files_newline_separated(self):
        mt = self.match("%s\n%s\r\n" % (self.a, self.b))
        self.assertEqual(mt.paths, [self.a, self.b])

    def test_tilde_path(self):
        home = os.path.expanduser("~")
        if not self.dir.startswith(home + os.sep):
            self.skipTest("temp dir not under $HOME")
        mt = self.match("~" + self.a[len(home):])
        self.assertEqual(mt.paths, [self.a])

    def test_non_file_text(self):
        for text in ("hello world", "ls -la /tmp", "/usr/bin", "cd " + self.a,
                     self.a + " and more", "http://example.com/x.png", "", "   ",
                     "$HOME/x", "`id`"):
            self.assertIsNone(self.match(text), text)

    def test_partial_matches_rejected(self):
        self.assertIsNone(self.match("%s %s" % (self.a, os.path.join(self.dir, "nope"))))
        self.assertIsNone(self.match(self.a + "x"))
        self.assertIsNone(self.match(self.a[:-1]))

    def test_nonexistent_path(self):
        self.assertIsNone(self.match(os.path.join(self.dir, "missing.png")))

    def test_directory_passes_through(self):
        self.assertIsNone(self.match(self.subdir))
        self.assertIsNone(self.match("'%s' '%s'" % (self.subdir, self.a)))

    def test_relative_path_rejected(self):
        cwd = os.getcwd()
        os.chdir(self.dir)
        try:
            self.assertIsNone(self.match("a.png"))
        finally:
            os.chdir(cwd)

    def test_control_chars_rejected(self):
        self.assertIsNone(self.match(self.a + "\x1b[A"))

    def test_unclosed_quote_rejected(self):
        self.assertIsNone(self.match("'" + self.a))


class TestRender(FileFixture):
    def test_rewrite_keeps_bracket_and_style(self):
        mt = self.match("'%s' '%s'" % (self.spaced, self.a))
        out = mt.render(["/Users/u/Downloads/Slingshot/my shot.png",
                         "/Users/u/Downloads/Slingshot/a.png"])
        self.assertEqual(out, S + b"'/Users/u/Downloads/Slingshot/my shot.png' "
                                  b"'/Users/u/Downloads/Slingshot/a.png'" + E)

    def test_plain_style_quotes_only_when_needed(self):
        mt = self.match("%s %s" % (self.a, self.spaced), bracketed=False)
        out = mt.render(["/r/a.png", "/r/my shot.png"])
        self.assertEqual(out, b"/r/a.png '/r/my shot.png'")

    def test_escaped_style(self):
        mt = self.match(self.spaced.replace(" ", "\\ "))
        self.assertEqual(mt.render(["/r/my shot.png"]), S + b"/r/my\\ shot.png" + E)

    def test_quote_in_remote_name(self):
        mt = self.match("'%s'" % self.quote.replace("'", "\\'"))
        self.assertEqual(mt.render(["/r/it's.png"]), S + b"'/r/it'\\''s.png'" + E)

    def test_uri_style(self):
        mt = self.match("file://" + urllib.parse.quote(self.spaced))
        self.assertEqual(mt.render(["/r/my shot.png"]), S + b"file:///r/my%20shot.png" + E)

    def test_separators_preserved(self):
        mt = self.match("%s\n%s" % (self.a, self.b), bracketed=False)
        self.assertEqual(mt.render(["/r/a", "/r/b"]), b"/r/a\n/r/b")


class TestDetector(FileFixture):
    def feed_all(self, det, chunks, now=0.0):
        out = []
        for c in chunks:
            out += det.feed(c, now)
        return out

    def sent(self, actions):
        return b"".join(v for k, v in actions if k == "send")

    def test_typing_passes_through(self):
        det = m.PasteDetector()
        chunks = [b"l", b"s", b" ", b"-", b"l", b"\r", b"\x1b[A", b"\x03", b"\x1b", b":wq\r"]
        acts = self.feed_all(det, chunks)
        self.assertTrue(all(k == "send" for k, _ in acts))
        self.assertEqual(self.sent(acts), b"".join(chunks))
        self.assertFalse(det.pending())

    def test_bracketed_file_paste(self):
        det = m.PasteDetector()
        acts = det.feed(S + ("'%s'" % self.spaced).encode() + E, 0)
        self.assertEqual([k for k, _ in acts], ["paste"])
        self.assertEqual(acts[0][1].paths, [self.spaced])
        self.assertTrue(acts[0][1].bracketed)

    def test_bracketed_split_everywhere(self):
        data = b"ab" + S + self.a.encode() + E + b"cd"
        for cut in range(1, len(data)):
            det = m.PasteDetector()
            acts = self.feed_all(det, [data[:cut], data[cut:]])
            kinds = [k for k, _ in acts]
            self.assertIn("paste", kinds, cut)
            self.assertEqual(self.sent(acts), b"abcd", cut)

    def test_bracketed_payload_and_end_marker_byte_by_byte(self):
        data = self.a.encode() + E
        det = m.PasteDetector()
        acts = self.feed_all(det, [S[:3], S[3:]] + [bytes([b]) for b in data])
        self.assertEqual([k for k, _ in acts], ["paste"])

    def test_lone_esc_read_before_marker_is_a_known_miss(self):
        # A 1-byte ESC read is forwarded at once (it is the Esc key); if a
        # paste marker were ever split right after it, the paste passes
        # through unchanged rather than being rewritten. Never corrupted.
        det = m.PasteDetector()
        data = S + self.a.encode() + E
        acts = self.feed_all(det, [data[:1], data[1:]])
        self.assertEqual(self.sent(acts), data)

    def test_bracketed_non_file_passes_byte_for_byte(self):
        det = m.PasteDetector()
        data = b"x" + S + b"hello\nworld /tmp" + E + b"y"
        acts = self.feed_all(det, [data[:9], data[9:]])
        self.assertEqual([k for k, _ in acts if k == "paste"], [])
        self.assertEqual(self.sent(acts), data)

    def test_unbracketed_whole_chunk(self):
        det = m.PasteDetector()
        acts = det.feed(("'%s' '%s'" % (self.a, self.b)).encode(), 0)
        self.assertEqual([k for k, _ in acts], ["paste"])
        self.assertFalse(acts[0][1].bracketed)
        self.assertEqual(acts[0][1].render(["/r/a", "/r/b"]), b"'/r/a' '/r/b'")

    def test_unbracketed_typed_one_char_at_a_time_is_ignored(self):
        det = m.PasteDetector()
        acts = self.feed_all(det, [bytes([b]) for b in self.a.encode()])
        self.assertTrue(all(k == "send" for k, _ in acts))
        self.assertEqual(self.sent(acts), self.a.encode())

    def test_partial_marker_is_held_then_released(self):
        det = m.PasteDetector()
        acts = det.feed(b"abc\x1b[2", 10.0)
        self.assertEqual(self.sent(acts), b"abc")
        self.assertTrue(det.pending())
        self.assertEqual(det.poll(10.01), [])
        acts = det.poll(10.0 + m.MARKER_HOLD_SECONDS + 0.001)
        self.assertEqual(self.sent(acts), b"\x1b[2")
        self.assertFalse(det.pending())

    def test_lone_escape_is_never_held(self):
        det = m.PasteDetector()
        self.assertEqual(self.sent(det.feed(b"\x1b", 0)), b"\x1b")
        self.assertFalse(det.pending())

    def test_unterminated_paste_times_out(self):
        det = m.PasteDetector()
        acts = det.feed(S + b"/some/thing", 5.0)
        self.assertEqual(acts, [])
        acts = det.poll(5.0 + m.PASTE_GATHER_SECONDS + 0.01)
        self.assertEqual(self.sent(acts), S + b"/some/thing")
        acts = det.feed(E + b"z", 9.0)
        self.assertEqual(self.sent(acts), E + b"z")

    def test_huge_paste_streams_through(self):
        det = m.PasteDetector()
        big = b"y" * (m.PASTE_GATHER_MAX + 10)
        acts = det.feed(S + big, 0)
        acts += det.feed(E, 0)
        self.assertEqual(self.sent(acts), S + big + E)

    def test_text_after_paste_kept_in_order(self):
        det = m.PasteDetector()
        acts = det.feed(S + self.a.encode() + E + b"\r" + S + b"plain" + E, 0)
        self.assertEqual([k for k, _ in acts], ["paste", "send"])
        self.assertEqual(acts[1][1], b"\r" + S + b"plain" + E)


if __name__ == "__main__":
    unittest.main()
