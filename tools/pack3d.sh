#!/bin/bash
# pack3d.sh: the 3D garden's part of the showcase pack (render/showcase-pack/, next to the 2D files):
#   video/soap-bubbles-garden3d-promo-4x3.mp4, -screen-9x19.mp4, -versions.mp4 and images/garden3d/ (poster, end card,
#   screens at key moments, a preview gif of the follow shot).
#   V=g12 tools/pack3d.sh            (needs render/promo/soap-bubbles-garden3d-$V.mp4, render/promo/$V/screen.mp4,
#                                     render/audio/mix_$V.wav, render/final/soap-bubbles-garden3d-versions.mp4)
set -euo pipefail
cd "$(dirname "$0")/.."
V=${V:?set V}
FS=$(cat render/promo/$V/film_start.txt)
B=blender/scripts/beats/$V.json
ev() { python3 -c "import json,sys; b=json.load(open('$B')); print(eval(sys.argv[1]))" "$1"; }
END=$(ev "b['app_end'] + 3.0")
PINCH=$(ev "b['events']['pinch']"); POP=$(ev "b['events']['big_pop']")
P=render/showcase-pack; mkdir -p $P/video $P/images/garden3d/screens
PROMO=render/promo/soap-bubbles-garden3d-$V.mp4
cp "$PROMO" $P/video/soap-bubbles-garden3d-promo-4x3.mp4
END=$END tools/screen_video.sh render/promo/$V/screen.mp4 "$FS" render/audio/mix_$V.wav $P/video/soap-bubbles-garden3d-screen-9x19.mp4
[ -f render/final/soap-bubbles-garden3d-versions.mp4 ] && cp render/final/soap-bubbles-garden3d-versions.mp4 $P/video/soap-bubbles-garden3d-versions.mp4
ffmpeg -v error -y -i "$PROMO" -frames:v 1 -q:v 2 $P/images/garden3d/poster.jpg
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$PROMO")
ffmpeg -v error -y -ss "$(python3 -c "print($D-0.6)")" -i "$PROMO" -frames:v 1 -q:v 2 $P/images/garden3d/end-card.jpg
# preview gif: the camera taking off after the bubble (pinch + 1 s, 3 s), 300 px wide, 20 fps
ffmpeg -v error -y -ss "$(python3 -c "print($FS+$PINCH+1.0)")" -t 3 -i render/promo/$V/screen.mp4 \
  -vf "fps=20,scale=300:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse=dither=sierra2_4a" \
  $P/images/garden3d/preview-follow.gif
APPEND=$(ev "b['app_end']")
for spec in "1.5:01-meadow" "8.5:02-blowing" "$PINCH:03-release" "$(python3 -c "print($PINCH+3.0)"):04-follow" \
            "$(python3 -c "print($POP-0.6)"):05-over-the-meadow" "$(python3 -c "print($POP+0.05)"):06-pop" \
            "$(python3 -c "print($POP+5.0)"):07-home" "$(python3 -c "print($APPEND-2.5)"):08-again"; do
  IFS=: read -r t n <<< "$spec"
  ffmpeg -v error -y -ss "$(python3 -c "print($FS+$t)")" -i render/promo/$V/screen.mp4 -frames:v 1 -vf scale=660:-1 -q:v 3 \
    $P/images/garden3d/screens/$n.jpg
done
ls -R $P/images/garden3d $P/video | head -40
