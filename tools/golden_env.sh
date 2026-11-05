#!/bin/bash
# golden_env.sh: post-process the golden-hour environment map for the app (run after tools/build.sh).
#  1. soften the whole map (sigma BLUR, default 6 px; 10 px vertically): a sharp tree row mirrored on every bubble reads as
#     the same stamped strip of trees; a slightly defocused world reads like a photo of real bubbles
#  2. below the horizon, take saturation and level out of the lawn: the bubble bottoms mirror the ground, and a bright
#     saturated green turns them muddy olive; a darker, quieter ground lets the film colours show (night look: night_env.sh)
# Input: blender/textures/env/golden_env_sharp.jpg (the raw Blender env) → app/assets/scene/env.jpg
set -euo pipefail
cd "$(dirname "$0")/.."
SRC=blender/textures/env/golden_env_sharp.jpg
ffmpeg -v error -y -i "$SRC" -filter_complex "[0]format=gbrp,gblur=sigma=${BLUR:-6}:sigmaV=${BLURV:-10},split=2[a][b];\
[b]hue=s=${GROUND_SAT:-0.45},eq=brightness=-0.05:gamma=1.15,format=gbrp[g];\
color=c=black:s=2048x1024,format=gray,geq=lum='255*clip((Y-0.505*H)/(0.06*H),0,1)'[m];\
[a][g][m]maskedmerge,format=yuv444p" -frames:v 1 -q:v 3 app/assets/scene/env.jpg
ls -lh app/assets/scene/env.jpg
