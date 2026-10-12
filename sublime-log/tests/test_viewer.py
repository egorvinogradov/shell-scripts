"""Headless-Chrome check of viewer.html over file:// against a log produced by the real watcher code. Skips if Chrome is missing."""
import json, os, re, shutil, subprocess, sys, tempfile, unittest, urllib.parse
from test_watcher import Env, T0, MIN, OLD

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


@unittest.skipUnless(os.path.exists(CHROME), "Chrome not installed")
class ViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e = cls.e = Env()
        anchor = e.disk("anchor.txt", "anchor line\nsecond anchor line\n", OLD)
        e.step(T0, [("f", anchor, None)])
        # an untitled tab, edited twice, then Save As -> a file tab
        e.step(T0 + 10 * MIN, [("f", anchor, None), ("u", "draft <b>one</b>\nline two")])
        e.step(T0 + 30 * MIN, [("f", anchor, None), ("u", "draft <b>one</b>\nline two\nline three")])
        saved = e.disk("saved.txt", "draft <b>one</b>\nline two\nline three")
        e.step(T0 + 40 * MIN, [("f", anchor, None), ("f", saved, None)])
        # old file edited later
        e.step(T0 + 60 * MIN, [("f", anchor, "anchor line\nsecond ANCHOR line\nthird\n"), ("f", saved, None)])
        cls.saved = saved
        for name in ("viewer.html", "viewer_lib.js"):
            shutil.copyfile(os.path.join(ROOT, name), os.path.join(e.logdir, name))
        with open(os.path.join(e.logdir, "open.js"), "w") as f:     # a range that covers the fixture dates
            f.write("window.SUBLOG_OPEN=" + json.dumps({"from": 0, "to": T0 + 99 * 86400000, "label": "All", "mode": "file", "ts": 1}) + ";\n")

    @classmethod
    def tearDownClass(cls):
        cls.e.close()

    def dom(self, hash_=""):
        url = "file://" + urllib.parse.quote(os.path.join(self.e.logdir, "viewer.html")) + hash_
        udd = tempfile.mkdtemp(prefix="sublog-chrome-")
        try:
            r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--user-data-dir=" + udd, "--virtual-time-budget=9000",
                                "--enable-logging=stderr", "--v=0", "--dump-dom", url], capture_output=True, text=True, timeout=60)
        finally:
            shutil.rmtree(udd, ignore_errors=True)
        errs = [l for l in r.stderr.splitlines() if "CONSOLE" in l and ("Uncaught" in l or "error" in l.lower())]
        self.assertEqual(errs, [], "JS errors: " + "\n".join(errs))
        return r.stdout

    def text(self, dom):
        dom = re.sub(r"<(script|style)\b.*?</\1>", " ", dom, flags=re.S)       # visible text only, not the page's own code
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", dom))

    def assertIn(self, needle, hay, msg=None):                                  # never dump a whole page into the failure message
        self.assertTrue(needle in hay, f"missing {needle!r} in: {hay[:600]!r}")

    def assertNotIn(self, needle, hay, msg=None):
        self.assertFalse(needle in hay, f"unexpected {needle!r} in: {hay[:600]!r}")

    def test_file_view_default(self):
        dom = self.dom()
        t = self.text(dom)
        self.assertIn('class="fr', dom)
        for needle in ("anchor line", "second ANCHOR line", "third"):
            self.assertIn(needle, t)
        self.assertIn("saved", t)                                   # blame label for text from a file saved long ago
        self.assertIn("edited", t)                                  # and for the later edit
        self.assertNotIn("Loading history", t)
        tabs = re.findall(r'class="tab[^"]*" data-id="([^"]+)"', dom)
        self.assertEqual(len(tabs), 2)                              # anchor + the saved-as tab (one tab, not two)

    def test_untitled_then_saved_tab_shows_new_tab_blame(self):
        tab = "f:" + self.saved
        dom = self.dom("#m=file&tab=" + urllib.parse.quote(tab))
        self.assertIn("new tab", self.text(dom))                    # lines typed in the untitled tab keep their origin after Save As
        self.assertIn("draft &lt;b&gt;one&lt;/b&gt;", dom)         # html in the text is escaped, not interpreted

    def test_line_click_state_shows_detail_with_change(self):
        tab = "f:" + self.saved
        dom = self.dom("#m=file&tab=" + urllib.parse.quote(tab) + "&l=3")
        self.assertRegex(dom, r'<div class="detail" id="detail">\s*<h3>Line 3')
        t = self.text(dom)
        self.assertIn("File before this change", t)
        self.assertIn("line three", t)

    def test_baseline_line_detail(self):
        anchor = "f:" + os.path.join(self.e.files, "anchor.txt")
        dom = self.dom("#m=file&tab=" + urllib.parse.quote(anchor) + "&l=1")
        self.assertIn("already in the file", self.text(dom))

    def test_version_history_view(self):
        tab = "f:" + self.saved
        dom = self.dom("#m=file&tab=" + urllib.parse.quote(tab) + "&v=1")        # just after the first logged change
        t = self.text(dom)
        self.assertIn("Version 1 of 2", t)
        self.assertIn("line two", t)
        self.assertNotIn("line three", t)                           # added by the second entry
        dom0 = self.dom("#m=file&tab=" + urllib.parse.quote(tab) + "&v=0")
        self.assertIn("before the first logged change", self.text(dom0))
        self.assertNotIn("line two", self.text(dom0).split("Version 0 of 2")[1].split("Current text")[0])

    def test_changes_view_merges_save_as_into_one_tab(self):
        dom = self.dom("#m=changes")
        tabs = re.findall(r'class="tab[^"]*" data-id="([^"]+)"', dom)
        self.assertEqual(sorted(tabs), sorted(["f:" + os.path.join(self.e.files, "anchor.txt"), "f:" + self.saved]))
        t = self.text(dom)
        self.assertIn("edited", t)


if __name__ == "__main__":
    unittest.main()
