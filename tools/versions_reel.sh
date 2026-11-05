#!/bin/bash
# versions_reel.sh: progress reel, several recorded versions of the demo playing side by side from app t = 0 (1920×1080,
# 60 fps, the latest mix as soundtrack). Like the goku-vs-frieza "versions" video. Labels are drawn by tools/text_png.mjs
# (Skia/CanvasKit), since this ffmpeg build has no drawtext.
#   tools/versions_reel.sh OUT.mp4 AUDIO.wav "v3:1.4:first take" "v9:1.2333:golden hour" ...   (version:film start:label)
# DUR (default 13.6) seconds of each, from its own app t = 0.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=$1; AUDIO=$2; shift 2
DUR=${DUR:-13.6}
TITLE=${TITLE:-Soap Bubbles · how it got here}
N=$#
TW=${TW:-290}; TH=$(( TW * 2868 / 1320 / 2 * 2 )); GAP=$(( (1920 - N * TW) / (N + 1) )); TY=${TY:-150}; LY=$(( TY + TH + 18 ))
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
node tools/text_png.mjs "$TITLE" 44 "#f2eadf" "$TMP/title.png" >/dev/null
IN=(); F="color=c=0x0b0d16:s=1920x1080:r=60:d=$DUR[bg0];"
k=0; L=()
for spec in "$@"; do
  IFS=: read -r v fs label <<< "$spec"
  IN+=(-ss "$fs" -t "$DUR" -i "render/promo/$v/screen.mp4")
  # NAMES=1: the label is the headline and the version the small print (looks reel)
  if [ "${NAMES:-0}" = 1 ]; then big=$label; small=$v; else big=$v; small=$label; fi
  node tools/text_png.mjs "$big" 34 "#ffffff" "$TMP/v$k.png" >/dev/null
  node tools/text_png.mjs "$small" 22 "#b9b4cc" "$TMP/l$k.png" >/dev/null
  L+=("$TMP/v$k.png" "$TMP/l$k.png")
  k=$((k + 1))
done
# inputs: N videos, title, 2N labels, audio
IN+=(-loop 1 -i "$TMP/title.png")
for f in "${L[@]}"; do IN+=(-loop 1 -i "$f"); done
IN+=(-i "$AUDIO")
TI=$N; AI=$((N + 1 + 2 * N))
F+="[bg0][$TI:v]overlay=(W-w)/2:52[bg1];"
for ((k = 0; k < N; k++)); do
  x=$(( GAP + k * (TW + GAP) ))
  vi=$((N + 1 + 2 * k)); li=$((vi + 1))
  F+="[$k:v]scale=$TW:$TH:flags=lanczos,setsar=1,fps=60,format=yuv420p[t$k];"
  F+="[bg$((k + 1))][t$k]overlay=$x:$TY[o$k];"
  F+="[o$k][$vi:v]overlay=$x+($TW-w)/2:$LY[p$k];"
  F+="[p$k][$li:v]overlay=$x+($TW-w)/2:$((LY + 46))[bg$((k + 2))];"
done
F+="[$AI:a]atrim=0:$DUR,afade=t=out:st=$(python3 -c "print($DUR-0.6)"):d=0.6[a]"
ffmpeg -v error -y "${IN[@]}" -filter_complex "$F" -map "[bg$((N + 1))]" -map "[a]" -t "$DUR" \
  -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -r 60 -c:a aac -b:a 192k -movflags +faststart "$OUT"
ls -lh "$OUT"
