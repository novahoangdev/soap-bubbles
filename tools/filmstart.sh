#!/bin/bash
# filmstart.sh: second in a recording (screen.mp4) that shows app t = 0.
# Demo builds hold the clock at t = 0 for ~40 frames with a magenta 9-pt marker in the top-left corner and hide it on the
# exact frame the clock starts; the answer is the first frame without the marker after frames with it.
# Fallback (old recordings without the marker): first bright frame after the dark launch screen.
#   tools/filmstart.sh render/promo/v8/screen.mp4
set -euo pipefail
ffmpeg -v error -i "$1" -t 8 -vf "crop=24:24:2:2,scale=1:1:flags=area,format=rgb24" -f rawvideo - | python3 -c "
import sys
d=sys.stdin.buffer.read()
fr=[d[i:i+3] for i in range(0,len(d)-2,3)]
seen=0
for k,(r,g,b) in enumerate(fr):
    mag = r>180 and g<90 and b>180
    if mag: seen+=1
    elif seen:
        if seen < 10:
            # the app holds the marker ~40 frames; a short run means the first frames reached the screen late (startup
            # display lag) and this time can be early; check an event frame against a good take (v23 was 0.1 s off)
            print(f'WARNING: marker visible for only {seen} frames, film start may be off', file=sys.stderr)
        print(round(k/60.0,4)); sys.exit(0)
sys.exit(1)
" || ffmpeg -v error -i "$1" -t 6 -vf "scale=66:-1,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-" -f null - \
  | python3 -c "
import sys,re
t=None; dark=False
for line in sys.stdin:
    m=re.search(r'pts_time:([0-9.]+)',line)
    if m: t=float(m.group(1)); continue
    m=re.search(r'YAVG=([0-9.]+)',line)
    if m and t is not None:
        y=float(m.group(1))
        if y<22: dark=True
        elif dark and y>60: print(round(t,4)); break
"
