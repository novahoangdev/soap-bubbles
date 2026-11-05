#!/bin/bash
# screen_video.sh: the raw app recording as a full-screen portrait video with the clip soundtrack (720×1564, 60 fps), like
# neon-sign-screen-9x19.mp4: from app t = 0 to app t = END (default 14.6), audio = the version's mix from app t = 0.
#   tools/screen_video.sh render/promo/vN/screen.mp4 <film start> render/audio/mix_vN.wav OUT.mp4
set -euo pipefail
cd "$(dirname "$0")/.."
SCREEN=$1; FS=$2; AUDIO=$3; OUT=$4
END=${END:-14.6}
ffmpeg -v error -y -ss "$FS" -t "$END" -i "$SCREEN" -i "$AUDIO" -filter_complex \
  "[0:v]scale=720:1564:flags=lanczos,setsar=1,fps=60,format=yuv420p,fade=t=out:st=$(python3 -c "print($END-0.5)"):d=0.5[v];\
[1:a]atrim=0:$END,afade=t=out:st=$(python3 -c "print($END-0.8)"):d=0.8[a]" \
  -map "[v]" -map "[a]" -t "$END" -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p -r 60 -c:a aac -b:a 192k \
  -movflags +faststart "$OUT"
ls -lh "$OUT"
ffmpeg -hide_banner -nostats -i "$OUT" -af ebur128=peak=true -f null - 2>&1 | awk '/Summary:/{s=1} s && /I:|Peak:/{printf "%s ", $0} END{print ""}' | tr -s ' '
