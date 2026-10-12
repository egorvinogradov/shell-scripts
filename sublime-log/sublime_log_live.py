# Sublime Text plugin (works on ST3 and ST4): writes every open tab's current text to <log_dir>/live-session.json
# ~0.3 s after each edit, in the same shape as Sublime's own session file. Sublime itself only flushes its session
# file every so often, so the watcher reads this one to see typing right away. Installed by sublime-log/install.sh.
import json
import os
import time

import sublime
import sublime_plugin

CONFIG = os.path.expanduser("~/.config/sublime-log/config.json")
DEFAULT_LOG_DIR = os.path.expanduser("~/.local/share/sublime-log")
DEBOUNCE_MS = 300
MAX_TEXT = 2000000

_generation = [0]


def _log_dir():
    try:
        with open(CONFIG) as f:
            return os.path.expanduser(json.load(f)["log_dir"])
    except Exception:
        return DEFAULT_LOG_DIR


def _snapshot():
    windows = []
    for window in sublime.windows():
        buffers, sheets = [], []
        for view in window.views():
            try:
                sheet = view.sheet()
                if sheet is not None and hasattr(sheet, "is_semi_transient") and sheet.is_semi_transient():
                    continue                                    # single-click preview tab, not a real tab
            except Exception:
                pass
            entry = {"settings": {}}
            name = view.name()
            if name:
                entry["settings"]["name"] = name
            path = view.file_name()
            if path:
                entry["file"] = path
            if view.is_dirty() or not path:
                if view.size() <= MAX_TEXT:
                    entry["contents"] = view.substr(sublime.Region(0, view.size()))
            sheets.append({"buffer": len(buffers)})
            buffers.append(entry)
        windows.append({"buffers": buffers, "groups": [{"sheets": sheets}]})
    return {"windows": windows, "written": int(time.time() * 1000)}


def _write(generation):
    if generation != _generation[0]:
        return                                                  # a newer edit is already queued
    root = _log_dir()
    try:
        os.makedirs(root, exist_ok=True)
        path = os.path.join(root, "live-session.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_snapshot(), f, ensure_ascii=False)
        os.replace(tmp, path)                                   # atomic: the watcher sees one clean rename
    except Exception as e:
        print("[sublime_log_live] {}".format(e))


def _schedule():
    _generation[0] += 1
    g = _generation[0]
    sublime.set_timeout_async(lambda: _write(g), DEBOUNCE_MS)


class SublimeLogLive(sublime_plugin.EventListener):
    def on_modified_async(self, view):
        _schedule()

    on_new_async = on_load_async = on_post_save_async = on_close = on_activated_async = lambda self, view: _schedule()


def plugin_loaded():
    _schedule()
