#!/usr/bin/env bash
# Blender pipeline -> app/assets/scene: (Codex textures) -> build garden.blend -> render bg / wand_front / env + layout.json
#   tools/build.sh            final (100 %, 256 samples, env 128)
#   PREVIEW=1 tools/build.sh  quick preview (50 %, 48 samples, env 32)
#   TEX=1 tools/build.sh      reprocess Codex images in blender/textures/raw first
#   LOOK=night tools/build.sh twilight with fairy lights -> blender/garden_night.blend, app/assets/scene/night/
#   extra args go to render_passes.py, e.g. tools/build.sh --only bg,wand
# Scene knobs (env vars read by build_scene.py): SB_FSTOP SB_EXPOSURE SB_WB SB_SKY SB_SUN SB_HAZE
#   (night_look.py: SB_EXPOSURE SB_WB SB_SKY SB_BULBS SB_BULB_DIFFUSE SB_MOON SB_LANTERN SB_WAND_KEY SB_WAND_WET SB_WAND_GLINT SB_WAND_MENISCUS SB_WAND_WINDOW
#    v2 photo look: SB_BULB_COLOR SB_BULB_CAM SB_HEDGE_LIGHTS SB_MID_LIGHTS SB_MICRO SB_KEY SB_GROUND_POOL SB_HOUSE SB_HOUSE_BACK
#    SB_HYDRANGEA SB_SKYFILL SB_SKY_BLUE, lens: SB_BLADES SB_BLADE_ROT SB_CATEYE SB_RIM SB_ONION; v3: SB_PATH_LIGHTS SB_FOREGROUND SB_HYD_LIFT SB_HYD_RIM;
#    v4: SB_WAND_COAT_SMOOTH SB_WAND_BASE_SPEC SB_WAND_WINDOW_SIZE SB_ENV_THIN
#    render_passes.py: SB_POST_RIM SB_GRAIN SB_BLOOM_WIDE SB_ENV_WIRES SB_WAND_SS SB_WAND_SPP SB_WAND_DENOISE SB_WAND_KEEP_RECT)
set -eo pipefail
cd "$(dirname "$0")/.."
BLENDER=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
if [[ "${PREVIEW:-0}" == 1 ]]; then RARGS=(--pct 50 --samples 48 --env-samples 32); else RARGS=(--pct 100 --samples 256 --env-samples 128); fi
if [[ "${TEX:-0}" == 1 ]]; then
  "$BLENDER" -b --factory-startup -P blender/scripts/prep_textures.py 2>&1 | grep -E "TEX|Error|Traceback" || true
fi
LOOK=${LOOK:-golden}
if [[ "$LOOK" == golden ]]; then BLEND=blender/garden.blend; OUTDIR=app/assets/scene; else BLEND=blender/garden_$LOOK.blend; OUTDIR=app/assets/scene/$LOOK; fi
SB_LOOK=$LOOK "$BLENDER" -b --factory-startup -P blender/scripts/build_scene.py 2>&1 | grep -E "SAVED|NIGHT|Error|Traceback|line [0-9]+" || true
"$BLENDER" -b "$BLEND" -P blender/scripts/render_passes.py -- "${RARGS[@]}" "$@" 2>&1 \
  | grep -E "── render|SAVE|LAYOUT|TIMES|Error|Traceback|line [0-9]+" || true
ls -lh "$OUTDIR"
