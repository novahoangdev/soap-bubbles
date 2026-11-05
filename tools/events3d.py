#!/usr/bin/env python3
"""events3d.py: beat sheet events for a 3D-garden recording from the app's own event log (sound on the frame).

  python3 tools/events3d.py render/promo/gN/app.log blender/scripts/beats/gN.json

The demo app (EXPO_PUBLIC_DEMO3D=1) logs `EVT3 <scene s> pops=… big=… release=… spray=… heroBig=…` whenever bubbles pop,
leave the wand or spray off a puff, and `EVT3HERO <s>` when the camera gives up following and pops it (else its own pop, the first big=1 line, is used). tools/rec3d.sh captures them.
Writes into the beat sheet: breath (the scripted keys of app/src/garden3d/demo3d.ts), puff_split / breath2_from (the
puffs come first in 3D, then the long breath), grow / pinch (the big bubble's release), pinch2 (the next release),
puffs (sprays), taps (small pops, thinned ≥ 0.14 s apart, up to app_end), big_pop (the followed bubble) and
app_end = big_pop + 0.9 s (cut to the end card just after it).
Chill beat sheets (music.style "chill", the long calm cut): the clip runs on past the pop, home again, through the second
round of puffs: app_end = the last scripted breath + 4.6 s; the sharp puffs are listed as puff_windows (the long breath
sounds soft, the puffs brighter, wherever they are); an act word AGAIN (if the sheet has one) runs from the second round
to the card, POP until then.
"""
import json
import re
import sys

log, beats = sys.argv[1], sys.argv[2]
ev, hero = [], None
for line in open(log, errors="ignore"):
    m = re.search(r"EVT3 ([0-9.]+) pops=(\d+) big=(\d+) release=(\d+) spray=(\d+) heroBig=(\d)", line)
    if m:
        ev.append((float(m[1]), *map(int, m.groups()[1:])))
    m = re.search(r"EVT3HERO ([0-9.]+)", line)
    if m and hero is None:
        hero = float(m[1])
if hero is None:
    # the followed bubble popped by itself (age / the ground / a flower) before the camera gave up on it
    hero = next((t for t, p, g, r, sp, hb in ev if g and p), None)
if not ev or hero is None:
    sys.exit("no EVT3 lines / no big pop in the log")
src = open("app/src/garden3d/demo3d.ts").read()
keys = [[float(a), float(b)] for a, b in re.findall(r"\[([0-9.]+), ([0-9.]+)\]", src.split("const KEYS")[1].split("];")[0])]
b = json.load(open(beats))
chill = b.get("music", {}).get("style") in ("chill", "lofi")
last_breath = max(t for t, v in keys if v > 0)
end = round(max(hero + 0.9, last_breath + 4.6) if chill else hero + 0.9, 3)
E = b.setdefault("events", {})
E["breath"] = keys
E["puff_split"] = 0.0
E["breath2_from"] = 2.2
# the sharp puffs: runs of keys above 0.6
wins, w0 = [], None
for (t, v), (t2, v2) in zip(keys, keys[1:]):
    if v2 > 0.6 and w0 is None:
        w0 = t
    if v2 <= 0.6 and w0 is not None and v <= 0.6:
        wins.append([round(w0, 3), round(t, 3)])
        w0 = None
    elif v2 == 0 and w0 is not None:
        wins.append([round(w0, 3), round(t2, 3)])
        w0 = None
E["puff_windows"] = wins
rel = [t for t, _, _, r, _, hb in ev if r]
big_rel = [t for t, _, _, r, _, hb in ev if r and hb]
E["pinch"] = round(big_rel[0] if big_rel else rel[0], 3)
E["grow"] = [2.4, E["pinch"]]
later = [t for t in rel if t > E["pinch"] + 0.3 and t <= end]
if later:
    E["pinch2"] = round(later[0], 3)
else:
    E.pop("pinch2", None)
E["puffs"] = [round(t, 3) for t, _, _, _, s, _ in ev if s and t <= end]
taps, last = [], -1.0
for t, p, g, _, _, _ in ev:
    # (chill / lofi: puffs now throw a few dozen bubbles; a soft pop every ~0.4 s at most, not a rattle)
    if p and not g and t <= end and abs(t - hero) > 0.1 and t - last >= (0.4 if chill else 0.14):
        taps.append(round(t, 3))
        last = t
E["taps"] = taps
E["big_pop"] = round(hero, 3)
E["sticks"] = []
E["drips"] = []
b["app_end"] = end
# the act words follow the events: BLOW until the big bubble leaves the wand, FOLLOW until it pops, POP to the card
for w in b.get("words", []):
    if w[0] == "BLOW":
        w[2] = E["pinch"]
    elif w[0] == "FOLLOW":
        w[1], w[2] = E["pinch"], E["big_pop"]
    elif w[0] == "POP":
        w[1] = E["big_pop"]
        again = next((a for a, _ in wins if a > hero), None)
        if any(x[0] == "AGAIN" for x in b["words"]) and again is not None:
            w[2] = round(again - 0.4, 3)
    elif w[0] == "AGAIN":
        w[1] = round(next((a for a, _ in wins if a > hero), end - 3.0) - 0.4, 3)
b["sheet"] = [0.05, 1.6, 4.4, round(E["pinch"] + 2.5, 2), round(E["big_pop"] - 0.6, 2), round(end + 2.0, 2)]
if chill:
    b["sheet"] = [0.05, 8.5, round(E["pinch"] + 3.0, 2), round(E["big_pop"] - 0.6, 2), round(end - 3.0, 2), round(end + 2.0, 2)]
json.dump(b, open(beats, "w"), indent=1)
print(f"pinch {E['pinch']} puffs {len(E['puffs'])} taps {len(taps)} big_pop {hero} app_end {end}")
