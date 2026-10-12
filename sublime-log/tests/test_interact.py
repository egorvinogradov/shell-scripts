"""Click through the viewer in headless Chrome: line -> detail -> versions -> tabs -> modes."""
import json, os, shutil, unittest, urllib.parse
from cdp import Chrome, CHROME
from test_watcher import Env, T0, MIN, OLD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@unittest.skipUnless(os.path.exists(CHROME), "Chrome not installed")
class Interact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e = cls.e = Env()
        cls.old = e.disk("old.txt", "alpha\nbeta\ngamma\n", OLD)
        e.step(T0, [("f", cls.old, None)])
        e.step(T0 + 10 * MIN, [("f", cls.old, None), ("u", "scratch one\nscratch two")])
        e.step(T0 + 20 * MIN, [("f", cls.old, "alpha\nBETA\ngamma\ndelta\n"), ("u", "scratch one\nscratch two")])
        e.step(T0 + 40 * MIN, [("f", cls.old, "alpha\nBETA\ngamma\ndelta\nepsilon\n"), ("u", "scratch one\nscratch two\nscratch three")])
        for name in ("viewer.html", "viewer_lib.js"):
            shutil.copyfile(os.path.join(ROOT, name), os.path.join(e.logdir, name))
        with open(os.path.join(e.logdir, "open.js"), "w") as f:
            f.write("window.SUBLOG_OPEN=" + json.dumps({"from": 0, "to": T0 + 99 * 86400000, "label": "All", "mode": "file", "ts": 1}) + ";\n")
        cls.url = "file://" + urllib.parse.quote(os.path.join(e.logdir, "viewer.html"))
        cls.c = Chrome()

    @classmethod
    def tearDownClass(cls):
        cls.c.close()
        cls.e.close()

    def setUp(self):
        self.c.errors.clear()
        self.c.goto(self.url + "#m=file&tab=" + urllib.parse.quote("f:" + self.old))

    def tearDown(self):
        self.assertEqual(self.c.errors, [])

    def click(self, sel):
        self.assertTrue(self.c.js(f'(()=>{{const e=document.querySelector({json.dumps(sel)}); if(!e) return false; e.click(); return true}})()'), "no element " + sel)

    def text(self, sel):
        return self.c.js(f'document.querySelector({json.dumps(sel)}) ? document.querySelector({json.dumps(sel)}).innerText : null')

    def test_blame_labels_on_load(self):
        rows = self.c.js('[...document.querySelectorAll(".fr")].map(r=>[r.querySelector(".no").innerText, r.querySelector(".cd").innerText, r.querySelector(".bl").innerText.replace(/\\s+/g," ").trim()])')
        by_line = {r[0]: r for r in rows}
        self.assertIn("saved", by_line["1"][2])                      # alpha: from the file saved long ago
        self.assertIn("edited", by_line["2"][2])                     # BETA
        self.assertIn("saved", by_line["3"][2])                      # gamma: untouched again, a new block after the edit
        self.assertEqual(by_line["2"][1], "BETA")

    def test_click_line_opens_detail_and_versions(self):
        self.click('.fr[data-line="5"]')                             # "epsilon" came with the second entry
        self.c.wait('document.querySelector("#detail") && !document.querySelector("#detail").hidden && document.querySelector("#dbefore")')
        self.assertIn("Line 5", self.text("#detail"))
        self.assertIn("epsilon", self.text("#detail"))
        self.assertIn("l=5", self.c.js("location.hash"))
        self.click("#dbefore")                                       # file as it was just before that change
        self.c.wait('document.querySelector("#vsel")')
        self.assertIn("Version 1 of 2", self.text(".banner"))
        lines = self.c.js('[...document.querySelectorAll(".fr .cd")].map(e=>e.innerText)')
        self.assertIn("delta", lines)
        self.assertNotIn("epsilon", lines)
        self.assertIn("v=1", self.c.js("location.hash"))
        self.click("#vold")                                          # one more step back: before BETA / delta existed
        self.c.wait('document.querySelector(".banner").innerText.includes("Version 0 of 2")')
        lines = self.c.js('[...document.querySelectorAll(".fr .cd")].map(e=>e.innerText)')
        self.assertIn("beta", lines)
        self.assertNotIn("BETA", lines)
        self.assertNotIn("delta", lines)
        self.assertTrue(self.c.js('document.querySelector("#vold").disabled'))
        self.click("#vnew"); self.click("#vnew")
        self.c.wait('document.querySelector(".banner").innerText.includes("Version 2 of 2")')
        self.assertIn("epsilon", self.c.js('document.querySelector("#file").innerText'))
        self.assertTrue(self.c.js('document.querySelector("#vnew").disabled'))                   # newest entry = the current text
        self.click("#vcur")
        self.c.wait('!document.querySelector("#vsel")')
        self.assertIn("Current text", self.text(".banner"))

    def test_version_view_marks_added_and_removed_lines(self):
        self.click('.fr[data-line="2"]')
        self.c.wait('document.querySelector("#dafter")')
        self.click("#dafter")
        self.c.wait('document.querySelector("#vsel")')
        self.assertEqual(self.c.js('document.querySelectorAll(".fr.add").length'), 2)            # BETA and delta
        self.assertEqual(self.text(".fr.del .cd"), "beta")                                       # the line that BETA replaced
        self.click("#vcur")
        self.c.wait('!document.querySelector("#vsel")')

    def test_switch_tabs_and_modes(self):
        tabs = self.c.js('[...document.querySelectorAll(".tab")].map(t=>t.innerText.replace(/\\s+/g," ").trim())')
        self.assertEqual(len(tabs), 2)
        self.click(".tab:not(.sel)")
        self.c.wait('document.querySelector(".tab.untitled.sel")')
        self.assertIn("scratch three", self.text("#file"))
        labels = self.c.js('[...document.querySelectorAll(".fr .bl")].map(e=>e.innerText.trim()).filter(Boolean)')
        self.assertTrue(any("new tab" in l for l in labels) and any("edited" in l for l in labels), labels)
        self.click("#m-changes")
        self.c.wait('document.querySelector("#m-changes").classList.contains("on") && document.querySelector(".ev")')
        self.assertIn("scratch three", self.text("main"))
        self.assertIn("m=changes", self.c.js("location.hash"))
        self.click("#m-file")
        self.c.wait('document.querySelector("#file")')

    def test_reload_keeps_position_and_escape_closes_detail(self):
        self.click('.fr[data-line="5"]')
        self.c.wait('document.querySelector("#dbefore")')
        self.c.goto(self.url + self.c.js("location.hash"))            # a browser refresh keeps tab + selected line
        self.c.wait('document.querySelector("#dbefore")')
        self.assertIn("Line 5", self.text("#detail"))
        self.c.js('document.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape"}))')
        self.c.wait('document.querySelector("#detail").hidden')

    def test_live_refresh_picks_up_new_edits(self):
        e = self.e
        e.step(T0 + 80 * MIN, [("f", self.old, "alpha\nBETA\ngamma\ndelta\nepsilon\nzeta\n"), ("u", "scratch one\nscratch two\nscratch three")])
        self.assertNotIn("zeta", self.c.js('document.querySelector("#file").innerText'))
        self.click("#refresh")                                        # the button re-reads current.js and the day files
        self.c.wait('document.querySelector("#file").innerText.includes("zeta")')


if __name__ == "__main__":
    unittest.main()
