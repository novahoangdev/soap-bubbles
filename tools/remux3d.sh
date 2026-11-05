#!/bin/bash
# remux3d.sh V AV: the 3D garden take V's picture (promo + 9:19 screen video) with another soundtrack, without
# re-rendering: blender/scripts/beats/$AV.json (a copy of V's sheet with its own "music" and "audio") is mixed with
# mix_clip.py, then muxed onto render/promo/soap-bubbles-garden3d-$V.mp4 (video copied) and V's screen recording.
#   tools/remux3d.sh g35 g35p   → render/promo/soap-bubbles-garden3d-g35p.mp4, render/final/soap-bubbles-garden3d-screen-g35p.mp4
set -euo pipefail
cd "$(dirname "$0")/.."
V=${1:?take}; AV=${2:?audio version}
B=blender/scripts/beats/$AV.json
ev() { python3 -c "import json,sys; b=json.load(open('$B')); print(eval(sys.argv[1]))" "$1"; }
WAV=$(ev "b['audio']")
/Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 blender/scripts/mix_clip.py --beats "$B" | tail -1
SRC=render/promo/soap-bubbles-garden3d-$V.mp4
OUT=render/promo/soap-bubbles-garden3d-$AV.mp4
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$SRC")
S=$(ev "b.get('app_start', 0.2)")
AF=$(python3 -c "
s, d = $S, $D
head = f'atrim=start={s},asetpts=PTS-STARTPTS' if s >= 0 else f'adelay={round(-s*1000)}:all=1'
print(f'{head},apad,atrim=end={d},afade=t=out:st={round(d - 0.4, 2)}:d=0.4')")
ffmpeg -v error -y -i "$SRC" -i "$WAV" -filter_complex "[1:a]$AF[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -ar 48000 \
  -movflags +faststart -t "$D" "$OUT"
mkdir -p render/final
END=$(ev "b['app_end'] + 3.0") tools/screen_video.sh render/promo/$V/screen.mp4 "$(cat render/promo/$V/film_start.txt)" "$WAV" \
  render/final/soap-bubbles-garden3d-screen-$AV.mp4
ls -lh "$OUT" render/final/soap-bubbles-garden3d-screen-$AV.mp4
