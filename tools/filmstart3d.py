#!/usr/bin/env python3
"""filmstart3d.py: second in a 3D-garden recording that shows app t = 0 (scene clock start).

  python3 tools/filmstart3d.py render/promo/gN/screen.mp4      → prints e.g. 1.4167

The 3D garden opens on a flat haze veil (#e6ecdc) that starts a linear fade on the scene clock's first frame
(Garden3D.tsx, GARDEN.onStart). The Dynamic Island and the home bar are cropped out. The first frame after the flat veil whose picture differs from it is app t = 0 (+ ~1 frame:
the native fade starts on the next UI frame, so one frame is subtracted).
"""
import subprocess
import sys

video = sys.argv[1]
N = 32 * 32
raw = subprocess.run(["ffmpeg", "-v", "error", "-t", "8", "-i", video, "-vf", "crop=1100:2200:110:400,scale=32:32:flags=area,format=gray",
                      "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
fr = [raw[i:i + N] for i in range(0, len(raw) - N + 1, N)]
spread = [max(f) - min(f) for f in fr]
mean = [sum(f) / N for f in fr]
# the veil: bright (mean > 200) and flat (spread < 6) frames
veil = [k for k in range(len(fr)) if mean[k] > 200 and spread[k] < 6]
if not veil:
    print("0.0")
    sys.exit("no veil found")
k = veil[0]
while k + 1 < len(fr) and spread[k + 1] < 6:
    k += 1
start = max(0, k + 1 - 1)  # first non-flat frame, minus the one-frame lag of the native fade
print(f"{start / 60:.4f}")
