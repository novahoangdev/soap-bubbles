#!/usr/bin/env python3
"""events.py: copy scene event times from a deterministic demo run into a beat sheet (sound effects land on the frame).

  EXPO_PUBLIC_DEMO=1 EXPO_PUBLIC_EVLOG=1 npx expo start …   (run the demo once on the dev sim, Metro log → notes/metro.log)
  python3 tools/events.py notes/metro.log blender/scripts/beats/vN.json

Writes events.pinch / grow / sticks (thinned to ≥ 0.35 s apart) / taps (every pop up to the clip end, except the giant)
/ big_pop (the giant's self-pop: the last "big" pop before the clip end).
"""
import json
import re
import sys

log, beats = sys.argv[1], sys.argv[2]
ev = []
for line in open(log, errors="ignore"):
    m = re.search(r"EVT ([0-9.]+) pops=(\d+) pinch=(\d+) spray=(\d+) stick=(\d+) big=(\d+)", line)
    if m:
        t, pops, pinch, spray, stick, big = float(m[1]), *map(int, m.groups()[1:])
        ev.append((t, pops, pinch, stick, big))
b = json.load(open(beats))
end = float(b.get("app_end", 14.8))
E = b["events"]
pinch = [t for t, _, p, _, _ in ev if p]
if pinch:
    E["pinch"] = round(pinch[0], 3)
    E["grow"] = [E.get("grow", [1.4])[0], round(pinch[0], 3)]
    if len(pinch) > 1 and pinch[1] <= end:
        E["pinch2"] = round(pinch[1], 3)
bigs = [t for t, p, _, _, g in ev if g and t <= end + 0.05]
E["big_pop"] = round(bigs[-1], 3) if bigs else E.get("big_pop")
sticks, last = [], -9.0
for t, _, _, s, _ in ev:
    if s and t <= end and t - last >= 0.35:
        sticks.append(round(t, 3))
        last = t
E["sticks"] = sticks
E["taps"] = [round(t, 3) for t, p, _, _, g in ev if p and t <= end and not (g and abs(t - E["big_pop"]) < 1e-3)]
json.dump(b, open(beats, "w"), indent=1)
print(f"pinch {E.get('pinch')} | big_pop {E['big_pop']} | {len(sticks)} sticks | taps {E['taps']}")
