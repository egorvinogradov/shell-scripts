import json, os, shutil, subprocess, sys, unittest
from test_watcher import Env, W, T0, MIN, OLD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def undo(lines, ev):
    out = list(lines)
    for h in sorted(ev["h"], key=lambda h: -h["n"]):
        p = h["n"] - 1
        assert out[p:p + len(h["+"])] == h["+"], "history chain broken"
        out[p:p + len(h["+"])] = h["-"]
    return out


class ImportTests(unittest.TestCase):
    def test_archive_is_joined_into_a_continuous_history(self):
        e = Env()
        try:
            notes = e.disk("notes.txt", "n1\nn2\n", OLD)
            anchor = e.disk("anchor.txt", "a\n", OLD)
            # ---- phase 1: the log that later gets archived
            e.step(T0, [("f", anchor, None), ("f", notes, None)])
            e.step(T0 + 10 * MIN, [("f", anchor, None), ("f", notes, None), ("u", "u line 1")])
            e.step(T0 + 20 * MIN, [("f", anchor, None), ("f", notes, "n1\nn2\nn3\n"), ("u", "u line 1\nu line 2")])
            e.step(T0 + 30 * MIN, [("f", anchor, None), ("f", notes, "n1\nN2\nn3\n"), ("u", "u line 1\nU LINE 2")])
            arch = os.path.join(e.logdir, "archive-test")
            os.makedirs(arch)
            shutil.copytree(e.w.log.days, os.path.join(arch, "days"))
            old_state = {"tabs": {tid: {"text": rec["text"], "file": rec["file"], "title": rec["title"]} for tid, rec in e.w.tabs.items()}}
            json.dump(old_state, open(os.path.join(arch, "state.json"), "w"))
            # ---- the upgrade: fresh live log, first run over the same session (silent baseline)
            shutil.rmtree(e.w.log.days)
            for n in ("state.json", "index.js", "current.js"):
                if os.path.exists(os.path.join(e.logdir, n)):
                    os.remove(os.path.join(e.logdir, n))
            e.restart()
            tabs_now = [("f", anchor, None), ("f", notes, "n1\nN2\nn3\n"), ("u", "u line 1\nU LINE 2")]
            e.step(T0 + 31 * MIN, tabs_now)
            e.step(T0 + 50 * MIN, [("f", anchor, None), ("f", notes, "n1\nN2\nn3\nn4\n"), ("u", "u line 1\nU LINE 2\nu line 3")])
            self.assertEqual(sum(1 for x in e.events() if x.get("h")), 2)
            # ---- import
            r = subprocess.run([sys.executable, os.path.join(ROOT, "import_archive.py"), arch, "--log-dir", e.logdir], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("joined", r.stdout)
            self.assertTrue(os.path.isdir(os.path.join(e.logdir, "imported-archive-test")))
            e.restart()
            e.step(T0 + 51 * MIN, [("f", anchor, None), ("f", notes, "n1\nN2\nn3\nn4\n"), ("u", "u line 1\nU LINE 2\nu line 3")])   # unchanged: rewrites current.js
            # ---- blame now reaches back into the archived period
            cur = {t["title"]: t for t in e.current()}
            for title, tab in cur.items():
                ev = tab["ev"]
                lines = tab["text"].split("\n")
                got = {}
                for start, n, eid in tab["segs"]:
                    for i in range(start - 1, start - 1 + n):
                        got[i] = (ev[str(eid)]["k"], ev[str(eid)]["t"])
                cur[title] = (lines, got)
            nl, nb = cur["notes.txt"]
            self.assertEqual([nb[i] for i in range(5)], [("baseline", nb[0][1]), ("edit", T0 + 30 * MIN), ("edit", T0 + 20 * MIN), ("edit", T0 + 50 * MIN), ("baseline", nb[4][1])])
            self.assertTrue(all(meta for meta in e.current()[1]["ev"].values()))
            u = next(t for t in e.current() if t["file"] is None)
            ulines = u["text"].split("\n")
            ukind = {i: u["ev"][str(eid)] for start, n, eid in u["segs"] for i in range(start - 1, start - 1 + n)}
            self.assertEqual((ukind[0]["k"], ukind[0]["t"]), ("new", T0 + 10 * MIN))        # typed in the archived period
            self.assertEqual((ukind[1]["k"], ukind[1]["t"]), ("edit", T0 + 30 * MIN))
            self.assertEqual((ukind[2]["k"], ukind[2]["t"]), ("edit", T0 + 50 * MIN))        # typed after the upgrade
            # ---- one unbroken chain from the current text back to before the first archived change
            for tab in e.current():
                ids = set(tab["ids"])
                evs = sorted((x for x in e.events() if x["id"] in ids and x.get("h") and x.get("e") is not None), key=lambda x: x["e"])
                lines = tab["text"].split("\n")
                for ev in reversed(evs):
                    lines = undo(lines, ev)
                if tab["file"] is None:
                    self.assertEqual(lines, [""])                                            # an untitled tab started empty
                    self.assertEqual(len(evs), 4)                                            # new, 2 edits before the upgrade, 1 after
                elif tab["title"] == "notes.txt":
                    self.assertEqual(lines, ["n1", "n2", ""])                                # the file as it was before the first test edit
            # the archived 'close/open/save' style entries are in the log too, mapped to the live tab id
            self.assertTrue(any(x["id"] == u["id"] and x["k"] == "new" for x in e.events()))
            # importing twice is refused
            r2 = subprocess.run([sys.executable, os.path.join(ROOT, "import_archive.py"), os.path.join(e.logdir, "imported-archive-test"), "--log-dir", e.logdir],
                                capture_output=True, text=True)
            self.assertNotEqual(r2.returncode, 0)
        finally:
            e.close()


if __name__ == "__main__":
    unittest.main()
