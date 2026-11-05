#!/bin/bash
# env_atlas.sh: build the three-level environment atlas a look's bubbles sample (v26).
#   LOOK=night tools/env_atlas.sh      (or LOOK=golden)
# Output: one 2048×3072 JPEG, three equirect maps stacked top to bottom:
#   0 sharp  (σ ≈ 1 px + a tight glow around the bulbs): big, in-focus bubbles mirror crisp little images of the light strings
#   1 mid    (σ ≈ 4 px)
#   2 soft   (the v18 softened map: night_env.sh / golden_env.sh)
# The shader picks a level per pixel from the reflection's footprint (how far the mirrored direction moves across one screen
# pixel: small bubbles and rims see a wide patch of the world, so they read the blurrier levels and never alias into the dotted
# "wireframe globe" that a single sharp map gave in v17).
# Night: the porch glow behind the camera is kept only faintly (the analytic window in the shaders replaces it).
set -euo pipefail
cd "$(dirname "$0")/.."
LOOK=${LOOK:-night}
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
if [ "$LOOK" = night ]; then
  SRC0=blender/textures/env/night_env_sharp.jpg
  OUT=app/assets/scene/night/env.jpg
  # (v38) the sky in the few degrees just above the horizon 45 % darker: it drew a bright cyan stripe along every bubble's
  # equator
  SRC=$TMP/src.png
  ffmpeg -v error -y -i "$SRC0" -vf "format=gbrp,geq=r='r(X,Y)*(1-0.45*exp(-pow((Y-0.49*H)/(0.012*H),2)))':g='g(X,Y)*(1-0.45*exp(-pow((Y-0.49*H)/(0.012*H),2)))':b='b(X,Y)*(1-0.45*exp(-pow((Y-0.49*H)/(0.012*H),2)))'" -frames:v 1 "$SRC"
  PORCH=${PORCH:-0.3}
  ffmpeg -v error -y -f lavfi -i "color=c=black:s=2048x1024" -frames:v 1 -vf "format=gbrp,geq=\
r='255*$PORCH*exp(-(pow(min(X,W-X)/(0.15*W),2)+pow((Y-0.45*H)/(0.2*H),4)))+24*exp(-pow((Y-0.15*H)/(0.25*H),2))':\
g='228*$PORCH*exp(-(pow(min(X,W-X)/(0.15*W),2)+pow((Y-0.45*H)/(0.2*H),4)))+27*exp(-pow((Y-0.15*H)/(0.25*H),2))':\
b='185*$PORCH*exp(-(pow(min(X,W-X)/(0.15*W),2)+pow((Y-0.45*H)/(0.2*H),4)))+42*exp(-pow((Y-0.15*H)/(0.25*H),2))'" "$TMP/porch.png"
  ffmpeg -v error -y -i "$SRC" -i "$TMP/porch.png" -filter_complex "[0]format=gbrp,split=3[s][h][s2];[s]gblur=sigma=0.9[a];\
[h]lutrgb=r='if(gt(val,90),min(255,val*1.6),0)':g='if(gt(val,80),min(255,val*1.5),0)':b='if(gt(val,80),min(255,val*1.4),0)',gblur=sigma=2.2[g0];\
[s2]lutrgb=r='if(gt(val,${BULB_T:-245}),255,0)':g='if(gt(val,${BULB_T:-245}),240,0)':b='if(gt(val,${BULB_T:-245}),210,0)',gblur=sigma=1.4,lutrgb=r='min(255,val*3)':g='min(255,val*3)':b='min(255,val*3)'[d];\
[a][g0]blend=all_mode=screen:all_opacity=0.35[ag0];[ag0][d]blend=all_mode=screen[ag];[1]format=gbrp[p];[ag][p]blend=all_mode=screen,format=gbrp" -frames:v 1 "$TMP/l0.png"
  ffmpeg -v error -y -i "$SRC" -i "$TMP/porch.png" -filter_complex "[0]format=gbrp,split=2[s][h];[s]gblur=sigma=3.5:sigmaV=4.5[a];\
[h]lutrgb=r='if(gt(val,80),min(255,val*1.6),0)':g='if(gt(val,70),min(255,val*1.5),0)':b='if(gt(val,70),min(255,val*1.4),0)',gblur=sigma=5[g];\
[a][g]blend=all_mode=screen:all_opacity=0.45[ag];[1]format=gbrp[p];[ag][p]blend=all_mode=screen,format=gbrp" -frames:v 1 "$TMP/l1.png"
  ffmpeg -v error -y -i "$SRC" -i "$TMP/porch.png" -filter_complex "[0]format=gbrp,gblur=sigma=10:sigmaV=16,split=3[a][b][c];\
[b]lutrgb=r='if(gt(val,70),val*1.6,0)':g='if(gt(val,62),val*1.5,0)':b='if(gt(val,62),val*1.4,0)',gblur=sigma=8[g1];\
[c]lutrgb=r='if(gt(val,95),val,0)':g='if(gt(val,85),val,0)':b='if(gt(val,85),val,0)',gblur=sigma=18[g2];\
[a][g2]blend=all_mode=screen[ab];[ab][g1]blend=all_mode=screen:all_opacity=0.7[ag];[1]format=gbrp[p];\
[ag][p]blend=all_mode=screen,format=gbrp" -frames:v 1 "$TMP/l2.png"
elif [ "$LOOK" != golden ]; then
  # any other look (v35): blender/textures/env/<look>_env_sharp.jpg → app/assets/scene/<look>/env.jpg, plain blur levels
  SRC=blender/textures/env/${LOOK}_env_sharp.jpg
  OUT=app/assets/scene/$LOOK/env.jpg
  for spec in "0 0.9 0.9" "1 3.5 4.5" "2 9 14"; do
    set -- $spec
    PRE=""
    # studio (v36): crush the backdrop's faint glow to true black; dawn (v36): ground and foliage below the horizon 3–4×
    # darker than the misty sky, so bubbles carry a bright-top / dark-bottom reflection instead of an even pastel wash
    [ "$LOOK" = studio ] && PRE="curves=all='0/0 0.09/0 0.3/0.25 1/1',"
    # golden2: the lawn below the horizon in shade: about half as bright and warmer (less of a green stamp in the bubbles)
    [ "$LOOK" = golden2 ] && PRE="geq=r='r(X,Y)*(1-0.42*clip((Y-0.5*H)/(0.05*H),0,1))':g='g(X,Y)*(1-0.55*clip((Y-0.5*H)/(0.05*H),0,1))':b='b(X,Y)*(1-0.45*clip((Y-0.5*H)/(0.05*H),0,1))',"
    # (v38) and the sky 1.5× more saturated (peach / pink, not beige), the ground tinted green rather than grey (v39: the
    # highlights pushed toward peach)
    [ "$LOOK" = dawn ] && PRE="eq=saturation=1.5,colorbalance=rs=-0.04:gs=0.05:bs=-0.03:rh=0.05:gh=-0.01:bh=-0.05,geq=r='r(X,Y)*(1-0.86*clip((Y-0.49*H)/(0.05*H),0,1))':g='g(X,Y)*(1-0.86*clip((Y-0.49*H)/(0.05*H),0,1))':b='b(X,Y)*(1-0.84*clip((Y-0.49*H)/(0.05*H),0,1))',"
    ffmpeg -v error -y -i "$SRC" -vf "format=gbrp,${PRE}gblur=sigma=$2:sigmaV=$3" -frames:v 1 "$TMP/l$1.png"
  done
  if [ "$LOOK" = studio ]; then
    # a big diffuser behind the photographer (the classic bubble-macro setup): fills the bubble fronts with broad colour
    # fields; the env's own softbox and strip stay the crisp highlights on top (v37: centred behind the camera, wide, flat
    # topped and brighter at its upper left; v36's narrow side band only lit a crescent)
    FILL=${FILL:-0.9}
    ffmpeg -v error -y -f lavfi -i "color=c=black:s=2048x1024" -frames:v 1 -vf "format=gbrp,geq=\
r='255*$FILL*(0.55+0.45*clip(1.2-Y/H-0.4*min(X,W-X)/W,0,1))*exp(-(pow(min(X,W-X)/(0.34*W),4)+pow((Y-0.45*H)/(0.36*H),4)))':\
g='246*$FILL*(0.55+0.45*clip(1.2-Y/H-0.4*min(X,W-X)/W,0,1))*exp(-(pow(min(X,W-X)/(0.34*W),4)+pow((Y-0.45*H)/(0.36*H),4)))':\
b='232*$FILL*(0.55+0.45*clip(1.2-Y/H-0.4*min(X,W-X)/W,0,1))*exp(-(pow(min(X,W-X)/(0.34*W),4)+pow((Y-0.45*H)/(0.36*H),4)))'" "$TMP/fill.png"
    for l in 0 1 2; do
      ffmpeg -v error -y -i "$TMP/l$l.png" -i "$TMP/fill.png" -filter_complex "[0]format=gbrp[a];[1]format=gbrp[b];[a][b]blend=all_mode=screen,format=gbrp" -frames:v 1 "$TMP/f$l.png"
      mv "$TMP/f$l.png" "$TMP/l$l.png"
    done
  fi
else
  SRC=blender/textures/env/golden_env_sharp.jpg
  OUT=app/assets/scene/env.jpg
  # the lawn below the horizon: desaturated and darkened (golden_env.sh) at every level
  g() {
    ffmpeg -v error -y -i "$SRC" -filter_complex "[0]format=gbrp,gblur=sigma=$1:sigmaV=$2,split=2[a][b];\
[b]hue=s=0.45,eq=brightness=-0.05:gamma=1.15,format=gbrp[g];\
color=c=black:s=2048x1024,format=gray,geq=lum='255*clip((Y-0.505*H)/(0.06*H),0,1)'[m];\
[a][g][m]maskedmerge,format=gbrp" -frames:v 1 "$3"
  }
  g 0.8 0.8 "$TMP/l0.png"
  g 3 4 "$TMP/l1.png"
  g 6 10 "$TMP/l2.png"
fi
if [ "$LOOK" = night ]; then
  # (v28) overhead the light strings all converge on the zenith; mirrored on a sphere that fan of lines reads as a globe's
  # wireframe. Above ~25° elevation the sharp and mid levels take the soft level, so only the strands sagging between the
  # trees (low in the sky) mirror crisply, like the two or three strings in a real bubble photo.
  ffmpeg -v error -y -f lavfi -i "color=c=black:s=2048x1024" -frames:v 1 -vf "format=gray,geq=lum='255*clip((Y-0.335*H)/(0.07*H),0,1)'" "$TMP/mask.png"
  for l in 0 1; do
    ffmpeg -v error -y -i "$TMP/l2.png" -i "$TMP/l$l.png" -i "$TMP/mask.png" -filter_complex "[0]format=gbrp[a];[1]format=gbrp[b];[2]format=gray[m];[a][b][m]maskedmerge,format=gbrp" -frames:v 1 "$TMP/m$l.png"
    mv "$TMP/m$l.png" "$TMP/l$l.png"
  done
fi
ffmpeg -v error -y -i "$TMP/l0.png" -i "$TMP/l1.png" -i "$TMP/l2.png" -filter_complex "[0][1][2]vstack=inputs=3,format=yuv444p" -frames:v 1 -q:v 2 "$OUT"
ls -lh "$OUT"
