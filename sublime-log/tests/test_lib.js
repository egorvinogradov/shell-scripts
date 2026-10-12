// node test_lib.js FIXTURE.json  — viewer_lib.js must rebuild every earlier version from the log, exactly.
const assert = require("assert");
const L = require("../viewer_lib.js");
const fixtures = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
let checks = 0;
for (const f of fixtures) {
  const evs = L.tabEvents(f.tab, f.events);
  assert.strictEqual(evs.length, f.versions.length - 1);                     // one entry per version after the first
  for (let idx = 0; idx <= evs.length; idx++) {
    const r = L.linesAt(f.current, evs, idx);
    assert.ok(r.ok, "history should be rebuildable");
    assert.deepStrictEqual(r.lines, f.versions[idx], `version ${idx}`);
    checks++;
  }
}
// tampering is detected, never silently wrong
const f = fixtures[0], evs = L.tabEvents(f.tab, f.events);
const bad = f.current.slice(); bad[bad.length - 1] = "someone edited this outside the log";
assert.strictEqual(L.linesAt(bad, evs, 0).ok, false);                       // current text no longer matches the newest entry
const cut = JSON.parse(JSON.stringify(evs)); cut[cut.length - 1].h[0].cut = true;
assert.strictEqual(L.linesAt(f.current, cut, 0).ok, false);
// alias map / segIndex / relTime
assert.deepStrictEqual(L.aliasMap([{id: "f:/x", ids: ["u3", "f:/x"]}]), {u3: "f:/x", "f:/x": "f:/x"});
const si = L.segIndex({segs: [[1, 2, 5], [3, 1, 9]]});
assert.strictEqual(si[2].e, 5); assert.strictEqual(si[3].e, 9); assert.strictEqual(si[3].start, 3);
assert.strictEqual(L.relTime(0, 30000), "just now"); assert.strictEqual(L.relTime(0, 120000), "2 min ago"); assert.strictEqual(L.relTime(0, 86400000 * 3), "3 d ago");
console.log(`ok: ${fixtures.length} tabs, ${checks} versions rebuilt exactly`);
