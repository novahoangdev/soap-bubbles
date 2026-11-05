# Blender pipeline

This folder holds the background passes for the Soap Bubbles app: a backlit golden-hour garden shot on an 85 mm lens, plus the bubble wand. Blender runs headless only (`-b`). Run everything through `tools/build.sh`:

```sh
tools/build.sh                 # final: 100 %, 256 spp (env 128), about 3.5 min on an M5 Pro GPU
PREVIEW=1 tools/build.sh       # preview: 50 %, 48 spp (env 32), about 20 s
TEX=1 tools/build.sh           # reprocess the Codex images in textures/raw first
tools/build.sh --only bg,wand  # render only some passes (bg, wand, env)
LOOK=night tools/build.sh      # second look: twilight with fairy lights -> app/assets/scene/night/ (about 2.5 min)
```

There are two looks. **golden** is the default: `blender/garden.blend`, written to `app/assets/scene/`. **night** is the same garden at blue hour with fairy lights: `blender/garden_night.blend`, written to `app/assets/scene/night/`. Both share the camera, the wand and the ring position, so the ring and `wand_front` values in the two `layout.json` files are identical.

## Scripts (`blender/scripts/`)

- **`prep_textures.py`** turns the Codex images in `textures/raw/` into Blender textures in `textures/`. The leaf cards have a magenta background and the flower card a blue one; both are keyed to alpha, with the spill removed and the edges bled. Grass and hedge become 1024 px JPEG tiles.
- **`build_scene.py`** builds `blender/garden.blend` from scratch:
  - **Sky and camera.** Physical sky (`MULTIPLE_SCATTERING`) with the sun 7° up and 2° left of the view axis. The portrait camera is 1320×2868, 85 mm (vertical sensor fit 36 mm) and level at 1 m. It focuses at 1.2 m on the wand plane at f/2.
  - **Garden.** Translucent leaf cards: near branches at about 3 m, a loose leaf screen in front of the sun at 14 m (with a clear window around the sun), a hero tree, a far tree line, and a ring of trees all around for the env map. Also a lumpy hedge at 9 m with ragged leaves on top, cosmos clumps, the lawn, and emissive glints that turn into bokeh discs.
  - **Wand.** A ridged pink torus parallel to the image plane, so it projects as an exact circle (centre at 50 % / 80 % of the frame, inner radius 70 pt). It has a neck, a mint handle and a collar, all in glossy clear-coated plastic. Fill, key and rim area lights are light-linked to the wand only, so it reads in the backlit shade without lighting the garden.
  - **Sky seen by the camera.** Camera rays see a soft-clipped copy of the sky (`c / (1 + c/400)`), which keeps the defocused sky gaps around the sun free of fireflies.
  - **Haze.** The haze volume is off by default (`SB_HAZE=0.006` turns it on); through f/2 depth of field it was too noisy. The golden veil is added in post instead.
  - **Settings.** Knobs are read from environment variables: `SB_FSTOP SB_EXPOSURE SB_WB SB_SKY SB_SUN SB_SUN_CAM SB_SKY_CLIP SB_HAZE`. Colour management is AgX (Medium High Contrast), exposure +0.8 and white balance 7000 K (warm).
  - **Layout data.** Values for `render_passes.py` are stored in `scene["sb"]`.
- **`night_look.py`** is called by `build_scene.py` when `SB_LOOK=night`. It runs after the golden garden is built and uses its own random stream, so the golden build does not change. It reworks that garden:
  - **Sky.** A blue-hour gradient sky with no sun: deep indigo at the zenith, blue-violet lower down, and a faint mauve afterglow just above the horizon in front. Faint stars are switched on for the env pass only (value node `stars_on`). A weak cool moon (a sun lamp, never visible) adds faint rims to the foliage.
  - **Opened canopy.** The 14 m leaf screen, the near branches and the right tree were only there to break up the golden sun, so they are removed. The hero canopy is thinned by half, and the cosmos clumps by the lantern are removed. The top 40 % of the frame becomes sky, with dark tree silhouettes.
  - **Fairy lights** (about 3,400 bulbs): catenary strings of small emissive bulbs, with thin dark wires. The colours are warm white and amber, plus a few pink and teal. The bulb spacing grows with distance (fairy lights up close, festoon bulbs 0.3 to 0.6 m apart further out), so each defocused bulb stays a separate disc through the f/2 depth of field. Strings also hang along the hedge, wind in spirals through the hero tree and the ring trees, form a web overhead, and run behind the camera. The env and the glossy wand see those as sharp points.
  - **Bulb light.** Bulbs show full radiance to camera and glossy rays, but only `SB_BULB_DIFFUSE` (2.5 %) of it lights the scene; otherwise the bulbs flood the garden and kill the blue hour.
  - **Lanterns.** Six frosted globe lanterns, each a glowing mesh with an invisible point light inside. One is the warm key, upper-left at 6.5 m. The others are pink and teal globes in the distance, one on the lawn bottom-left (the warm glow pool), and one behind the camera.
  - **Wand.** Its light-linked lights become a weak cool sky fill, a small warm key up-left (a crisp highlight on the clear coat), a warm rim and a cool kicker on the right.
  - **Settings.** Knobs: `SB_EXPOSURE` (0), `SB_WB` (6500), `SB_SKY`, `SB_BULBS`, `SB_BULB_DIFFUSE`, `SB_MOON`, `SB_LANTERN`, `SB_WAND_KEY`, and for the wet wand `SB_WAND_WET` (1; 0 = the old dry plastic), `SB_WAND_GLINT` (400: bulb radiance seen in the wand's own reflections, wand pass only), `SB_WAND_MENISCUS` (0.6), `SB_WAND_WINDOW` (1: a warm porch-window area light behind the camera, glossy-only, linked to the wand).
  - **v2 "photo" look** (the defaults; each part has a knob, 0 switches it off). The aim is a real blue-hour photo shot on a fast 85 mm:
    - **World.** A house with warm lit windows at 46 m behind the hedge, right of centre (Codex facade `textures/raw/house_night.png` -> `house_night.jpg`, warm pixels emit; `SB_HOUSE` 0.45), and a second one behind the camera that only the env and the bubbles see (`SB_HOUSE_BACK`). Pale hydrangea shrubs (Codex card `hydrangea.png`, magenta-keyed) stand in front of the hedge at both sides of the frame (`SB_HYDRANGEA`), replacing the cosmos border. A cool sun lamp, light-linked to the garden within 14 m (not the lawn, not the trees), stands in for the blue-hour sky dome so foliage and flowers read (`SB_SKYFILL`). The sky gradient is a bluer cobalt (`SB_SKY_BLUE`).
    - **Lights.** Bulbs are 2400-3000 K warm whites with a wide per-bulb brightness spread (some dim, a few hot); coloured bulbs are rare (`SB_BULB_COLOR` 0.03). A copper-wire micro string sags across the top at 1.5-2.3 m, just behind the focus plane: the only small discs (`SB_MICRO`). The hedge swags are dimmer with gaps (`SB_HEDGE_LIGHTS` 0.4); the two festoon strings across the upper middle are off (`SB_MID_LIGHTS` 0). All globes are warm; the key lantern keeps its position (layout `sun`) but is dimmed so it is no longer a blown white blob (`SB_KEY` 0.22, `SB_GROUND_POOL`). `SB_BULB_CAM` (0.6) scales what the main camera sees of the bulbs so the discs stay below clipping; the env pass keeps the full radiance.
    - **Lens.** An 11-blade aperture (`SB_BLADES`, `SB_BLADE_ROT`). A transparent filter 2 mm in front of the lens, whose transmission is each disc's brightness profile: a brighter rim and faint onion rings (`SB_RIM` 0.45, `SB_ONION` 0.16). A black stop 10 cm in front of the lens, with a hole of 1.41 aperture radii (`SB_CATEYE`), clips off-axis bundles, so discs towards the frame edges become cat's eyes. These are camera-ray-only objects parented to the camera (`lens_only`), and the env pass hides them. The camera's clip start is 1 mm.
  - **v3 lower half.** Five shielded bollard path lights on the lawn at the frame sides (warm out-of-focus discs, spot pools at their feet; `SB_PATH_LIGHTS`). Foreground maple leaves 0.7-0.9 m from the lens in the bottom corners, and one fairy bulb at 0.55 m bottom-right that makes a big soft foreground disc (`SB_FOREGROUND`). The hydrangea heads are raised (`SB_HYD_LIFT` 0.3 m), with more translucency and a warm rim light behind them that is light-linked to the hydrangeas only (`SB_HYD_RIM`). The house behind the camera is off by default (`SB_HOUSE_BACK` 0): it made crisp window glyphs in every bubble. String wires carry a `string_wire` flag, and the env pass hides them unless `SB_ENV_WIRES=1`.
  - **v4 wand and mid band.**
    - **Wet wand.** The coat is mirror-smooth (`SB_WAND_COAT_SMOOTH` 1): only the meniscus bend drives it, with no noise or bump. The base keeps the moulded ridges, loses the fine speckle bump, and barely reflects (`SB_WAND_BASE_SPEC` 0.03).
    - **Wand highlights.** The bulb glint boost is now 1, which is physical (`SB_WAND_GLINT`; at 400 it lit the ridged base in square patches). The porch-window light is bigger and brighter (`SB_WAND_WINDOW_SIZE` 1.6, `SB_WAND_WINDOW` 2), so the highlights are continuous streaks along the tube.
    - **Mid band.** The blue-hour fill drops from 1.6 to 1.0 and the hydrangea rim light from 1 to 0.6, which takes about 38 % off the olive mid band.
    - **Env dashes.** The out-of-frame strings (overhead web, behind the camera) keep a minimum spacing of 1° between bulbs as seen from the bubble (`SB_ENV_THIN`), so strings running away from it no longer pile into dashes in the env.
- **`render_passes.py`** renders into `app/assets/scene/` (night: `app/assets/scene/night/`, the look comes from the .blend):
  - **`bg.jpg`** shows the whole frame. It is rendered to a 16-bit PNG and then graded in numpy: the lower third falls off into shade, the corners are softened, the shadows are warmed toward deep green, and a golden bloom plus a veiling flare around the sun is added with a screen blend.
  - **`wand_front.png`** shows only the wand. It is rendered at 2× (`SB_WAND_SS`) with `SB_WAND_SPP` samples (default: the bg's) and denoised (`SB_WAND_DENOISE` 1), then box-averaged down in premultiplied alpha. The previous sprite rect is kept whenever the wand still fits inside it (`SB_WAND_KEEP_RECT` 1). Everything else is hidden from camera rays but still lights and shadows it, and the film is transparent. It is cropped to its bounding box, with the crop recorded in `layout.json`. It gets the same grade and glow as `bg.jpg`, so the two match pixel for pixel. The alpha is straight (not premultiplied).
  - **`env.jpg`** is a 2048×1024 equirectangular panorama from the bubble position, with the wand hidden and no depth of field.
  - **`layout.json`** holds the ring centre and radii, the wand crop, the sun's screen position and camera-space direction, and the env orientation, all in the 440×956 pt frame.
  - A contact sheet is written to `render/preview/passes.jpg` (night: `passes_night.jpg`).
  - **Night grade.** Instead of the golden veil, the night grade:
    - deepens the falloff in the lower third and the corners;
    - adds a cool split-tone, so the near-black foliage and lawn turn blue-green-violet instead of the warm brown the bulbs leave;
    - adds a bloom around the discs;
    - gives every disc a faint brighter rim (a band-pass of the highlights), like the "soap-bubble" bokeh of old fast lenses (with the v2 lens this is only a touch, `SB_POST_RIM` 0.3, since the discs already have real rims);
    - (v2) adds fine sensor grain (`SB_GRAIN` 0.01; the bg only, not the wand crop);
    - (v3) keeps the widest bloom term low (`SB_BLOOM_WIDE` 0.04, was 0.16), so the dark lower half has no uniform grey veil.
  - **Night layout.** There is no sun at night, so the `sun` and `sun_dir` fields hold the key lantern. `sun` is its screen position (upper-left) and `sun_dir` is the direction from the bubble position to it. A `note` field explains this, and `key_light` gives the lantern's name, colour and distance.

## Conventions

- All images are display-referred sRGB with the AgX view transform baked in. Treat them as ordinary sRGB images.
- The night env is mostly dark. The lawn is near black, the sky is a navy-to-violet gradient, and hundreds of bulbs are 1 to 3 px points, with strings arching overhead and around the camera. It needs more gain in the app than the golden env (`envGain` 2.6 in `app/src/scene/looks.ts`). The sparkle in the reflections comes from those points, not from the analytic highlight.
- Camera space in `layout.json`: x points right, y points up, and z points towards the viewer (the sun has z < 0 because it is in front of the camera).
- Env map: u = 0.5 is the camera's forward direction, u = 0.75 is right, and u = 0 or 1 is behind the camera. v = 0 is the zenith, v = 0.5 the horizon and v = 1 the nadir. For a camera-space direction d: `u = 0.5 + atan2(d.x, -d.z) / 2π` and `v = 0.5 - asin(d.y) / π`.

### Night env post-process (app side)

The raw night env (`blender/textures/env/night_env_sharp.jpg`, copy of what `LOOK=night tools/build.sh` writes) is
post-processed by `tools/night_env.sh` into `app/assets/scene/night/env.jpg`: the 1–3 px bulbs get a soft bloom (they
would alias away in bubble reflections) and a broad warm "porch window" is added behind the camera so the bubble fronts
reflect a soft light and show their film colours. After re-rendering the night env, copy it to
`blender/textures/env/night_env_sharp.jpg` and rerun `tools/night_env.sh`.
