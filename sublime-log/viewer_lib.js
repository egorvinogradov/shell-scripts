// Pure helpers for viewer.html (no DOM) so they can be tested with node. Browser: window.SublogLib.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.SublogLib = factory();
})(this, function () {
  "use strict";

  // Undo one log entry: `lines` is the text right after it, the result is the text right before it.
  // Hunks carry 1-based start lines in the new text (`n`), the lines added (`+`) and the lines they replaced (`-`).
  // Returns null if the text no longer matches what the entry says it produced (file changed while not tracked, long cut block).
  function revertEvent(lines, ev) {
    const hunks = (ev.h || []).slice().sort((a, b) => b.n - a.n);   // last hunk first: earlier positions stay valid
    const out = lines.slice();
    for (const h of hunks) {
      if (h.cut) return null;
      const p = h.n - 1, add = h["+"], del = h["-"];
      if (p < 0 || p + add.length > out.length) return null;
      for (let i = 0; i < add.length; i++) if (out[p + i] !== add[i]) return null;
      out.splice(p, add.length, ...del);
    }
    return out;
  }

  // Log entries of one tab (a tab keeps all its ids after Save As), oldest first. Only entries that change text.
  function tabEvents(tab, events) {
    const ids = new Set(tab.ids || [tab.id]);
    return events.filter(e => ids.has(e.id) && e.h && e.h.length && e.e != null).sort((a, b) => a.e - b.e);
  }

  // Text after the first `idx` entries (idx 0 = before any logged change), rebuilt backwards from the current text.
  function linesAt(currentLines, evs, idx) {
    let lines = currentLines.slice();
    for (let i = evs.length - 1; i >= idx; i--) {
      const r = revertEvent(lines, evs[i]);
      if (!r) return {ok: false, lines: null, failedAt: i};
      lines = r;
    }
    return {ok: true, lines};
  }

  // line number (1-based) -> segment {start, count, e}
  function segIndex(tab) {
    const map = [];
    for (const [start, count, e] of tab.segs) for (let i = 0; i < count; i++) map[start + i] = {start, count, e};
    return map;
  }

  // old tab ids (before Save As) -> the id the tab has now
  function aliasMap(tabs) {
    const m = {};
    for (const t of tabs || []) for (const id of t.ids || []) m[id] = t.id;
    return m;
  }

  function relTime(ms, now) {
    const s = Math.max(0, Math.round((now - ms) / 1000));
    if (s < 45) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    if (s < 86400 * 45) return Math.round(s / 86400) + " d ago";
    return Math.round(s / 86400 / 30) + " mo ago";
  }

  return {revertEvent, tabEvents, linesAt, segIndex, aliasMap, relTime};
});
