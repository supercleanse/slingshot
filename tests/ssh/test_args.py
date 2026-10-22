import unittest

from helpers import load

m = load()


def parse(*argv):
    return m.parse_ssh_args(list(argv))


class TestSshArgs(unittest.TestCase):
    def test_plain_destination_is_interactive(self):
        a = parse("macbook")
        self.assertTrue(a.interactive)
        self.assertEqual(a.dest, "macbook")
        self.assertEqual(a.command, [])

    def test_user_at_host_with_options(self):
        a = parse("-p", "2222", "-i", "/k/id", "-A", "alice@host")
        self.assertTrue(a.interactive)
        self.assertEqual(a.dest, "alice@host")
        self.assertEqual(a.opts, [("p", "2222"), ("i", "/k/id"), ("A", None)])

    def test_attached_option_values_and_flag_clusters(self):
        a = parse("-p2222", "-AXo", "ServerAliveInterval=30", "h")
        self.assertEqual(a.opts, [("p", "2222"), ("A", None), ("X", None),
                                  ("o", "ServerAliveInterval=30")])
        self.assertEqual(a.dest, "h")
        self.assertTrue(a.interactive)

    def test_remote_command_is_passthrough(self):
        a = parse("macbook", "ls", "-la")
        self.assertFalse(a.interactive)
        self.assertEqual(a.command, ["ls", "-la"])
        self.assertEqual(a.reason, "remote command")

    def test_options_after_destination(self):
        a = parse("macbook", "-p", "22", "-L", "8080:localhost:80")
        self.assertTrue(a.interactive)
        self.assertEqual(a.dest, "macbook")
        self.assertEqual(a.command, [])
        self.assertIn(("L", "8080:localhost:80"), a.opts)

    def test_options_after_destination_then_command(self):
        a = parse("macbook", "-p", "22", "uptime", "-p")
        self.assertFalse(a.interactive)
        self.assertEqual(a.command, ["uptime", "-p"])

    def test_double_dash_ends_options(self):
        a = parse("--", "macbook", "-p")
        self.assertEqual(a.dest, "macbook")
        self.assertEqual(a.command, ["-p"])
        self.assertFalse(a.interactive)

    def test_forced_tty_with_command_is_proxied(self):
        a = parse("-t", "macbook", "herdr")
        self.assertTrue(a.interactive)
        a = parse("-o", "RequestTTY=force", "macbook", "herdr")
        self.assertTrue(a.interactive)

    def test_noninteractive_flags(self):
        for argv in (["-N", "-L", "1:h:2", "h"], ["-W", "h:22", "jump"], ["-O", "exit", "h"],
                     ["-f", "h"], ["-T", "h"], ["-n", "h"], ["-G", "h"], ["-V"],
                     ["-Q", "cipher"], ["-s", "h", "sftp"], ["-NT", "h"]):
            self.assertFalse(parse(*argv).interactive, argv)

    def test_o_options_that_disable_interactivity(self):
        self.assertFalse(parse("-o", "RequestTTY=no", "h").interactive)
        self.assertFalse(parse("-o", "SessionType=none", "h").interactive)
        self.assertFalse(parse("-o", "ForkAfterAuthentication yes", "h").interactive)
        self.assertFalse(parse("-oRemoteCommand=uptime", "h").interactive)
        self.assertTrue(parse("-oRemoteCommand=none", "h").interactive)

    def test_no_destination(self):
        self.assertFalse(parse().interactive)
        self.assertFalse(parse("-v").interactive)

    def test_missing_argument_raises(self):
        with self.assertRaises(m.ArgError):
            parse("macbook", "-p")

    def test_unknown_option_raises(self):
        with self.assertRaises(m.ArgError):
            parse("-Z", "macbook")

    def test_user_control_detection(self):
        self.assertTrue(parse("-S", "/tmp/s", "h").user_control)
        self.assertTrue(parse("-o", "ControlPath=/tmp/x", "h").user_control)
        self.assertTrue(parse("-o", "controlmaster no", "h").user_control)
        self.assertFalse(parse("h").user_control)

    def test_escape_char(self):
        self.assertEqual(parse("h").escape_char, "default")
        self.assertIsNone(parse("-e", "none", "h").escape_char)
        self.assertEqual(parse("-e", "^]", "h").escape_char, "\x1d")
        self.assertEqual(parse("-o", "EscapeChar=%", "h").escape_char, "%")

    def test_o_option_parsing(self):
        self.assertEqual(m.parse_o_option("ControlPath=/a b"), ("controlpath", "/a b"))
        self.assertEqual(m.parse_o_option("ControlPath /a"), ("controlpath", "/a"))
        self.assertEqual(m.parse_o_option(" User = bob"), ("user", "bob"))

    def test_upload_argv_filters_session_options(self):
        a = parse("-t", "-p", "2222", "-L", "1:h:2", "-o", "RequestTTY=force",
                  "-o", "User=bob", "-v", "macbook")
        up = m.Uploader("/usr/bin/ssh", a, "/run/x/cm-%C", "~/Downloads/Slingshot")
        argv = up.argv()
        self.assertEqual(argv[0], "/usr/bin/ssh")
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("ControlMaster=no", argv)
        self.assertIn("ControlPath=/run/x/cm-%C", argv)
        self.assertIn("2222", argv)
        self.assertIn("User=bob", argv)
        self.assertNotIn("-t", argv)
        self.assertNotIn("-L", argv)
        self.assertNotIn("-v", argv)
        self.assertNotIn("RequestTTY=force", argv)
        self.assertEqual(argv[-3:-1], ["--", "macbook"])
        self.assertTrue(argv[-1].startswith("sh -c '"))


if __name__ == "__main__":
    unittest.main()
