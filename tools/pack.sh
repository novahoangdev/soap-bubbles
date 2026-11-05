#!/bin/bash
# pack.sh: showcase pack like ../showcase/neon-sign (video/ + images/), written to render/showcase-pack/ (not into the shared
# showcase repo: copy it there yourself).
#   V=v35 FS=<film start> tools/pack.sh
# Needs: render/promo/soap-bubbles-demo-$V.mp4 (promo), render/promo/$V/screen.mp4 + render/audio/mix_$V.wav (screen video),
# render/final/soap-bubbles-versions.mp4 (progress reel, tools/versions_reel.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
V=${V:?set V}; FS=${FS:?set FS}
P=render/showcase-pack; mkdir -p $P/video $P/images/screens
PROMO=render/promo/soap-bubbles-demo-$V.mp4
cp "$PROMO" $P/video/soap-bubbles-promo-4x3.mp4
tools/screen_video.sh render/promo/$V/screen.mp4 "$FS" render/audio/mix_$V.wav $P/video/soap-bubbles-screen-9x19.mp4
[ -f render/final/soap-bubbles-versions.mp4 ] && cp render/final/soap-bubbles-versions.mp4 $P/video/soap-bubbles-versions.mp4
# poster = promo frame 1, end card = last second, contact sheet from sheet.sh
ffmpeg -v error -y -i "$PROMO" -frames:v 1 -q:v 2 $P/images/poster.jpg
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$PROMO")
ffmpeg -v error -y -ss "$(python3 -c "print($D-0.6)")" -i "$PROMO" -frames:v 1 -q:v 2 $P/images/end-card.jpg
cp render/promo/soap-bubbles-sheet-$V.jpg $P/images/contact-sheet.jpg
# preview gif: the giant's black film and pop (app 11.6–13.2 s), 360 px wide, 20 fps
ffmpeg -v error -y -ss "$(python3 -c "print($FS+11.6)")" -t 1.6 -i render/promo/$V/screen.mp4 \
  -vf "fps=20,scale=360:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse=dither=sierra2_4a" \
  $P/images/preview-giant-pop.gif
# screens: key moments (app time → name)
for spec in "0.05:01-opening-cluster" "2.4:02-long-breath" "4.3:03-puffs" "7.6:04-stuck-together" "8.483:05-tap-pop" \
            "11.9:06-black-film" "12.79:07-giant-tears" "13.4:08-after"; do
  IFS=: read -r t n <<< "$spec"
  ffmpeg -v error -y -ss "$(python3 -c "print($FS+$t)")" -i render/promo/$V/screen.mp4 -frames:v 1 -vf scale=660:-1 -q:v 3 \
    $P/images/screens/$n.jpg
done
ls -R $P | head -40
