#!/bin/bash
# burst.sh: relaunch the app and take N screenshots, one every STEP seconds (quick look at the demo storyboard).
#   N=16 STEP=1 OUT=render/shots/burst tools/burst.sh
set -euo pipefail
cd "$(dirname "$0")/.."
U=${UDID:-$(cat notes/udid.txt)}; N=${N:-16}; STEP=${STEP:-1}; OUT=${OUT:-render/shots/burst}
rm -rf "$OUT"; mkdir -p "$OUT"
xcrun simctl terminate "$U" dev.hoanghoa.soapbubbles 2>/dev/null || true
xcrun simctl launch "$U" dev.hoanghoa.soapbubbles >/dev/null
sleep "${WAIT:-3}"
T0=$(python3 -c "import time; print(time.time())")
for i in $(seq -w 0 $((N-1))); do
  xcrun simctl io "$U" screenshot "$OUT/$i.png" >/dev/null 2>&1
  python3 -c "import time; print(round(time.time()-$T0,2))" > "$OUT/$i.t"
  sleep "$STEP"
done
ffmpeg -v error -y -framerate 1 -pattern_type glob -i "$OUT/*.png" -vf "scale=330:-2,tile=8x$(( (N+7)/8 )):padding=4:color=black" -frames:v 1 "$OUT/sheet.jpg"
echo "$OUT/sheet.jpg"; paste -sd' ' "$OUT"/*.t
