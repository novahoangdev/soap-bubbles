#!/bin/bash
# final3d.sh gN: the 3D garden's showcase videos from a recording made by tools/rec3d.sh gN, like the 2D pack:
#   1. beat sheet blender/scripts/beats/gN.json (copied from BASE, events from the app log), audio mix
#   2. promo plate (the app's own meadow, defocused) and the 4:3 promo (Blender) → render/promo/soap-bubbles-garden3d-gN.mp4
#   3. the versions reel (VERSIONS="g2:first take g8:… …", each with its film start) → render/final/soap-bubbles-garden3d-versions.mp4
#   4. tools/pack3d.sh: promo, 9:19 screen video, reel, poster / end card / screens / gif into render/showcase-pack/
#   BASE=g29b WORKERS=2 tools/final3d.sh g30   (g29b: the promo layout after art director round 20: phone right, big
#   deep-green act words, a bright warm plate with sky, left-aligned end card)
#   WORKERS=2 tools/final3d.sh g33             (default BASE g33b: the same layout, the long calm cut with chill music
#   and a fourth act word, AGAIN)
set -euo pipefail
cd "$(dirname "$0")/.."
V=${1:?version}; BASE=${BASE:-g34b}
B=blender/scripts/beats/$V.json
F=$(cat render/promo/$V/film_start.txt)
cp blender/scripts/beats/$BASE.json "$B"
python3 -c "import json,sys; b=json.load(open(sys.argv[1])); b['audio']='render/audio/mix_$V.wav'; json.dump(b,open(sys.argv[1],'w'),indent=1)" "$B"
python3 tools/events3d.py render/promo/$V/app.log "$B"
/Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 blender/scripts/mix_clip.py --beats "$B" | tail -1
# promo plate: the home view at 3.2 s (clouds, wood and meadow), defocused, warm and bright like the app
ffmpeg -v error -y -ss "$(python3 -c "print($F+3.2)")" -i render/promo/$V/screen.mp4 -frames:v 1 \
  -vf "scale=1920:-1,crop=1920:1440:0:900,gblur=sigma=20,eq=brightness=0.02:contrast=1.0:saturation=1.1,colorbalance=rh=0.04:bh=-0.03" -q:v 2 \
  blender/textures/promo/garden3d_plate.jpg
WORKERS=${WORKERS:-2} FRAMES=render/promo/frames_$V tools/promo.sh --beats "$B" --screen render/promo/$V/screen.mp4 \
  --film-start "$F" --out render/promo/soap-bubbles-garden3d-$V.mp4 </dev/null | tail -2
rm -rf render/promo/frames_$V
tools/sheet.sh render/promo/soap-bubbles-garden3d-$V.mp4 render/promo/soap-bubbles-garden3d-sheet-$V.jpg "$B" >/dev/null 2>&1 || true
# versions reel: the listed takes side by side from their own app t = 0, the final take's mix
if [ -n "${VERSIONS:-}" ]; then
  ARGS=()
  for spec in $VERSIONS; do
    v=${spec%%:*}; label=${spec#*:}; label=${label//_/ }
    ARGS+=("$v:$(cat render/promo/$v/film_start.txt):$label")
  done
  DUR=13 TW=330 TITLE="Soap Bubbles 3D · how the garden grew" tools/versions_reel.sh \
    render/final/soap-bubbles-garden3d-versions.mp4 render/audio/mix_$V.wav "${ARGS[@]}" </dev/null | tail -1
fi
V=$V tools/pack3d.sh
