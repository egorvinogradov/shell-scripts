# sublime-log

Background change log for every Sublime Text tab. `sublime_log` opens a page with two views: **File** (default: every open tab's current text,
each block labelled with when it was added; click a line for that change, its earlier versions and a full version history) and **Changes**
(what was added / removed per time range).

    ./install.sh [--log-dir PATH]   # launchd agent (login + auto-restart) and ~/.local/bin/sublime_log
    ./uninstall.sh [--purge]        # remove them; logs stay unless --purge

    sublime_log                     today          sublime_log 2h | 3d | week | month | all
    sublime_log y                   yesterday      sublime_log status
    sublime_log 2026-10-05          a day          sublime_log --text y   (print in terminal, no browser)
    sublime_log 2026-10-01 2026-10-05   a range    sublime_log --no-open  (just write the range, print viewer path)
    sublime_log --changes [range]   open on the Changes view     sublime_log --blame   (terminal: text + when each line was added)

Files here: `sublime_log_live.py` (Sublime plugin: writes live-session.json 0.3 s after every edit, copied into Packages/User by install.sh), `sublime_log_watcher.py` (the daemon, kqueue + debounce), `sublime_log` (CLI), `viewer.html` (static page, works from file://),
`install.sh`, `uninstall.sh`.

Log dir (default `~/.local/share/sublime-log`, remembered in `~/.config/sublime-log/config.json`):
`days/YYYY-MM-DD.js` (UTC day, one `SUBLOG_EVENT({...});` JSONP line per change, rolls to `.2.js` past 2 MB), `index.js`, `state.json`,
`watcher-status.json`, `watcher.log`, `viewer.html` (copy of the one here, refreshed on every run), `open.js` (range the CLI asked for).
The log holds everything typed in tabs, so the folder is chmod 700 — keep it out of Dropbox.

How it works: Sublime's `Auto Save Session.sublime_session` (newest `Sublime Text*/Local/`) holds unsaved text; clean tabs are read from disk.
The watcher is woken by kqueue, logs within ~1 s of each Sublime flush (never more than 5 s), and folds edits to one tab less than 7.5 s apart into a single entry.
Event time = the session file's mtime, i.e. the last Sublime flush, so within seconds of the typing. Untitled tabs have no id in the session,
so they are matched between snapshots by text similarity / tab slot. Nothing is recorded while the Mac is off or Sublime has no windows.

Blame: `state.json` keeps, per tab, which log entry each line comes from (diffs carry origins forward; untouched lines of a file keep
"saved <file mtime>"; lines of an untitled tab present at install keep "before tracking"). `current.js` is that, plus the current text, for the
viewer. A tab turned into a file (Save As) keeps its history; a closed file tab keeps it for 90 days so reopening resumes it.
Version history is rebuilt by undoing log entries from the current text (the viewer verifies every step, and says so if the file
changed while not tracked). Tabs over ~500 KB are listed but not shown in the File view.

Tests: `tests/run_all.sh` (watcher logic + fuzz, viewer helpers in node, the viewer clicked through in headless Chrome).
