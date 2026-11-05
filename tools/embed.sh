#!/bin/bash
# embed.sh: copy the built Release app, replace main.jsbundle with the current JS bundle (no native build), install on the sim.
#   UDID=<sim> [TS=0.5] [DEMO=1] tools/embed.sh
#   MODE=3d DEMO3D=1 UDID=<sim> TS=1 tools/embed.sh   (the 3D garden demo)
# Use when only JS/TS/SkSL changed. Native changes (app.json, new modules) need a rebuild with expo run:ios --configuration Release.
set -euo pipefail
cd "$(dirname "$0")/../app"
UDID=${UDID:?set UDID}
SRC=${SRC:-$(ls -d ~/Library/Developer/Xcode/DerivedData/SoapBubbles-*/Build/Products/Release-iphonesimulator/SoapBubbles.app | head -1)}
WORK=${WORK:-$(cd .. && pwd)/render/embed}
rm -rf "$WORK"; mkdir -p "$WORK"; cp -R "$SRC" "$WORK/"
APPD="$WORK/SoapBubbles.app"
EXPO_PUBLIC_MODE=${MODE:-2d} EXPO_PUBLIC_DEMO3D=${DEMO3D:-0} EXPO_PUBLIC_DEMO=${DEMO:-1} EXPO_PUBLIC_TIMESCALE=${TS:-0.5} EXPO_PUBLIC_LOOK=${LOOK:-golden} EXPO_PUBLIC_LOOKSWITCH=${LOOKSWITCH:-0} npx expo export:embed --platform ios --dev false --minify true \
  --entry-file index.ts --bundle-output "$APPD/main.jsbundle" --assets-dest "$APPD" >/dev/null
xcrun simctl install "$UDID" "$APPD"
echo "installed $APPD (MODE=${MODE:-2d} DEMO3D=${DEMO3D:-0} DEMO=${DEMO:-1} TS=${TS:-0.5} LOOK=${LOOK:-golden} LOOKSWITCH=${LOOKSWITCH:-0})"
