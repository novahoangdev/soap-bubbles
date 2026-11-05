#!/bin/bash
# night_env.sh: post-process the night environment map for the app (run after LOOK=night tools/build.sh).
#  1. bloom the fairy-light bulbs (1–3 px points would alias away in bubble reflections) → soft glows
#  2. add a broad, soft warm "porch window" behind the camera (u = 0/1, just above the horizon): what a night photographer
#     uses to make soap films show their colours; the bubble fronts reflect it, the backs reflect the lights
#  3. (v18) soften the whole map first (sigma BLUR, default 10 px, 16 px vertically): sharp strings of bulbs mirrored on a sphere read as a
#     dotted "wireframe globe" and the horizon as a hard seam; a slightly defocused world reads as a real photo
# Input: blender/textures/env/night_env_sharp.jpg (the raw Blender env) → app/assets/scene/night/env.jpg
set -euo pipefail
cd "$(dirname "$0")/.."
SRC=blender/textures/env/night_env_sharp.jpg
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
ffmpeg -v error -y -f lavfi -i "color=c=black:s=2048x1024" -frames:v 1 -vf "format=gbrp,geq=\
r='255*0.62*exp(-(pow(min(X,W-X)/(0.15*W),2)+pow((Y-0.45*H)/(0.2*H),4)))+24*exp(-pow((Y-0.15*H)/(0.25*H),2))':\
g='228*0.62*exp(-(pow(min(X,W-X)/(0.15*W),2)+pow((Y-0.45*H)/(0.2*H),4)))+27*exp(-pow((Y-0.15*H)/(0.25*H),2))':\
b='185*0.62*exp(-(pow(min(X,W-X)/(0.15*W),2)+pow((Y-0.45*H)/(0.2*H),4)))+42*exp(-pow((Y-0.15*H)/(0.25*H),2))'" "$TMP/porch.png"
ffmpeg -v error -y -i "$SRC" -i "$TMP/porch.png" -filter_complex "[0]format=gbrp,gblur=sigma=${BLUR:-10}:sigmaV=${BLURV:-16},split=3[a][b][c];\
[b]lutrgb=r='if(gt(val,70),val*1.6,0)':g='if(gt(val,62),val*1.5,0)':b='if(gt(val,62),val*1.4,0)',gblur=sigma=8[g1];\
[c]lutrgb=r='if(gt(val,95),val,0)':g='if(gt(val,85),val,0)':b='if(gt(val,85),val,0)',gblur=sigma=18[g2];\
[a][g2]blend=all_mode=screen[ab];[ab][g1]blend=all_mode=screen:all_opacity=0.7[ag];[1]format=gbrp[p];\
[ag][p]blend=all_mode=screen,format=yuv444p" -q:v 3 app/assets/scene/night/env.jpg
ls -lh app/assets/scene/night/env.jpg
