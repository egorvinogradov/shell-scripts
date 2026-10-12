"""Write a JSON fixture (current text, log entries, expected text of every version) for test_lib.js. Usage: make_fixture.py OUT.json"""
import json, random, sys
from test_watcher import Env, T0, MIN, OLD

rnd = random.Random(11)
out = []
for trial in range(30):
    e = Env()
    try:
        a = e.disk("a.txt", "a\n", OLD)
        e.step(T0, [("f", a, None)])
        text = "seed\nline two"
        versions = [""]                               # version 0: before the first logged change = empty untitled tab
        t = T0 + 10 * MIN
        e.step(t, [("f", a, None), ("u", text)])
        versions.append(text)
        for _ in range(rnd.randint(2, 20)):
            lines = text.split("\n")
            for _ in range(rnd.randint(1, 4)):
                op = rnd.choice(["ins", "del", "mod", "dup"])
                i = rnd.randrange(len(lines))
                if op == "ins":
                    lines.insert(i, f"n{rnd.randint(0, 99)}")
                elif op == "del" and len(lines) > 1:
                    del lines[i]
                elif op == "mod":
                    lines[i] += f" m{rnd.randint(0, 9)}"
                else:
                    lines.insert(i, lines[i])
            new = "\n".join(lines)
            if new == text:
                continue
            text = new
            t += 10 * MIN
            e.step(t, [("f", a, None), ("u", text)])
            versions.append(text)
        events = [x for x in e.events() if x.get("h")]
        out.append({"current": text.split("\n"), "events": events, "versions": [v.split("\n") for v in versions],
                    "tab": e.current()[1]})
    finally:
        e.close()
json.dump(out, open(sys.argv[1], "w"))
