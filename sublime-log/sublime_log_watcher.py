#!/usr/bin/env python3
"""sublime_log_watcher — keep a change log of every Sublime Text tab (what was added / removed, and when).

Sublime keeps a live "Auto Save Session" JSON next to its settings. Unsaved text lives in it (`contents`); clean
file-backed tabs are read from disk. macOS tells us when that file changes (kqueue), we wait until typing pauses
(debounce), diff each tab against its previous snapshot and append the difference to a JSONP log:

  <log_dir>/days/YYYY-MM-DD.js    one `SUBLOG_EVENT({...});` line per change, UTC day, rolls to .2.js, .3.js past 2 MB
  <log_dir>/index.js              which day files exist (the static viewer needs it, file:// cannot list folders)
  <log_dir>/state.json            last snapshot of every tab + which log entry each line comes from (a restart loses nothing)
  <log_dir>/current.js            every open tab's current text with per-line origin, for the viewer's file ("blame") view
  <log_dir>/watcher-status.json   pid / last check / last event, for `sublime_log status`

Only the session-file layout (windows[].groups[].sheets[] -> windows[].buffers[]) is relied on, so no Sublime
version is hard-coded and every key is read defensively. Stdlib only.
"""
import argparse, difflib, glob, json, os, re, select, signal, subprocess, sys, tempfile, time
from datetime import datetime, timezone

APP_SUPPORT = os.path.expanduser("~/Library/Application Support")
SESSION_NAME = "Auto Save Session.sublime_session"
CONFIG = os.path.expanduser("~/.config/sublime-log/config.json")
DEFAULT_LOG_DIR = os.path.expanduser("~/.local/share/sublime-log")

STATE_VERSION = 2
CURRENT_TEXT_CAP = 500_000  # tabs longer than this are not embedded in current.js (blame view needs the text)
CLOSED_KEEP_DAYS = 90       # closed file tabs keep their history this long, so reopening resumes it
MERGE_SECONDS = 7.5         # edits to one tab closer together than this are folded into a single log entry
QUIET_SECONDS = float(os.environ.get("SUBLOG_QUIET", 1))   # typing pause that closes a burst
MAX_WAIT_SECONDS = float(os.environ.get("SUBLOG_MAX_WAIT", 5))      # never sit on an unlogged change longer than this, even if typing never stops
SAFETY_CHECK_SECONDS = 60   # stat-only fallback in case a kernel event is ever missed
MAX_TEXT = 2_000_000        # larger tabs are tracked by hash only
MAX_HUNK_CHARS = 20_000     # per side of a hunk; longer text is cut and flagged
PART_BYTES = 2_000_000      # day file rolls to the next part past this size
SMALL_DIFF_CELLS = 250_000  # lines_old * lines_new beyond this -> the system `diff` instead of difflib (which is quadratic)


def log(msg):
    print(f"{datetime.now().isoformat(timespec='seconds')} {msg}", flush=True)


def log_dir_from_config(arg):
    if arg:
        return os.path.expanduser(arg)
    if os.environ.get("SUBLIME_LOG_DIR"):
        return os.path.expanduser(os.environ["SUBLIME_LOG_DIR"])
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return os.path.expanduser(json.load(f)["log_dir"])
    except Exception:
        return DEFAULT_LOG_DIR


def find_session(arg):
    """Newest Auto Save Session of any 'Sublime Text*' install (ST3, ST4, future)."""
    if arg:
        return os.path.expanduser(arg)
    found = glob.glob(os.path.join(APP_SUPPORT, "Sublime Text*", "Local", SESSION_NAME))
    found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return found[0] if found else os.path.join(APP_SUPPORT, "Sublime Text", "Local", SESSION_NAME)


def atomic_write(path, text):
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------- reading tabs out of the session

def read_text(path):
    try:
        if os.path.getsize(path) > MAX_TEXT:
            return None
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().replace("\r\n", "\n").replace("\r", "\n")
    except OSError:
        return None


def tab_title(buf, text, file):
    if file:
        return os.path.basename(file)
    name = (buf.get("settings") or {}).get("name")
    if name:
        return str(name)[:80]
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:60]
    return "untitled"


def read_tabs(session_path):
    """-> list of {key|None, file, title, text|None, dirty} in tab-strip order, or None if the session has no windows."""
    with open(session_path, encoding="utf-8") as f:
        data = json.load(f)
    windows = data.get("windows") or []
    if not windows:
        return None
    tabs, seen = [], set()
    for w in windows:
        buffers = w.get("buffers") or []
        for g in w.get("groups") or []:
            for sh in g.get("sheets") or []:
                idx = sh.get("buffer")
                if sh.get("semi_transient") or idx is None or not (0 <= idx < len(buffers)):
                    continue                    # preview tabs and non-text sheets are not tabs the user made
                buf = buffers[idx]
                file = buf.get("file")
                if file:
                    if file in seen:
                        continue
                    seen.add(file)
                contents = buf.get("contents")
                dirty = contents is not None
                text = contents if dirty else (read_text(file) if file else "")
                if text is not None:
                    text = text.replace("\r\n", "\n").replace("\r", "\n")
                    if len(text) > MAX_TEXT:
                        text = None
                tabs.append({"file": file, "title": tab_title(buf, text, file), "text": text, "dirty": dirty,
                             "pos": len(tabs)})
    return tabs


# ---------------------------------------------------------------- diffing

def _clip(lines):
    s = "\n".join(lines)
    return (s[:MAX_HUNK_CHARS], True) if len(s) > MAX_HUNK_CHARS else (s, False)


def diff_ops(old, new):
    """Line-level edit ops [(i1, i2, j1, j2)]: old lines i1:i2 became new lines j1:j2 (0-based, ascending). Also returns both line lists."""
    a, b = old.split("\n"), new.split("\n")
    pre = 0
    while pre < len(a) and pre < len(b) and a[pre] == b[pre]:
        pre += 1
    suf = 0
    while suf < len(a) - pre and suf < len(b) - pre and a[-1 - suf] == b[-1 - suf]:
        suf += 1
    am, bm = a[pre:len(a) - suf], b[pre:len(b) - suf]
    if not am and not bm:
        return [], a, b
    if len(am) * len(bm) > SMALL_DIFF_CELLS:
        ops = _external_diff(am, bm)
        if ops is None:                     # no `diff` available / it timed out: say "this whole block changed"
            ops = [(0, len(am), 0, len(bm))]
        return [(pre + i1, pre + i2, pre + j1, pre + j2) for i1, i2, j1, j2 in ops], a, b
    ops = [(pre + i1, pre + i2, pre + j1, pre + j2)
           for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, am, bm, autojunk=False).get_opcodes() if tag != "equal"]
    return ops, a, b


_DIFF_LINE = re.compile(r"^(\d+)(?:,(\d+))?([acd])(\d+)(?:,(\d+))?$")


def _external_diff(am, bm):
    """Big edits: difflib is quadratic, the system `diff` (Myers, C) is not. Returns ops over am/bm or None."""
    try:
        with tempfile.TemporaryDirectory() as d:
            fa, fb = os.path.join(d, "a"), os.path.join(d, "b")
            for p, lines in ((fa, am), (fb, bm)):
                with open(p, "w", encoding="utf-8", newline="") as f:
                    f.write("\n".join(lines) + "\n")
            r = subprocess.run(["diff", fa, fb], capture_output=True, text=True, timeout=20)
        if r.returncode not in (0, 1):
            return None
        ops = []
        for line in r.stdout.splitlines():
            m = _DIFF_LINE.match(line)
            if not m:
                continue
            a1, a2, kind, b1, b2 = int(m.group(1)), m.group(2), m.group(3), int(m.group(4)), m.group(5)
            a2 = int(a2) if a2 else a1
            b2 = int(b2) if b2 else b1
            if kind == "a":
                ops.append((a1, a1, b1 - 1, b2))
            elif kind == "d":
                ops.append((a1 - 1, a2, b1, b1))
            else:
                ops.append((a1 - 1, a2, b1 - 1, b2))
        return ops
    except Exception:
        return None


def ops_to_hunks(ops, a, b):
    """-> hunks [{o,n,-,+}] (1-based start lines in old/new; `cut` if a side was too long to keep), inserted and deleted line counts."""
    hunks, ins, dele = [], 0, 0
    for i1, i2, j1, j2 in ops:
        d, t1 = _clip(a[i1:i2])
        p, t2 = _clip(b[j1:j2])
        h = {"o": i1 + 1, "n": j1 + 1, "-": d.split("\n") if i2 > i1 else [], "+": p.split("\n") if j2 > j1 else []}
        if t1 or t2:
            h["cut"] = True
        hunks.append(h)
        dele += i2 - i1
        ins += j2 - j1
    return hunks, ins, dele


def diff_hunks(old, new):
    ops, a, b = diff_ops(old, new)
    return ops_to_hunks(ops, a, b)


def apply_ops(lines, ops, e, n_new):
    """Carry per-line origin ids across a diff: untouched lines keep theirs, inserted/replaced lines get `e`. None if the shape is off."""
    out, pos = [], 0
    for i1, i2, j1, j2 in ops:
        out.extend(lines[pos:i1])
        out.extend([e] * (j2 - j1))
        pos = i2
    out.extend(lines[pos:])
    return out if len(out) == n_new else None


def to_runs(lines):
    runs = []
    for e in lines:
        if runs and runs[-1][1] == e:
            runs[-1][0] += 1
        else:
            runs.append([1, e])
    return runs


def from_runs(runs):
    return [e for n, e in runs for _ in range(n)]


def nlines(text):
    return text.count("\n") + 1


def similarity(a, b):
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    if len(a) > 20000 or len(b) > 20000:        # cheap proxy for big tabs: shared head/tail
        n = min(len(a), len(b), 2000)
        return 0.9 if a[:n] == b[:n] or a[-n:] == b[-n:] else 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).quick_ratio() * 0.5 + \
        difflib.SequenceMatcher(None, a[:3000], b[:3000], autojunk=False).ratio() * 0.5


# ---------------------------------------------------------------- log files

class Log:
    def __init__(self, root):
        self.root = root
        self.days = os.path.join(root, "days")
        os.makedirs(self.days, exist_ok=True)
        os.chmod(root, 0o700)

    def _part_path(self, day):
        n = 1
        while True:
            name = f"{day}.js" if n == 1 else f"{day}.{n}.js"
            p = os.path.join(self.days, name)
            if not os.path.exists(p) or os.path.getsize(p) < PART_BYTES:
                return name, p
            n += 1

    def append(self, ev):
        day = datetime.fromtimestamp(ev["t"] / 1000, timezone.utc).strftime("%Y-%m-%d")
        name, path = self._part_path(day)
        new_file = not os.path.exists(path)
        offset = 0 if new_file else os.path.getsize(path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(self._line(ev))
        if new_file:
            self.write_index()
        return path, offset, os.path.getsize(path)

    @staticmethod
    def _line(ev):
        return "SUBLOG_EVENT(" + json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + ");\n"

    def rewrite_last(self, path, offset, ev):
        """Replace the last line (starting at `offset`) of a day file; ev=None drops it."""
        with open(path, "r+", encoding="utf-8") as f:
            f.seek(offset)
            f.truncate()
            if ev is not None:
                f.write(self._line(ev))
        return path, offset, os.path.getsize(path)

    def write_index(self):
        days = {}
        for p in sorted(glob.glob(os.path.join(self.days, "*.js"))):
            base = os.path.basename(p)
            days.setdefault(base[:10], []).append(base)
        atomic_write(os.path.join(self.root, "index.js"),
                     "window.SUBLOG_INDEX=" + json.dumps({"updated": int(time.time() * 1000), "days": days}) + ";\n")


# ---------------------------------------------------------------- the watcher

class Watcher:
    """Tracks every tab: appends diffs to the day log, and keeps per-line origin ("blame") so the viewer can show the
    current file with who-changed-what-when. Tab record (state.json, `lines` stored as runs):
      title, file, dirty, pos, text, lines[e per line], ev{str(e): {t,k[,src]}}, born, ids[all ids this tab had], closed
    e = id of the log entry (or baseline marker) a line comes from; ev[e].t is when that entry last changed."""

    def __init__(self, session, log_root):
        self.session_file = session
        self.live_file = os.path.join(log_root, "live-session.json")     # written by the Sublime plugin on every edit
        self.log = Log(log_root)
        self.state_path = os.path.join(log_root, "state.json")
        self.current_path = os.path.join(log_root, "current.js")
        self.status_path = os.path.join(log_root, "watcher-status.json")
        self.tabs = {}
        self.next_untitled = 1
        self.next_e = 1
        self.last_event = None
        self.bursts = {}        # tab id -> the entry still open for merging: {e, base, base_lines, t, path, offset, end}
        self._last_current = None
        self._load_state()
        try:
            with open(self.status_path, encoding="utf-8") as f:
                self.last_event = json.load(f).get("last_event")
        except Exception:
            pass

    @property
    def session(self):
        """Whichever of Sublime's own session file / the plugin's live snapshot was written last."""
        def mt(p):
            try:
                return os.path.getmtime(p)
            except OSError:
                return -1
        return self.live_file if mt(self.live_file) > mt(self.session_file) else self.session_file

    # ------------------------------------------------------------ state
    def _load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            s = None
        if s is not None and s.get("version") != STATE_VERSION:
            self._archive_old_log()
            s = None
        if s:
            self.next_untitled, self.next_e = s.get("next_untitled", 1), s.get("next_e", 1)
            for tid, rec in s.get("tabs", {}).items():
                rec["lines"] = from_runs(rec["lines"]) if rec.get("lines") is not None else None
                self.tabs[tid] = rec

    def _archive_old_log(self):
        """Log written by an older version has no line-origin info: keep it aside, start a fresh one."""
        dest = os.path.join(self.log.root, "archive-" + time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(dest, exist_ok=True)
        for name in ("state.json", "days", "index.js", "current.js"):
            src = os.path.join(self.log.root, name)
            if os.path.exists(src):
                os.rename(src, os.path.join(dest, name))
        os.makedirs(self.log.days, exist_ok=True)
        log(f"old-format log moved to {dest}")

    def _save_state(self):
        tabs = {}
        for tid, rec in self.tabs.items():
            r = dict(rec)
            r["lines"] = to_runs(rec["lines"]) if rec.get("lines") is not None else None
            tabs[tid] = r
        atomic_write(self.state_path, json.dumps({"version": STATE_VERSION, "tabs": tabs, "next_untitled": self.next_untitled,
                                                  "next_e": self.next_e}, ensure_ascii=False))

    def write_status(self, **extra):
        st = {"pid": os.getpid(), "session": self.session, "checked": int(time.time() * 1000),
              "last_event": self.last_event, "tabs": sum(1 for t in self.tabs.values() if not t.get("closed"))}
        st.update(extra)
        atomic_write(self.status_path, json.dumps(st))

    def write_current(self):
        """current.js: every open tab's current text + which log entry each line comes from (for the viewer's file view)."""
        out = []
        for tid, tab in sorted(((k, v) for k, v in self.tabs.items() if not v.get("closed")),
                               key=lambda kv: (kv[1].get("born", 0), kv[1].get("pos", 0))):
            text, lines = tab.get("text"), tab.get("lines")
            entry = {"id": tid, "ids": tab.get("ids", [tid]), "title": tab["title"], "file": tab.get("file"),
                     "dirty": bool(tab.get("dirty")), "born": tab.get("born", 0)}
            if text is None or lines is None or len(text) > CURRENT_TEXT_CAP:
                entry.update({"text": None, "segs": [], "ev": {}})
            else:
                segs, start = [], 1
                for n, e in to_runs(lines):
                    segs.append([start, n, e])
                    start += n
                entry.update({"text": text, "segs": segs, "ev": {str(e): tab["ev"].get(str(e), {"t": 0, "k": "baseline"}) for _, _, e in segs}})
            out.append(entry)
        payload = "window.SUBLOG_CURRENT=" + json.dumps({"updated": int(time.time() * 1000), "tabs": out}, ensure_ascii=False) + ";\n"
        body = payload.split(",", 1)[1]                       # ignore the `updated` stamp when deciding whether anything changed
        if body != self._last_current:
            atomic_write(self.current_path, payload)
            self._last_current = body

    # ------------------------------------------------------------ events
    def _new_e(self):
        e = self.next_e
        self.next_e += 1
        return e

    def _event(self, t, tid, tab, kind, **extra):
        ev = {"t": t, "id": tid, "title": tab["title"], "file": tab.get("file"), "k": kind}
        ev.update(extra)
        return ev

    def _log_event(self, ev):
        self.log.append(ev)
        self.last_event = ev["t"]

    def _tab(self, tid, x, text, lines, ev, born):
        return {"title": x["title"], "file": x["file"], "dirty": x["dirty"], "pos": x["pos"], "text": text, "lines": lines,
                "ev": ev, "born": born, "ids": [tid], "closed": False}

    def _match_untitled(self, new_untitled):
        """Pair untitled tabs in the new snapshot with tracked ones. Untitled tabs have no id in the session file."""
        old = {tid: tab for tid, tab in self.tabs.items() if tid.startswith("u") and not tab.get("closed")}
        pairs, left_new, left_old = {}, list(range(len(new_untitled))), set(old)
        scored = sorted(((similarity(old[tid]["text"] or "", new_untitled[i]["text"] or ""), tid, i)
                         for tid in old for i in range(len(new_untitled))), reverse=True)
        for sc, tid, i in scored:
            if sc >= 0.5 and tid in left_old and i in left_new:
                pairs[i] = tid
                left_old.discard(tid)
                left_new.remove(i)
        for i in list(left_new):                # same tab-strip slot, text rewritten beyond recognition
            for tid in list(left_old):
                if old[tid].get("pos") == new_untitled[i]["pos"]:
                    pairs[i] = tid
                    left_old.discard(tid)
                    left_new.remove(i)
                    break
        return pairs

    # ------------------------------------------------------------ one tab
    def _edit(self, t, tid, x, tab, text, src, log_it, kind="edit"):
        """tab text -> `text`: log it (merging into the open burst when typing continues) and carry line origins."""
        prev_text = tab["text"]
        ops, a, b = diff_ops(prev_text, text)
        if not ops:
            tab["text"] = text
            return
        burst = self.bursts.get(tid)
        merge = bool(log_it and burst and src is None and t - burst["t"] <= MERGE_SECONDS * 1000
                     and os.path.exists(burst["path"]) and os.path.getsize(burst["path"]) == burst["end"])
        if merge:
            e = burst["e"]
            hunks, ins, dele = diff_hunks(burst["base"], text)          # one entry for the whole burst: diff from where it began
            if not hunks:                                                # typed and deleted again: nothing changed overall
                self.log.rewrite_last(burst["path"], burst["offset"], None)
                tab["lines"], tab["text"] = list(burst["base_lines"]), text
                del self.bursts[tid]
                return
            ev = self._event(t, tid, tab, "edit", e=e, ins=ins, **{"del": dele}, h=hunks)
            burst["path"], burst["offset"], burst["end"] = self.log.rewrite_last(burst["path"], burst["offset"], ev)
            burst["t"] = t
            self.last_event = t
        else:
            e = self._new_e()
            if log_it:
                hunks, ins, dele = ops_to_hunks(ops, a, b)
                ev = self._event(t, tid, tab, "edit", e=e, ins=ins, **{"del": dele}, h=hunks, **({"src": src} if src else {}))
                path, offset, end = self.log.append(ev)
                self.last_event = t
                if src is None:
                    self.bursts[tid] = {"e": e, "base": prev_text, "base_lines": list(tab["lines"] or []), "t": t,
                                        "path": path, "offset": offset, "end": end}
                else:
                    self.bursts.pop(tid, None)
        lines = apply_ops(tab["lines"], ops, e, len(b)) if tab.get("lines") is not None else None
        tab["lines"] = lines if lines is not None else [e] * len(b)    # shape mismatch: restart this tab's blame rather than lie
        tab["ev"][str(e)] = {"t": t, "k": kind, **({"src": src} if src else {})}
        tab["text"] = text

    def _new_tab(self, t, tid, x, first_run):
        text = x["text"]
        if text is None:                                                 # too big to diff: presence only
            self.tabs[tid] = self._tab(tid, x, None, None, {}, 0 if first_run else t)
            if not first_run:
                self._log_event(self._event(t, tid, x, "open", saved=not x["dirty"]))
            return
        if x["file"]:
            disk = read_text(x["file"])
            base = disk if disk is not None else text
            try:
                saved_at = int(os.path.getmtime(x["file"]) * 1000)       # untouched lines count as "last saved then"
            except OSError:
                saved_at = t
            e0 = self._new_e()
            tab = self._tab(tid, x, base, [e0] * nlines(base), {str(e0): {"t": saved_at, "k": "baseline"}}, 0 if first_run else t)
            self.tabs[tid] = tab
            if not first_run:
                self._log_event(self._event(t, tid, x, "open", saved=not x["dirty"]))
            if text != base:
                self._edit(t, tid, x, tab, text, None, not first_run, "unsaved" if first_run else "edit")
        elif first_run:
            e0 = self._new_e()
            self.tabs[tid] = self._tab(tid, x, text, [e0] * nlines(text), {str(e0): {"t": t, "k": "baseline"}}, 0)
        else:
            e = self._new_e()
            ops, a, b = diff_ops("", text)
            hunks, ins, dele = ops_to_hunks(ops, a, b)
            tab = self._tab(tid, x, text, [e] * nlines(text), {str(e): {"t": t, "k": "new"}}, t)
            self.tabs[tid] = tab
            self._log_event(self._event(t, tid, x, "new", e=e, ins=ins, **{"del": dele}, h=hunks) if hunks else
                            self._event(t, tid, x, "new", e=e))

    def _update_tab(self, t, tid, x, tab):
        text = x["text"]
        if tab.get("closed"):                                            # reopened: carry on where we left off
            tab["closed"] = False
            tab.pop("closed_t", None)
            self._log_event(self._event(t, tid, x, "open", saved=not x["dirty"]))
        if text is None:
            if not x["file"] or x["dirty"]:                              # an unsaved tab grew past the size limit: stop pretending
                tab["text"], tab["lines"] = None, None
            # clean file we cannot read right now (permissions / too big): keep the old baseline
        elif tab.get("text") is None:
            e0 = self._new_e()                                           # became readable again: re-baseline
            tab["text"], tab["lines"] = text, [e0] * nlines(text)
            tab["ev"][str(e0)] = {"t": t, "k": "baseline"}
        elif text != tab["text"]:
            self._edit(t, tid, x, tab, text, None if (x["dirty"] or not x["file"]) else "disk", True)
        elif tab.get("dirty") and not x["dirty"] and x["file"]:
            self._log_event(self._event(t, tid, x, "save"))
        tab.update({"title": x["title"], "file": x["file"], "dirty": x["dirty"], "pos": x["pos"]})

    def process(self, t):
        tabs = read_tabs(self.session)
        if tabs is None:                        # no windows: Sublime is quitting / not running; keep state as is
            return
        first_run = not os.path.exists(self.state_path)
        untitled = [x for x in tabs if not x["file"]]
        pairs = self._match_untitled(untitled)
        current = {}
        for i, x in enumerate(untitled):
            if i in pairs:
                tid = pairs[i]
            else:
                tid = f"u{self.next_untitled}"
                self.next_untitled += 1
            current[tid] = x
        for x in tabs:
            if x["file"]:
                current["f:" + x["file"]] = x

        # an untitled tab that became a file in the same snapshot is "Save As", not close + open: keep its history
        fresh_files = [tid for tid in current if tid.startswith("f:") and (tid not in self.tabs or self.tabs[tid].get("closed"))]
        for old in [tid for tid in self.tabs if tid.startswith("u") and tid not in current and not self.tabs[tid].get("closed")]:
            for nid in fresh_files:
                if similarity(self.tabs[old]["text"] or "", current[nid]["text"] or "") >= 0.9:
                    tab = self.tabs.pop(old)
                    self.bursts.pop(old, None)
                    tab["ids"] = tab.get("ids", [old]) + [nid]
                    tab.update({"file": current[nid]["file"], "title": current[nid]["title"], "dirty": current[nid]["dirty"], "closed": False})
                    self.tabs[nid] = tab
                    self._log_event(self._event(t, nid, tab, "save", **{"as": current[nid]["file"], "from": old}))
                    fresh_files.remove(nid)
                    break

        for tid, x in current.items():
            tab = self.tabs.get(tid)
            if tab is None:
                self._new_tab(t, tid, x, first_run)
            else:
                self._update_tab(t, tid, x, tab)
        for tid in [k for k, v in self.tabs.items() if k not in current and not v.get("closed")]:
            self._log_event(self._event(t, tid, self.tabs[tid], "close"))
            self.bursts.pop(tid, None)
            if tid.startswith("u"):
                del self.tabs[tid]
            else:
                self.tabs[tid].update({"closed": True, "closed_t": t})
        for tid in [k for k, v in self.tabs.items() if v.get("closed") and t - v.get("closed_t", t) > CLOSED_KEEP_DAYS * 86400000]:
            del self.tabs[tid]
        self._save_state()
        self.write_current()

    def run(self):
        directory = os.path.dirname(self.session_file)
        log(f"watching {self.session_file} (+ live snapshot in {self.log.root})")
        kq = select.kqueue()
        fd_dir = os.open(directory, os.O_RDONLY)
        fflags = select.KQ_NOTE_WRITE | select.KQ_NOTE_EXTEND | select.KQ_NOTE_ATTRIB | select.KQ_NOTE_DELETE | \
            select.KQ_NOTE_RENAME | select.KQ_NOTE_REVOKE
        flags = select.KQ_EV_ADD | select.KQ_EV_CLEAR
        kq.control([select.kevent(fd_dir, select.KQ_FILTER_VNODE, flags, fflags)], 0)
        fd_live = os.open(self.log.root, os.O_RDONLY)                    # the plugin replaces live-session.json atomically
        kq.control([select.kevent(fd_live, select.KQ_FILTER_VNODE, flags, select.KQ_NOTE_WRITE)], 0)
        fd_file, sig = None, (None, None, None)

        def attach_file():
            nonlocal fd_file
            if fd_file is not None:
                os.close(fd_file)
                fd_file = None
            try:
                fd_file = os.open(self.session_file, os.O_RDONLY)
                kq.control([select.kevent(fd_file, select.KQ_FILTER_VNODE, flags, fflags)], 0)
            except OSError:
                fd_file = None

        def signature():
            try:
                s = os.stat(self.session_file)
                return (s.st_ino, s.st_mtime_ns, s.st_size)
            except OSError:
                return (None, None, None)

        attach_file()
        pending_since = last_event_at = None
        self._process_now(time.time())          # catch up on whatever happened while we were not running
        sig = signature()
        stop = {"v": False}
        for s in (signal.SIGTERM, signal.SIGINT):
            signal.signal(s, lambda *_: stop.update(v=True))
        while not stop["v"]:
            now = time.time()
            if pending_since is None:
                timeout = SAFETY_CHECK_SECONDS
            else:
                timeout = max(0.2, min(last_event_at + QUIET_SECONDS, pending_since + MAX_WAIT_SECONDS) - now)
            try:
                events = kq.control(None, 8, timeout)
            except InterruptedError:
                continue
            now = time.time()
            if events:
                log(f"kqueue: {len(events)} event(s)")
                if any(e.ident == fd_file and e.fflags & (select.KQ_NOTE_DELETE | select.KQ_NOTE_RENAME | select.KQ_NOTE_REVOKE)
                       for e in events) or fd_file is None:
                    time.sleep(0.3)             # atomic-replace write: re-attach to the new inode
                    attach_file()
                pending_since = pending_since or now
                last_event_at = now
            elif pending_since is None:         # nothing from the kernel: cheap stat as a safety net
                new_sig = signature()
                if new_sig != sig:
                    log("safety check saw a change the kernel did not report")
                    if new_sig[0] != sig[0]:
                        attach_file()
                    pending_since, last_event_at = now, now
            if pending_since is not None and (now - last_event_at >= QUIET_SECONDS or now - pending_since >= MAX_WAIT_SECONDS):
                log("processing")
                self._process_now(self._session_mtime_ms() / 1000)
                sig = signature()
                pending_since = last_event_at = None
        log("stopping")
        self._save_state()

    def _session_mtime_ms(self):
        try:
            return int(os.path.getmtime(self.session) * 1000)
        except OSError:
            return int(time.time() * 1000)

    def _process_now(self, t_seconds):
        for attempt in range(4):                # the file can be caught mid-write: retry on bad JSON
            try:
                self.process(int(t_seconds * 1000))
                self.write_status()
                return
            except (json.JSONDecodeError, FileNotFoundError) as e:
                if attempt == 3:
                    log(f"session unreadable ({e}); will retry on the next change")
                    self.write_status(error=str(e))
                    return
                time.sleep(1.5)
            except Exception as e:              # never die on a bad snapshot; launchd would only restart into the same one
                log(f"error while processing: {e!r}")
                self.write_status(error=repr(e))
                return


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log-dir", help=f"where the log lives (default: config.json, then {DEFAULT_LOG_DIR})")
    ap.add_argument("--session", help="Auto Save Session path (default: newest Sublime Text*/Local/ one)")
    ap.add_argument("--once", action="store_true", help="process the session once, then exit (for testing)")
    a = ap.parse_args()
    w = Watcher(find_session(a.session), log_dir_from_config(a.log_dir))
    if a.once:
        w.process(w._session_mtime_ms())
        w.write_status()
        return
    w.run()


if __name__ == "__main__":
    main()
