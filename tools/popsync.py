#!/usr/bin/env python3
"""popsync.py: film start of a recording from the giant's pop (cross-check for tools/filmstart.sh).

  python3 tools/popsync.py render/promo/vN/screen.mp4 blender/scripts/beats/vN.json [marker_film_start]

The giant's self-pop is the largest frame-to-frame change in the middle of the picture. Its frame minus the beat sheet's
events.big_pop (app time) minus the render lag (POP_LAG: the hole needs ~2 frames to clear most of the bubble; measured on
v28, whose marker sync was confirmed by the pops) is the second of app t = 0. When a marker start is given and the two
disagree by more than 3 frames, it warns (the pop frame itself is only good to ±2 frames: trust a marker
that ends cleanly, catch the gross misses): the marker can end late after startup jank on the simulator (v29: 0.35 s).
"""
import json
import subprocess
import sys

POP_LAG = 0.017   # v31+: a pop starts with the hole already open (0.15 rad); v26–v30 needed 0.033
video, beats = sys.argv[1], sys.argv[2]
big = float(json.load(open(beats))["events"]["big_pop"])
N = 16 * 16
raw = subprocess.run(
    ["ffmpeg", "-v", "error", "-i", video, "-vf", "crop=1100:1000:110:1050,scale=16:16:flags=area,format=gray",
     "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
fr = [raw[i:i + N] for i in range(0, len(raw) - N + 1, N)]
best, bk = -1.0, 0
for k in range(1, len(fr)):
    t = k / 60.0
    if not (big - 0.5 < t - 1.0 < big + 2.5):   # film start is ~1–2 s: only look near the expected pop
        continue
    d = sum(abs(a - b) for a, b in zip(fr[k], fr[k - 1])) / N
    if d > best:
        best, bk = d, k
fs = round(bk / 60.0 - big - POP_LAG, 4)
print(fs)
if len(sys.argv) > 3 and abs(float(sys.argv[3]) - fs) > 0.05:
    print(f"WARNING: marker film start {sys.argv[3]} disagrees with the pop sync {fs} (peak frame {bk}, diff {best:.1f})",
          file=sys.stderr)
