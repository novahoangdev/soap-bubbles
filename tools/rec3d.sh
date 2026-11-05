#!/bin/bash
# rec3d.sh vN: record the 3D garden demo (EXPO_PUBLIC_MODE=3d, DEMO3D=1) on the Rec sim into render/promo/<vN>/screen.mp4.
# SECS (scene seconds, default 50: the long calm demo of app/src/garden3d/demo3d.ts runs ~45 s).
# Stops the dev Metro and the dev-sim app first: a SIGSTOPped WebGPU app on the other simulator stalls this one's Metal
# presentation (the recording froze on its first frame).
set -euo pipefail
cd "$(dirname "$0")/.."
V=${1:?version name}
U=$(cat notes/udid_rec.txt); D=$(cat notes/udid.txt)
pkill -f "expo start --port" || true
xcrun simctl terminate "$D" dev.hoanghoa.soapbubbles 2>/dev/null || true
MODE=3d DEMO3D=1 UDID=$U TS=${TS:-0.5} tools/embed.sh | tail -1
mkdir -p render/promo/$V
# the app's event log (EVT3 lines: scene seconds of pops / releases / sprays) for the promo audio
xcrun simctl spawn "$U" log stream --level info --style compact --predicate 'category == "javascript"' > render/promo/$V/app.log 2>&1 & LOGP=$!
TS=${TS:-0.5} SECS=${SECS:-50} PRE=${PRE:-8} UDID=$U OUT=render/promo/$V tools/rec.sh | tail -2
kill $LOGP 2>/dev/null || true
echo "events logged: $(grep -c EVT3 render/promo/$V/app.log || true)"
python3 tools/filmstart3d.py render/promo/$V/screen.mp4 | tee render/promo/$V/film_start.txt
