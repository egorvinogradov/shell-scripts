#!/usr/bin/env python3
"""sublime_log_watcher — keep a change log of every Sublime Text tab (what was added / removed, and when).

Sublime keeps a live "Auto Save Session" JSON next to its settings. Unsaved text lives in it (`contents`); clean
file-backed tabs are read from disk. macOS tells us when that file changes (kqueue), we wait until typing pauses
(debounce), diff each tab against its previous snapshot and append the difference to a JSONP log:

  <log_dir>/days/YYYY-MM-DD.js    one `SUBLOG_EVENT({...});` line per change, UTC day, rolls to .2.js, .3.js past 2 MB
  <log_dir>/index.js              which day files exist (the static viewer needs it, file:// cannot list folders)
  <log_dir>/state.json            last snapshot of every tab (so a restart loses nothing)
  <log_dir>/watcher-status.json   pid / last check / last event, for `sublime_log status`

Only the session-file layout (windows[].groups[].sheets[] -> windows[].buffers[]) is relied on, so no Sublime
version is hard-coded and every key is read defensively. Stdlib only.
"""
import argparse, difflib, glob, json, os, select, signal, sys, time
from datetime import datetime, timezone

APP_SUPPORT = os.path.expanduser("~/Library/Application Support")
SESSION_NAME = "Auto Save Session.sublime_session"
CONFIG = os.path.expanduser("~/.config/sublime-log/config.json")
DEFAULT_LOG_DIR = os.path.expanduser("~/.local/share/sublime-log")

MERGE_SECONDS = 90          # edits to one tab closer together than this are folded into a single log entry
QUIET_SECONDS = float(os.environ.get("SUBLOG_QUIET", 1))   # typing pause that closes a burst
MAX_WAIT_SECONDS = float(os.environ.get("SUBLOG_MAX_WAIT", 5))      # never sit on an unlogged change longer than this, even if typing never stops
SAFETY_CHECK_SECONDS = 60   # stat-only fallback in case a kernel event is ever missed
MAX_TEXT = 2_000_000        # larger tabs are tracked by hash only
MAX_HUNK_CHARS = 20_000     # per side of a hunk; longer text is cut and flagged
PART_BYTES = 2_000_000      # day file rolls to the next part past this size
BIG_DIFF_CELLS = 4_000_000  # lines_old * lines_new beyond this -> one whole-block hunk instead of a full diff


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
                tabs.append({"file": file, "title": tab_title(buf, text, file), "text": text, "dirty": dirty,
                             "pos": len(tabs)})
    return tabs


# ---------------------------------------------------------------- diffing

def _clip(lines):
    s = "\n".join(lines)
    return (s[:MAX_HUNK_CHARS], True) if len(s) > MAX_HUNK_CHARS else (s, False)


def diff_hunks(old, new):
    """Line-level hunks [{o,n,-,+}] (1-based start lines in old/new) plus total inserted/deleted line counts."""
    a, b = old.split("\n"), new.split("\n")
    pre = 0
    while pre < len(a) and pre < len(b) and a[pre] == b[pre]:
        pre += 1
    suf = 0
    while suf < len(a) - pre and suf < len(b) - pre and a[-1 - suf] == b[-1 - suf]:
        suf += 1
    am, bm = a[pre:len(a) - suf], b[pre:len(b) - suf]
    if not am and not bm:
        return [], 0, 0
    if len(am) * len(bm) > BIG_DIFF_CELLS:
        ops = [("replace", 0, len(am), 0, len(bm))]
    else:
        ops = [o for o in difflib.SequenceMatcher(None, am, bm, autojunk=False).get_opcodes() if o[0] != "equal"]
    hunks, ins, dele = [], 0, 0
    for _, i1, i2, j1, j2 in ops:
        d, t1 = _clip(am[i1:i2])
        p, t2 = _clip(bm[j1:j2])
        h = {"o": pre + i1 + 1, "n": pre + j1 + 1, "-": d.split("\n") if i2 > i1 else [], "+": p.split("\n") if j2 > j1 else []}
        if t1 or t2:
            h["cut"] = True
        hunks.append(h)
        dele += i2 - i1
        ins += j2 - j1
    return hunks, ins, dele


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
    def __init__(self, session, log_root):
        self.session_file = session
        self.live_file = os.path.join(log_root, "live-session.json")     # written by the Sublime plugin on every edit
        self.log = Log(log_root)
        self.state_path = os.path.join(log_root, "state.json")
        self.status_path = os.path.join(log_root, "watcher-status.json")
        self.tabs = {}          # id -> {title,file,text,hash,dirty}
        self.next_untitled = 1
        self.last_event = None
        self.bursts = {}        # tab id -> the entry still open for merging: {base, t, path, offset, end}
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

    def _load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                s = json.load(f)
            self.tabs, self.next_untitled = s.get("tabs", {}), s.get("next_untitled", 1)
        except Exception:
            self.tabs, self.next_untitled = {}, 1

    def _save_state(self):
        atomic_write(self.state_path, json.dumps({"tabs": self.tabs, "next_untitled": self.next_untitled}, ensure_ascii=False))

    def write_status(self, **extra):
        st = {"pid": os.getpid(), "session": self.session, "checked": int(time.time() * 1000),
              "last_event": self.last_event, "tabs": len(self.tabs)}
        st.update(extra)
        atomic_write(self.status_path, json.dumps(st))

    def _emit(self, t, tid, tab, kind, hunks=None, ins=0, dele=0, **extra):
        ev = {"t": t, "id": tid, "title": tab["title"], "file": tab.get("file"), "k": kind}
        if hunks:
            ev.update({"ins": ins, "del": dele, "h": hunks})
        ev.update(extra)
        b = self.bursts.get(tid)
        if kind == "edit" and hunks and b and not extra and t - b["t"] <= MERGE_SECONDS * 1000 \
                and os.path.exists(b["path"]) and os.path.getsize(b["path"]) == b["end"]:
            h2, i2, d2 = diff_hunks(b["base"], tab["text"])      # one entry for the whole burst: diff from where it began
            if h2:
                ev.update({"ins": i2, "del": d2, "h": h2})
                b["path"], b["offset"], b["end"] = self.log.rewrite_last(b["path"], b["offset"], ev)
            else:                                                  # typed and deleted again: nothing changed overall
                self.log.rewrite_last(b["path"], b["offset"], None)
                del self.bursts[tid]
            b["t"] = t
            self.last_event = t
            return
        path, offset, end = self.log.append(ev)
        if kind == "edit" and hunks and not extra:
            self.bursts[tid] = {"base": self._base, "t": t, "path": path, "offset": offset, "end": end}
        else:
            self.bursts.pop(tid, None)
        self.last_event = t

    def _match_untitled(self, new_untitled):
        """Pair untitled tabs in the new snapshot with tracked ones. Untitled tabs have no id in the session file."""
        old = {tid: tab for tid, tab in self.tabs.items() if tid.startswith("u")}
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

    def process(self, t):
        tabs = read_tabs(self.session)
        if tabs is None:                        # no windows: Sublime is quitting / not running; keep state as is
            return
        first_run = not self.tabs and not os.path.exists(self.state_path)
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

        for tid, x in current.items():
            prev = self.tabs.get(tid)
            text = x["text"]
            if prev is None:
                if not first_run:
                    self._emit(t, tid, x, "new" if not x["file"] else "open",
                               *(diff_hunks("", text) if (text and (not x["file"] or x["dirty"])) else ([], 0, 0)),
                               **({"saved": not x["dirty"]} if x["file"] else {}))
            elif text is None or prev.get("text") is None:
                if text is None and prev.get("text") is not None and x["file"]:
                    pass                        # unreadable right now (permissions / too big): keep the old baseline
                elif text is not None and prev.get("text") is None:
                    pass                        # became readable again: just re-baseline below
                else:
                    self._emit(t, tid, x, "edit", note="large file, diff skipped")
            elif text != prev["text"]:
                hunks, ins, dele = diff_hunks(prev["text"], text)
                self._base = prev["text"]
                if hunks:
                    self._emit(t, tid, x, "edit", hunks, ins, dele,
                               **({} if x["dirty"] or not x["file"] else {"src": "disk"}))
            elif prev.get("dirty") and not x["dirty"] and x["file"]:
                self._emit(t, tid, x, "save")
            self.tabs[tid] = {"title": x["title"], "file": x["file"], "dirty": x["dirty"], "pos": x["pos"],
                              "text": text if text is not None and len(text) <= MAX_TEXT else
                              (prev or {}).get("text")}
        for tid in [k for k in self.tabs if k not in current]:
            if not first_run:
                self._emit(t, tid, self.tabs[tid], "close")
            del self.tabs[tid]
        self._save_state()

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
