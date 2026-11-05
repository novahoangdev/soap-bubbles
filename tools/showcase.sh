#!/usr/bin/env bash
# Save a showcase version of the demo to compare versions / collect feedback later (like ../neon-sign/tools/showcase.sh).
#   tools/showcase.sh v10 "short note"                         embed current JS (DEMO, TS 0.5), record on the Rec sim, save
#   SCREEN=render/promo/v9/screen.mp4 tools/showcase.sh v9 "…"  reuse an existing recording instead
# Output in render/showcase/<v>/:
#   screen.mp4   1320×2868 60 fps from app t = 0 (corner sync marker)       preview.mp4  540 px, 30 fps, with the clip mix if found
#   sheet.jpg    16 evenly spaced frames      src.tgz  copy of app/src      NOTES.md  the note + timings
set -eo pipefail
cd "$(dirname "$0")/.."
V=${1:?version name}; NOTE=${2:-}
OUT=render/showcase/$V; mkdir -p "$OUT"
if [[ -z "${SCREEN:-}" ]]; then
  R=${UDID:-$(cat notes/udid_rec.txt)}
  UDID=$R DEMO=1 TS=0.5 tools/embed.sh | tail -1
  UDID=$R TS=0.5 SECS=${SECS:-19} OUT="$OUT/rec" tools/rec.sh | tail -2
  SCREEN=$OUT/rec/screen.mp4
fi
FS=$(tools/filmstart.sh "$SCREEN")
ffmpeg -v error -y -ss "$FS" -i "$SCREEN" -c:v libx264 -crf 14 -preset slow -pix_fmt yuv420p -an "$OUT/screen.mp4"
MIX=${MIX:-$(ls -t render/audio/mix_v*.wav 2>/dev/null | head -1)}
if [[ -f "$MIX" ]]; then
  ffmpeg -v error -y -i "$OUT/screen.mp4" -i "$MIX" -vf "scale=540:-2,fps=30" -c:v libx264 -crf 22 -c:a aac -b:a 160k -shortest "$OUT/preview.mp4"
else
  ffmpeg -v error -y -i "$OUT/screen.mp4" -vf "scale=540:-2,fps=30" -c:v libx264 -crf 22 "$OUT/preview.mp4"
fi
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT/screen.mp4")
ffmpeg -v error -y -i "$OUT/screen.mp4" -vf "fps=16/$D,scale=220:-2,tile=8x2:padding=4:color=black" -frames:v 1 "$OUT/sheet.jpg"
tar -czf "$OUT/src.tgz" -C app src
printf '# Showcase %s\n\n%s\n\n- recorded from %s (film start %ss), %.1f s\n- preview audio: %s\n' "$V" "$NOTE" "$SCREEN" "$FS" "$D" "${MIX:-none}" > "$OUT/NOTES.md"
echo "→ $OUT"
