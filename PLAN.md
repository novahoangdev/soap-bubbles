# Soap Bubbles: blow into the phone

> **Status (04/11, night) — 3D garden g35:** natural blowing (bubbles leave the ring one after another, always beyond the wand) and a smooth curved glide home after the pop. Showcase pack rebuilt from g35.
>
> **Status (04/11, late evening) — 3D garden g34:** lofi music (`blender/scripts/lofi_garden.py`) with real public-domain birdsong (`blender/audio/birds/`), puffs that throw clouds of bubbles big and small, a smooth glide home after the pop (no jerk), poppies, cornflowers, clover and cow parsley in the meadow. Showcase pack rebuilt from g34.
>
> **Status (04/11, evening) — 3D garden g33, the long calm cut:** painted daisy heads (tools/paint_daisy.py) on cupped 3D discs, folded and twisted grass blades, the wand low and still (it stays when the camera leaves; the camera comes home over it), a ~40 s chill demo (slow breath, ~14 s follow, a second round), bigger visible small bubbles, chill music and the act word AGAIN (beat sheet g33b). Showcase pack rebuilt from g33.
>
> **Status (04/11, 07:30) — 3D garden mode (g1 → g32):** a second mode in the app (`app/src/garden3d/`, three.js WebGPU on react-native-webgpu): a painted anime daisy meadow with real depth; a big bubble flies off down the meadow and the camera follows it. 21 art-director rounds (5.5 → 9.3/10), promo layout v2 (8.2/10). Showcase pack: `video/soap-bubbles-garden3d-promo-4x3.mp4`, `-screen-9x19.mp4`, `-versions.mp4`, `images/garden3d/`. Final take g32; one-command rebuild `tools/rec3d.sh` + `tools/final3d.sh`. Versions: `notes/versions.md` (g rows). Known: unverified on a physical phone (adaptive resolution steps down under 48 fps).
>
> **Status (03/11, 23:30) — four looks pass (v37 → v40):** art-director rounds per look (golden 8, night 8, studio 6.5, dawn 6.5/10): per-look film parameters (`lookK`, `filmF`), golden hour v2 (`golden2_look.py`), studio with a broad diffuser behind the photographer, dawn plate v2 with a mid-focus blossom branch, night bulbs as round glows, near-invisible wand film, drifting near-lens ghosts; the app starts in the night look. Showcase pack `render/showcase-pack/` led by golden hour (promo `soap-bubbles-demo-v38g.mp4`), plus night v40, studio v39s, dawn v40d promos and 9:19 screen videos, versions and looks reels. Earlier (19:00): photoreal pass v24 → v35 (3-level env atlas, porch window, fringe averaging, black film, torn pops, handheld camera, wand in front, felt pops + music loop, Codex icon). Versions: `notes/versions.md`. Known: a 3-frame jump at app t ≈ 4.28 s (bond spring when the giant sticks); device-only audio/mic behaviour unverified on a phone.

An iPhone demo of about 15 seconds to post on X. Blow into the microphone and soap bubbles swell out of a plastic wand at the bottom of the screen: a soft, long breath grows one giant wobbly bubble, a sharp puff sprays a stream of little ones. Rainbow colours swirl and drain over each film (real thin-film interference in a Skia shader). Bubbles bump, stick together into clusters with flat shared walls, and burst into a spray of tiny droplets when you tap them.

Plan written on 03/11/2026. Skia is the core (one thin-film shader per bubble, droplets, post); Reanimated runs the physics on the UI thread (springs for wobble, sticking, wand film); expo-audio measures the breath; Blender renders the backlit garden and the environment the bubbles reflect.

---

## 0. Summary

**Clip story.** Late golden hour in a garden, the sun low behind dark, blurry foliage, warm bokeh everywhere. A pastel plastic wand sits at the bottom of the screen with a fresh soap film stretched across its ring, shimmering. A slow breath: the film bulges, a bubble balloons out, wobbling, the colours rushing over it, then pinches off with a jiggle and drifts upward, reflecting the sky and the trees (upright on the front, upside-down on the back). A sharp puff: a stream of fifteen little bubbles tumbles out. Two bubbles touch and *stick*, the wall between them flattens (Plateau's 120° rule), a third joins the cluster. A finger taps: the film tears open from the tap point, the rim races around the sphere and shatters into glittering droplets that fall; the neighbour in the cluster springs back into a sphere. The last big bubble thins at the top, turns gold → magenta → black, and pops on its own.

**Architecture.** Real-time 2D in Skia over a background pre-rendered by Blender. Each bubble is a quad with a runtime shader that computes a sphere (plus wobble deformation), thin-film interference over the visible spectrum, Fresnel, and reflections of an equirectangular environment map rendered by Blender from the same garden. No 3D engine needed.

- **Thin film:** film thickness field per bubble = gravity drainage (thick at the bottom, thin at the top, thinning with age) + swirling Marangoni eddies (advected, domain-warped noise) + breath turbulence. Reflectance is computed for 8 wavelengths (two-beam interference, `R(λ) = 2R₀(1 − cos δ)`, `δ = 4π n d cosθₜ / λ`) and converted to sRGB through fitted CIE curves. Below ~25 nm the film goes black, a sign it will pop.
- **Reflections:** front surface (convex, upright, small) and back surface (concave, inverted, dimmer) both sample the Blender environment map; sun highlight as a sharp specular window.
- **Physics** (UI-thread worklet, fixed pool of 32 bubbles, no allocation per frame): buoyancy ≈ neutral, drag, curl-noise breeze, finger wind, tilt gravity, collisions. Slow contacts stick: a bond pulls the centres to the Plateau distance `d² = r₁² + r₂² − r₁r₂`; the shared wall is an arc of radius `r₁r₂ / |r₁ − r₂|`. Each bubble has two spring wobble modes (ellipse l=2, trefoil l=3) kicked by birth, hits and neighbour pops.
- **Breath:** `expo-audio` `useAudioStream` (float32 PCM) → RMS + low-frequency "wind noise" energy per ~20 ms buffer → smoothed envelope in a shared value. A soft long breath = growth; a fast attack = spray. Fallback: recorder metering. On the simulator: press-and-hold the wand to fake a breath (drag up = stronger).

### Stack

Same as `../neon-sign/app` and `../goku-vs-frieza/app`: Expo SDK 58, RN 0.88.1, `react-native-skia` 3.8.x, Reanimated 4.7.1 + worklets 0.13, gesture-handler 3.3, expo-haptics, **expo-audio 58** (mic), expo-dev-client. Dev build, no Expo Go, no `react-native-webgpu` unless the shader cost forces it. Blender 5.2.2 at `/Applications/Blender.app`, headless `-b -P` only (the Blender MCP belongs to another project). FFmpeg for the promo.

**2D assets: generate freely with Codex, no need to ask** (foliage and flower cards for the Blender garden, grass texture, concept art, end card art):

```sh
codex exec --skip-git-repo-check -s workspace-write "Generate <description>, no text. Save it as <name>.png in the current directory and print its absolute path."
```

If Codex can't save the file, take the image from `~/Library/Application Support/orca/codex-accounts/*/home/generated_images/`. Compress images before putting them in `app/assets` or `blender/textures`.

---

## 1. Art direction

- Tone: summer golden hour, backlit, like an 85 mm f/1.4 photo. Deep warm-green shadows so the iridescence pops, a hot low sun upper-left behind the leaves, creamy bokeh discs (amber, peach, a few cool sky-blue ones).
- Bubbles: mostly transparent — colour only where the film reflects. Fresh film = pale silver-gold, a few seconds later = bands of magenta / cyan / green swirling, old film = gold top turning black just before it pops. Bright window of sky + sun highlight on the upper-left, inverted dim garden on the lower-right (back surface). A thin bright rim.
- Wand: glossy pastel plastic (bubblegum pink ring, mint handle), slightly worn, wet glints; the film in the ring always visible.
- Droplets: tiny, sharp, sun-glinting, a hint of colour; a soft mist puff on each pop.
- Typography for the end card only (promo).

## 2. Experience and storyboard

| Seconds | Shot | Interaction / effect |
|---|---|---|
| 0–1.5 | Frame 1 = the best moment: three iridescent bubbles (one cluster) floating in front of the sun | Swirls flowing, slow drift, gentle wobble |
| 1.5–5 | Long soft breath | Wand film bulges, giant bubble balloons out, colours rush, pinches off with a jiggle, drifts up |
| 5–7 | Sharp puffs | Stream of small bubbles tumbles out, bump, bounce |
| 7–9.5 | Bubbles meet | Two stick, flat shared wall, third joins (triple cluster) |
| 9.5–12.5 | Finger taps | Tear from tap point, rim → droplets fall, cluster neighbour springs back to a sphere; a chain of pops |
| 12.5–14.5 | Last giant bubble | Top drains gold → magenta → black, pops by itself; a few droplets hit the bottom edge |
| 14.5– | End card (promo) | |

UI: none on screen in demo mode. In normal mode a tiny breath meter glow around the wand ring, a mic hint on first launch ("blow gently"), haptics on pops and pinch-offs. Drag anywhere = waft air; tap = pop; long press on wand = fake breath (simulator).

## 3. Bubbles and physics

- **Pool:** 32 bubble slots × fields (x, y, vx, vy, r, age, life, seed, wobble a2/φ2/a3/φ3 + velocities, popAt, popX, popY, bonds[3]) stored as flat number arrays in shared values, mutated in place in a `useFrameCallback`, `modify()` to notify. Rendering: 32 fixed `<Rect>` slots, each with its own `<Shader>` uniforms derived from the arrays; hidden slots get zero size off-screen.
- **Wand:** ring centre/radius from `layout.json`. Film state: `bulge` spring driven by breath; when bulge passes the ring a cap grows — a sphere of radius `R ≥ a` whose centre sits `√(R² − a²)` in front of the ring (drawn face-on: a disc anchored to the ring, rising slightly). Breath stops or `R > Rmax` → neck pinch-off (spring), bubble released with velocity from breath, wobble kick, new film reforms in the ring (thin rainbow → silver over 0.6 s). Fast attack → spray mode: spawn small bubbles at a rate ∝ breath, random size 18–50 pt.
- **Forces:** net gravity ≈ −4 pt/s² (slowly sinking), quadratic drag, curl-noise breeze (slow), finger wind (velocity field around drag path, falls off with distance), tilt via gravity sensor.
- **Contacts:** overlapping and relative speed < threshold → bond (max 3 per bubble), spring to Plateau distance with damping; fast → elastic bounce + wobble kick. Bonded pairs share a wall rendered by the smaller-index bubble; each bubble clips itself by its bonded neighbours' wall planes/arcs.
- **Pop:** `popAt`, contact point in local coords. Shader shows the film only outside a growing cap around the pop point (angular radius grows ~π in 90 ms of demo time, the rim slightly thickened and bright). The rim emits droplets (particles pool 600, Atlas sprites, gravity, drag, fade); a mist puff; bonded neighbours lose the bond and get a wobble kick; haptic + pop sound.
- **Ageing:** life 8–20 s; top thickness drains to black; at the end the bubble pops itself from the thinnest point.

## 4. Shaders

- **`bubble.ts`** (per bubble): local coords with wobble deformation → sphere normal; Fresnel (Schlick, n = 1.33); thickness field (drainage + eddies + age); spectral two-beam interference at 8 wavelengths → XYZ → linear sRGB; front reflection `env(reflect(v, n))`, back reflection with inverted normal (×0.5); sun specular; rim; clip by bonded walls; pop hole + bright rim; premultiplied output (colour = R × env, alpha = luminance(R)).
- **`wall.ts`** (shared wall arc between bonded bubbles): drawn as part of the smaller-index bubble's shader.
- **`wand film`**: same film code with a flat-to-dome normal, thickness from reformation timer.
- **`post.ts`**: warm bloom on highlights, subtle chromatic edge, film grain, vignette, a light-leak drift.
- Env map: equirectangular image from Blender; the gamut conversion on Graphite (sRGB → P3) is irrelevant for colour data but keep it in mind for any data textures.

## 5. Blender

Scripts, rerunnable (like `../neon-sign/blender/scripts`):

- `prep_textures.py`: Codex images (raw/) → alpha-cut foliage / flower cards, grass texture.
- `build_scene.py`: garden at golden hour — Nishita sky with the sun low upper-left behind, layered foliage cards (near/mid/far) with translucency, a hedge, flowers, a lawn, floating dust motes and emissive bokeh points for sparkle; volumetric haze for light shafts. Camera portrait 1320×2868 (iPhone 17 Pro Max, design frame 440×956 pt), 85 mm, f/1.4 focused on an empty plane in front (everything behind is creamy bokeh). The wand (pink torus ring + mint handle, glossy plastic) at the bottom centre, sharp.
- `render_passes.py` (Cycles): `bg.jpg` (garden + wand, no film), `wand_front.png` (the ring's front part with alpha, drawn over the film), `env.jpg` (equirect 2048×1024 from the bubble position, no DOF, sharp sun window), `layout.json` (ring centre/radius in pt, sun direction in screen space, horizon).

## 6. Folder structure

```
soap-bubbles/
  PLAN.md  README.md
  blender/scripts/  prep_textures.py  build_scene.py  night_look.py  render_passes.py  promo.py  mix_clip.py  synth_audio.py
                    beats/ (v1…v15, n1, n2)
  blender/textures/ raw/ (Codex)  env/ (raw night env)
  tools/            build.sh  embed.sh  rec.sh  filmstart.sh  events.py  promo.sh  sheet.sh  showcase.sh  burst.sh  night_env.sh
                    perf/sksl_check.mjs
  notes/            versions.md  polish.md  promo.md
  render/promo/     vN/ recordings, soap-bubbles-demo-vN.mp4, soap-bubbles-night-nN.mp4, soap-bubbles-final.mp4, captions
  app/
    src/scene/BubbleScene.tsx   Canvas, layers, clock (fixed-step physics), gestures, demo, look crossfade, glints
    src/scene/looks.ts          golden hour / twilight looks       src/scene/layout.ts  Blender layout
    src/sim/pool.ts  step.ts    bubble pool, physics, wand, pops, droplets, clusters
    src/audio/breath.ts         mic stream → breath envelope
    src/shaders/film.ts  bubbles.ts  wandFilm.ts  post.ts
    src/fx/sfx.ts  haptics.ts   src/ui/MicHint.tsx   src/demo/script.ts
```

## 7. Demo mode and X clip

- `EXPO_PUBLIC_DEMO=1`: the app plays the storyboard of section 2 with a scripted breath curve and scripted taps (a faint ghost-finger dot), seeded randomness so every recording is identical. `EXPO_PUBLIC_TIMESCALE=0.5` slows the clock for smooth recordings (`tools/rec.sh` compresses time back to 60 fps CFR), as in Neon Sign.
- Clip rules (latest from Neon Sign / Pumpkin): 4:3 1920×1440, 60 fps; the phone stays still in the centre for the whole clip, one straight cut to the end card; frame 1 is the most beautiful moment; no status bar, no extra UI in the recording. End card compact: "Soap Bubbles", "Expo · React Native · Skia · Reanimated · Blender", "by Hoa Hoang · @novahoangdev", "From @vgangstudio with love". Audio: light, playful music with a hook + diegetic SFX (breath whoosh, wobble, pops, droplets), −14 LUFS, true peak ≤ −1 dBTP.
- Versions: each recording is `render/promo/vN/` + `blender/scripts/beats/vN.json`, clip `render/promo/soap-bubbles-demo-vN.mp4`, sheet `soap-bubbles-sheet-vN.jpg`; the chosen one copied to `soap-bubbles-final.mp4` + `caption-final.txt`.
- Caption: short and playful, credits line "Expo @expo · Skia v3 @wcandillon · Reanimated @swmansion", closing "From @vgangstudio with love #vgang".

## 8. Milestones (each one recordable)

| Milestone | Content | Done when |
|---|---|---|
| **M0** | Plan, Codex assets, Blender garden + passes (preview), app scaffold, sim, background on screen | Garden + wand visible on the sim |
| **M1** | Bubble shader (thin film, env reflections, Fresnel, sun), pool + physics, tap to pop (simple) | Bubbles float and look like soap |
| **M2** | Breath (mic + fake), wand film bulge, grow, pinch-off, spray; wobble springs; contacts + sticking clusters with Plateau walls | Blow → bubbles, they stick |
| **M3** | Pop polish (tear, rim, droplets, mist), ageing to black film + self-pop, haptics, post, demo mode | Storyboard plays by itself |
| **M4** | Final Blender render, Release perf 60/60 on the sim, recordings v1… with promo pipeline, sheet, caption | Clip file |
| **M5** | Audio (music + SFX), polish rounds from recordings, final clip | `soap-bubbles-final.mp4` |
| **M6** (added) | Second look: twilight with fairy lights (Blender), two-finger switch, day → night clip | `soap-bubbles-demo-v13+` |

## 9. Risks

- **Shader cost with many large bubbles:** 8-wavelength film per pixel × 32 quads. Mitigate: per-bubble bounding quads only, cheaper noise, LUT texture for thickness → RGB (1D, computed once on the CPU into an image) instead of the spectral loop.
- **Mic on the simulator:** uses the Mac mic (needs permission) — fake breath via long press and the demo script; real device test later.
- **Clusters of 3+ look wrong:** cap bonds at 3, small bubbles only stick in pairs/triples; walls as arcs only between bonded pairs.
- **Graphite pitfalls** (see neon-sign notes): no zero RSXform on Atlas, `makeTextureImage()` for big images, no `BlurMask` on trimmed paths.
- **Reanimated Release crashes:** all helpers called from worklets must be `"worklet"`; no allocation per frame.

## 10. Defaults chosen (changeable)

- Display name "Soap Bubbles", bundle id `dev.hoanghoa.soapbubbles`.
- Device: only the project's sim "Soap Bubbles 17 Pro Max" (UDID `FDBD95D1-C30D-4F57-B35F-0E302CB63F08`, iOS 27.0), portrait, 1320×2868 px = 440×956 pt. iOS only. Metro port 8092.
- English in code, comments and docs (the repo may go public); chat stays Vietnamese.
- No git repo and no push.
