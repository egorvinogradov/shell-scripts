"""Run: python3 -m unittest discover -s ~/repos/shell-scripts/sublime-log/tests -v"""
import importlib.machinery, importlib.util, json, os, random, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
loader = importlib.machinery.SourceFileLoader("watcher", os.path.join(HERE, "..", "sublime_log_watcher.py"))
W = importlib.util.module_from_spec(importlib.util.spec_from_loader("watcher", loader))
loader.exec_module(W)

MIN = 60_000
T0 = 1_790_000_000_000
OLD = 1_500_000_000_000          # a file "saved long ago"


class Env:
    """A fake Sublime session + a Watcher over it. Files are real (tmpdir) so disk reads behave."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="sublog-test-")
        self.files = os.path.join(self.dir, "files")
        os.makedirs(self.files)
        self.session = os.path.join(self.dir, "Auto Save Session.sublime_session")
        self.logdir = os.path.join(self.dir, "log")
        self.restart()

    def restart(self):
        self.w = W.Watcher(self.session, self.logdir)

    def disk(self, name, text, mtime=None):
        p = os.path.join(self.files, name)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        if mtime:
            os.utime(p, (mtime / 1000, mtime / 1000))
        return p

    def step(self, t, tabs):
        """tabs: list of ('u', text) | ('f', path, text_or_None_if_clean)."""
        bufs, sheets = [], []
        for i, tb in enumerate(tabs):
            if tb[0] == "u":
                bufs.append({"contents": tb[1], "settings": {}})
            else:
                b = {"file": tb[1], "settings": {}}
                if tb[2] is not None:
                    b["contents"] = tb[2]
                bufs.append(b)
            sheets.append({"buffer": i})
        with open(self.session, "w", encoding="utf-8") as f:
            json.dump({"windows": [{"buffers": bufs, "groups": [{"sheets": sheets}]}]}, f)
        self.w.process(t)

    def events(self):
        out = []
        for p in sorted(os.listdir(self.w.log.days)):
            for line in open(os.path.join(self.w.log.days, p), encoding="utf-8"):
                out.append(json.loads(line[len("SUBLOG_EVENT("):].rstrip().rstrip(";").rstrip(")")))
        return out

    def current(self):
        raw = open(self.w.current_path, encoding="utf-8").read()
        return json.loads(raw[len("window.SUBLOG_CURRENT="):].rstrip().rstrip(";"))["tabs"]

    def blame(self, tab_index=0):
        """[(line text, kind, t)] for the n-th open tab in current.js."""
        tab = self.current()[tab_index]
        lines = tab["text"].split("\n")
        out = [None] * len(lines)
        for start, n, e in tab["segs"]:
            meta = tab["ev"][str(e)]
            for i in range(start - 1, start - 1 + n):
                out[i] = (lines[i], meta["k"], meta["t"])
        assert all(o is not None for o in out), "every line must have an origin"
        return out

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class BlameTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.anchor = self.env.disk("anchor.txt", "anchor\n", OLD)

    def tearDown(self):
        self.env.close()

    def test_new_untitled_tab_blame(self):
        e = self.env
        e.step(T0, [("f", self.anchor, None)])                        # first run: silent baseline
        self.assertEqual(e.events(), [])
        e.step(T0 + 10 * MIN, [("f", self.anchor, None), ("u", "a\nb")])
        self.assertEqual([x["k"] for x in e.events()], ["new"])
        self.assertEqual(e.blame(1), [("a", "new", T0 + 10 * MIN), ("b", "new", T0 + 10 * MIN)])
        e.step(T0 + 20 * MIN, [("f", self.anchor, None), ("u", "a\nb\nc")])
        b = e.blame(1)
        self.assertEqual([x[1:] for x in b], [("new", T0 + 10 * MIN), ("new", T0 + 10 * MIN), ("edit", T0 + 20 * MIN)])
        e.step(T0 + 30 * MIN, [("f", self.anchor, None), ("u", "a\nB\nc")])
        self.assertEqual([x[1:] for x in e.blame(1)], [("new", T0 + 10 * MIN), ("edit", T0 + 30 * MIN), ("edit", T0 + 20 * MIN)])
        e.step(T0 + 40 * MIN, [("f", self.anchor, None), ("u", "B\nc")])      # delete first line: others keep origin
        self.assertEqual([x[1:] for x in e.blame(1)], [("edit", T0 + 30 * MIN), ("edit", T0 + 20 * MIN)])
        self.assertEqual(len(e.events()), 4)

    def test_old_saved_file_then_edited(self):
        e = self.env
        p = e.disk("old.txt", "one\ntwo\nthree\n", OLD)
        e.step(T0, [("f", p, None)])
        self.assertEqual(e.events(), [])
        self.assertEqual({x[1:] for x in e.blame(0)}, {("baseline", OLD)})            # all lines: "saved long ago"
        e.step(T0 + 5 * MIN, [("f", p, "ONE\ntwo\nthree\nfour\n")])
        b = e.blame(0)
        self.assertEqual([x[1:] for x in b], [("edit", T0 + 5 * MIN), ("baseline", OLD), ("baseline", OLD),
                                              ("edit", T0 + 5 * MIN), ("baseline", OLD)])
        # save: the tab turns clean and disk has the new text
        e.disk("old.txt", "ONE\ntwo\nthree\nfour\n")
        e.step(T0 + 6 * MIN, [("f", p, None)])
        self.assertEqual([x["k"] for x in e.events()], ["edit", "save"])
        self.assertEqual([x[1:] for x in e.blame(0)], [("edit", T0 + 5 * MIN), ("baseline", OLD), ("baseline", OLD),
                                                       ("edit", T0 + 5 * MIN), ("baseline", OLD)])
        # someone else changes the file on disk while it is open and clean
        e.disk("old.txt", "ONE\ntwo\nTHREE\nfour\n")
        e.step(T0 + 9 * MIN, [("f", p, None)])
        last = e.events()[-1]
        self.assertEqual((last["k"], last.get("src")), ("edit", "disk"))
        self.assertEqual(e.blame(0)[2][1:], ("edit", T0 + 9 * MIN))

    def test_file_opened_later_has_saved_time_as_baseline(self):
        e = self.env
        e.step(T0, [("f", self.anchor, None)])
        p = e.disk("later.txt", "x\ny\n", OLD)
        e.step(T0 + MIN, [("f", self.anchor, None), ("f", p, None)])
        self.assertEqual([x["k"] for x in e.events()], ["open"])
        self.assertEqual({x[1:] for x in e.blame(1)}, {("baseline", OLD)})
        e.step(T0 + 10 * MIN, [("f", self.anchor, None), ("f", p, "x\ny\nz\n")])
        self.assertEqual([x[1:] for x in e.blame(1)], [("baseline", OLD), ("baseline", OLD), ("edit", T0 + 10 * MIN), ("baseline", OLD)])

    def test_dirty_file_present_at_first_run(self):
        e = self.env
        p = e.disk("d.txt", "a\nb\n", OLD)
        e.step(T0, [("f", p, "a\nB\n")])
        self.assertEqual(e.events(), [])
        self.assertEqual([x[1:] for x in e.blame(0)], [("baseline", OLD), ("unsaved", T0), ("baseline", OLD)])

    def test_save_as_keeps_history(self):
        e = self.env
        e.step(T0, [("f", self.anchor, None)])
        e.step(T0 + 10 * MIN, [("f", self.anchor, None), ("u", "draft\nline2")])
        e.step(T0 + 20 * MIN, [("f", self.anchor, None), ("u", "draft\nline2\nline3")])
        p = e.disk("saved.txt", "draft\nline2\nline3")
        e.step(T0 + 30 * MIN, [("f", self.anchor, None), ("f", p, None)])                 # Save As: same text, now a file
        kinds = [x["k"] for x in e.events()]
        self.assertEqual(kinds, ["new", "edit", "save"])
        self.assertNotIn("close", kinds)
        tab = e.current()[1]
        self.assertEqual(len(tab["ids"]), 2)
        self.assertEqual(tab["file"], p)
        self.assertEqual([x[1:] for x in e.blame(1)], [("new", T0 + 10 * MIN), ("new", T0 + 10 * MIN), ("edit", T0 + 20 * MIN)])
        e.step(T0 + 40 * MIN, [("f", self.anchor, None), ("f", p, "draft\nline2 edited\nline3")])
        self.assertEqual(e.blame(1)[1][1:], ("edit", T0 + 40 * MIN))
        self.assertEqual(e.blame(1)[0][1:], ("new", T0 + 10 * MIN))

    def test_close_and_reopen_resumes(self):
        e = self.env
        p = e.disk("r.txt", "a\nb\n", OLD)
        e.step(T0, [("f", self.anchor, None), ("f", p, None)])
        e.step(T0 + MIN * 5, [("f", self.anchor, None), ("f", p, "a\nb\nc\n")])
        e.disk("r.txt", "a\nb\nc\n")
        e.step(T0 + MIN * 6, [("f", self.anchor, None), ("f", p, None)])
        e.step(T0 + MIN * 7, [("f", self.anchor, None)])                                   # closed
        self.assertEqual(len(e.current()), 1)
        e.step(T0 + MIN * 60, [("f", self.anchor, None), ("f", p, None)])                   # reopened, unchanged
        self.assertEqual([x["k"] for x in e.events()][-2:], ["close", "open"])
        self.assertEqual([x[1:] for x in e.blame(1)], [("baseline", OLD), ("baseline", OLD), ("edit", T0 + MIN * 5), ("baseline", OLD)])
        e.step(T0 + MIN * 70, [("f", self.anchor, None)])
        e.disk("r.txt", "a\nb\nc\nd\n")                                                      # changed while closed
        e.step(T0 + MIN * 120, [("f", self.anchor, None), ("f", p, None)])
        self.assertEqual(e.events()[-1].get("src"), "disk")
        self.assertEqual(e.blame(1)[3][1:], ("edit", T0 + MIN * 120))

    def test_burst_merges_and_revert_drops_entry(self):
        e = self.env
        e.step(T0, [("f", self.anchor, None)])
        e.step(T0 + MIN, [("f", self.anchor, None), ("u", "hello")])
        e.step(T0 + 2 * MIN, [("f", self.anchor, None), ("u", "hello w")])
        e.step(T0 + 2 * MIN + 2000, [("f", self.anchor, None), ("u", "hello wo")])
        e.step(T0 + 2 * MIN + 4000, [("f", self.anchor, None), ("u", "hello wor\nnext")])
        ev = e.events()
        self.assertEqual([x["k"] for x in ev], ["new", "edit"])                              # three flushes -> one entry
        self.assertEqual(ev[1]["h"][0]["+"], ["hello wor", "next"])
        self.assertEqual({x[1:] for x in e.blame(1)}, {("edit", T0 + 2 * MIN + 4000)} | {("new", T0 + MIN)} - {("new", T0 + MIN)})
        e.step(T0 + 2 * MIN + 6000, [("f", self.anchor, None), ("u", "hello")])              # undone back to the start
        self.assertEqual([x["k"] for x in e.events()], ["new"])
        self.assertEqual(e.blame(1), [("hello", "new", T0 + MIN)])

    def test_restart_keeps_blame_and_old_format_is_archived(self):
        e = self.env
        e.step(T0, [("f", self.anchor, None), ("u", "x\ny")])
        e.step(T0 + 10 * MIN, [("f", self.anchor, None), ("u", "x\ny\nz")])
        before = e.blame(1)
        e.restart()
        e.step(T0 + 20 * MIN, [("f", self.anchor, None), ("u", "x\ny\nz")])
        self.assertEqual(e.blame(1), before)
        e.step(T0 + 30 * MIN, [("f", self.anchor, None), ("u", "x\nY\nz")])
        self.assertEqual(e.blame(1)[1][1:], ("edit", T0 + 30 * MIN))
        # a v1 state (no version) is archived, not read
        s = json.load(open(e.w.state_path))
        s.pop("version")
        json.dump(s, open(e.w.state_path, "w"))
        e.restart()
        self.assertTrue(any(n.startswith("archive-") for n in os.listdir(e.logdir)))
        self.assertEqual(e.w.tabs, {})

    def test_odd_texts(self):
        e = self.env
        e.step(T0, [("f", self.anchor, None)])
        for i, text in enumerate(["", "no newline", "crlf\r\nline\r\n", "ünïcödé ✓ 😀\nline", "\n\n\n", "x" * 5000 + "\n" + "y" * 30000]):
            e.step(T0 + (i + 1) * 10 * MIN, [("f", self.anchor, None), ("u", text)])
            tab = e.current()[1]
            self.assertEqual(tab["text"], text.replace("\r\n", "\n"))
            self.assertEqual(sum(n for _, n, _ in tab["segs"]), tab["text"].count("\n") + 1)
        big = "line\n" * 500_000                                                              # > 2 MB: tracked by presence only
        e.step(T0 + 99 * MIN, [("f", self.anchor, None), ("u", big)])
        self.assertIsNone(e.current()[1]["text"])

    def test_many_lines_fast(self):
        import time
        e = self.env
        text = "\n".join(f"line {i}" for i in range(20000))
        p = e.disk("big.txt", text, OLD)
        e.step(T0, [("f", p, None)])
        t = time.time()
        edited = text.replace("line 10000", "line TEN THOUSAND").replace("line 5", "line five")
        e.step(T0 + MIN, [("f", p, edited)])
        self.assertLess(time.time() - t, 5)
        changed = sum(1 for a, b in zip(text.split("\n"), edited.split("\n")) if a != b)             # same line count: line i vs line i
        self.assertEqual(sum(1 for x in e.blame(0) if x[1] == "edit"), changed)
        self.assertEqual(sum(1 for x in e.blame(0) if x[1] == "baseline"), 20000 - changed)


class DiffOps(unittest.TestCase):
    def rebuild(self, old, new):
        ops, a, b = W.diff_ops(old, new)
        out, pos = [], 0
        for i1, i2, j1, j2 in ops:
            self.assertGreaterEqual(i1, pos)
            out.extend(a[pos:i1])
            out.extend(b[j1:j2])
            pos = i2
        out.extend(a[pos:])
        self.assertEqual(out, b)
        self.assertIsNotNone(W.apply_ops([0] * len(a), ops, 1, len(b)))

    def test_small_and_big_paths_rebuild_new_text(self):
        rnd = random.Random(3)
        for n in (0, 1, 5, 80, 700, 4000):                    # 700x700 and above go through the system diff
            for _ in range(6):
                a = [f"l{rnd.randint(0, 3 * n + 1)}" for _ in range(n)]
                b = list(a)
                for _ in range(rnd.randint(0, 40)):
                    op = rnd.choice(["ins", "del", "mod"])
                    i = rnd.randrange(len(b) + 1)
                    if op == "ins":
                        b.insert(i, f"n{rnd.randint(0, 9)}")
                    elif op == "del" and b:
                        del b[min(i, len(b) - 1)]
                    elif b:
                        b[min(i, len(b) - 1)] += "!"
                self.rebuild("\n".join(a), "\n".join(b))

    def test_external_diff_is_used_and_finer_than_a_block(self):
        a = "\n".join(f"line {i}" for i in range(6000))
        b = a.replace("line 100\n", "LINE 100\n").replace("line 5000\n", "LINE 5000\n")
        ops, _, _ = W.diff_ops(a, b)
        self.assertEqual(len(ops), 2)


class Fuzz(unittest.TestCase):
    """Random edits: (1) each line's origin entry really contains that line, (2) walking the log backwards from the current text
    reproduces every earlier version exactly (this is what the viewer's version history relies on)."""

    def test_fuzz(self):
        rnd = random.Random(7)
        for trial in range(40):
            e = Env()
            try:
                anchor = e.disk("a.txt", "a\n", OLD)
                e.step(T0, [("f", anchor, None)])
                text, versions = "seed line\nsecond", []
                t = T0 + 10 * MIN
                e.step(t, [("f", anchor, None), ("u", text)])
                versions.append(text)
                for _ in range(rnd.randint(3, 25)):
                    lines = text.split("\n")
                    for _ in range(rnd.randint(1, 4)):
                        op = rnd.choice(["ins", "del", "mod", "dup"])
                        i = rnd.randrange(len(lines))
                        if op == "ins":
                            lines.insert(i, f"new{rnd.randint(0, 99)}")
                        elif op == "del" and len(lines) > 1:
                            del lines[i]
                        elif op == "mod":
                            lines[i] = lines[i] + f" m{rnd.randint(0, 9)}"
                        else:
                            lines.insert(i, lines[i])
                    if "\n".join(lines) == text:
                        continue
                    text = "\n".join(lines)
                    t += 10 * MIN                                                             # > merge window: one entry per step
                    e.step(t, [("f", anchor, None), ("u", text)])
                    versions.append(text)
                events = [x for x in e.events() if x.get("h")]
                tab = e.current()[1]
                self.assertEqual(tab["text"], text)
                # (1) origin sanity
                by_e = {x["e"]: x for x in events}
                cur_lines = text.split("\n")
                for start, n, ev_id in tab["segs"]:
                    for i in range(start - 1, start - 1 + n):
                        self.assertIn(cur_lines[i], by_e[ev_id]["h"][0]["+"] + sum((h["+"] for h in by_e[ev_id]["h"]), []))
                # (2) walk back
                cur = text.split("\n")
                for k, ev in enumerate(reversed(events)):
                    for h in sorted(ev["h"], key=lambda h: -h["n"]):
                        p = h["n"] - 1
                        self.assertEqual(cur[p:p + len(h["+"])], h["+"])
                        cur[p:p + len(h["+"])] = h["-"]
                    want = versions[len(versions) - 2 - k]
                    self.assertEqual("\n".join(cur), want if k < len(versions) - 1 else "")
            finally:
                e.close()


if __name__ == "__main__":
    unittest.main()
