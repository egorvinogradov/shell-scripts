#!/usr/bin/env python3
"""import_archive — fold an archived (old-format) log into the live log so a tab's history is continuous.

  import_archive.py ARCHIVE_DIR [--log-dir DIR]

ARCHIVE_DIR is an `archive-*` folder the watcher made when it moved an old-format log aside. Stop the watcher first
(launchctl bootout gui/$(id -u)/com.egor.sublime-log) and start it again afterwards (install.sh does both).
Per tab it proves the join: the archived log must end exactly at the text the live log starts from, and every archived
change must undo cleanly. Whatever does not verify is imported as plain log entries (Changes view) without rewriting blame.
The previous live log is copied to pre-import-backup-*/ first, and ARCHIVE_DIR is renamed imported-* so it is never imported twice.
"""
import argparse, glob, importlib.machinery, importlib.util, json, os, shutil, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
_loader = importlib.machinery.SourceFileLoader("watcher", os.path.join(HERE, "sublime_log_watcher.py"))
W = importlib.util.module_from_spec(importlib.util.spec_from_loader("watcher", _loader))
_loader.exec_module(W)


def read_events(days_dir):
    out = []
    for p in sorted(glob.glob(os.path.join(days_dir, "*.js"))):
        for line in open(p, encoding="utf-8"):
            if line.startswith("SUBLOG_EVENT("):
                out.append(json.loads(line[len("SUBLOG_EVENT("):].rstrip().rstrip(";").rstrip(")")))
    return out


def undo(lines, ev):
    """Text before `ev` given the text after it (hunk positions are in the new text); None if it does not match."""
    out = list(lines)
    for h in sorted(ev["h"], key=lambda h: -h["n"]):
        p = h["n"] - 1
        if h.get("cut") or p < 0 or out[p:p + len(h["+"])] != h["+"]:
            return None
        out[p:p + len(h["+"])] = h["-"]
    return out


def redo(lines, blame, ev, e):
    """Apply `ev` forward to (text lines, per-line origin ids); every line it adds gets origin `e`. (None, None) if it does not fit."""
    out, bl, pos = [], [], 0
    for h in sorted(ev["h"], key=lambda h: h["n"]):
        i1 = h["o"] - 1
        i2 = i1 + len(h["-"])
        if h.get("cut") or i1 < pos or lines[i1:i2] != h["-"]:
            return None, None
        out.extend(lines[pos:i1]); bl.extend(blame[pos:i1])
        out.extend(h["+"]); bl.extend([e] * len(h["+"]))
        pos = i2
    out.extend(lines[pos:]); bl.extend(blame[pos:])
    return out, bl


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archive")
    ap.add_argument("--log-dir")
    a = ap.parse_args()
    root = W.log_dir_from_config(a.log_dir)
    arch = os.path.abspath(a.archive)
    if os.path.basename(arch).startswith("imported-"):
        sys.exit("already imported")
    state_path = os.path.join(root, "state.json")
    state = json.load(open(state_path, encoding="utf-8"))
    assert state.get("version") == W.STATE_VERSION, "live state is not in the current format"
    for rec in state["tabs"].values():                              # state stores lines as runs
        rec["lines"] = W.from_runs(rec["lines"]) if rec.get("lines") is not None else None
    arch_tabs = json.load(open(os.path.join(arch, "state.json"), encoding="utf-8")).get("tabs", {})
    arch_events = read_events(os.path.join(arch, "days"))
    new_events = read_events(os.path.join(root, "days"))
    start_t = min((e["t"] for e in arch_events), default=int(time.time() * 1000))
    try:                                                           # tracking began when the first watcher started
        first = open(os.path.join(root, "watcher.log")).readline().split()[0]
        start_t = int(time.mktime(time.strptime(first, "%Y-%m-%dT%H:%M:%S")) * 1000)
    except Exception:
        pass

    backup = os.path.join(root, "pre-import-backup-" + time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(backup)
    for name in ("state.json", "days", "index.js", "current.js"):
        if os.path.exists(os.path.join(root, name)):
            (shutil.copytree if os.path.isdir(os.path.join(root, name)) else shutil.copy2)(os.path.join(root, name), os.path.join(backup, name))

    id_map, used = {}, set()                                       # archived tab id -> live tab id
    plans = []
    for tid, rec in state["tabs"].items():
        if rec.get("text") is None or rec.get("lines") is None:
            continue
        cur = rec["text"].split("\n")
        mine = sorted((e for e in new_events if e["id"] in rec.get("ids", [tid]) and e.get("h") and e.get("e") is not None), key=lambda e: e["e"])
        base = cur
        for ev in reversed(mine):
            base = undo(base, ev) if base is not None else None
        if base is None:
            print(f"skip {rec['title']!r}: live log does not rewind cleanly")
            continue
        aid = tid if tid in arch_tabs else next((k for k, v in arch_tabs.items() if k.startswith("u") and k not in used and v.get("text") is not None
                                                  and v["text"].replace("\r\n", "\n").split("\n") == base), None)
        if aid is None:
            print(f"skip {rec['title']!r}: not in the archive, or its text differs where the logs meet")
            continue
        if arch_tabs[aid].get("text", "").replace("\r\n", "\n").split("\n") != base:
            print(f"skip {rec['title']!r}: archive ends with different text than the live log starts with")
            continue
        used.add(aid)
        id_map[aid] = tid
        evs = [e for e in arch_events if e["id"] == aid and e.get("h")]
        lines, k0 = base, len(evs)
        for i in range(len(evs) - 1, -1, -1):                      # how far back can the archive be undone, step by step
            prev = undo(lines, evs[i])
            if prev is None:
                break
            lines, k0 = prev, i
        plans.append({"tid": tid, "rec": rec, "cur": cur, "evs": evs[k0:], "earliest": lines, "mine": mine})

    # one global, chronological numbering for imported entries: negative, so they sort before every live entry (those start at 1)
    all_used = sorted(((ev["t"], n, p["tid"], ev) for p in plans for n, ev in enumerate(p["evs"])), key=lambda x: (x[0], x[1]))
    e_of = {id(ev): -(len(all_used) - i) for i, (_, _, _, ev) in enumerate(all_used)}

    joined = []
    for p in plans:
        rec = p["rec"]
        e_base = state["next_e"]
        state["next_e"] += 1
        text, blame = p["earliest"], [e_base] * len(p["earliest"])
        meta = {str(e_base): {"t": start_t, "k": "baseline", "unknown": True}}
        ok = True
        for ev in p["evs"]:
            text, blame = redo(text, blame, ev, e_of[id(ev)])
            if text is None:
                ok = False
                break
            meta[str(e_of[id(ev)])] = {"t": ev["t"], "k": "new" if ev["k"] == "new" else "edit"}
        for ev in p["mine"] if ok else []:
            text, blame = redo(text, blame, ev, ev["e"])
            if text is None:
                ok = False
                break
            meta[str(ev["e"])] = rec["ev"].get(str(ev["e"]), {"t": ev["t"], "k": "edit"})
        if not ok or text != p["cur"]:
            print(f"keep {rec['title']!r}: replay did not land on the current text; its history is added to the log but blame is unchanged")
            continue
        joined.append(p)
        rec["lines"], rec["ev"] = blame, {**rec.get("ev", {}), **meta}
        rec["ids"] = list(dict.fromkeys(rec.get("ids", [p["tid"]]) + [k for k, v in id_map.items() if v == p["tid"]]))
        print(f"joined {rec['title']!r}: {len(p['evs'])} archived changes, blame rebuilt for {len(p['cur'])} lines")

    joined_ids = {id(ev) for p in joined for ev in p["evs"]}
    log = W.Log(root)
    imported = 0
    for ev in arch_events:                                         # every archived entry goes into the log (Changes view), mapped to its live tab
        new = dict(ev)
        if ev["id"] in id_map:
            new["id"] = id_map[ev["id"]]
        elif ev["id"].startswith("u"):
            new["id"] = "arch:" + os.path.basename(arch) + ":" + ev["id"]
        if id(ev) in joined_ids:
            new["e"] = e_of[id(ev)]
        log.append(new)
        imported += 1
    for rec in state["tabs"].values():
        rec["lines"] = W.to_runs(rec["lines"]) if rec.get("lines") is not None else None
    W.atomic_write(state_path, json.dumps(state, ensure_ascii=False))
    os.rename(arch, os.path.join(os.path.dirname(arch), "imported-" + os.path.basename(arch)))
    print(f"imported {imported} archived log entries; backup of the previous live log: {backup}")


if __name__ == "__main__":
    main()
