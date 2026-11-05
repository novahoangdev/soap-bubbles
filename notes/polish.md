# Polish notes

The separate shader-polish lane got stuck launching its dev client and was stopped (03/11 ~03:15); its reference images
stay in `notes/polish/ref/` (Codex: single backlit bubble, cluster, ageing bubble). Shader work since then by the main agent.

## Shaders (app/src/shaders)

- **film.ts — ageing.** The drained cap goes through first-order interference colours (thickness 150–290 nm: gold,
  magenta, blue) from the top down, then black-film spots (10 nm, no reflection) open with sharp edges
  (`spot = smoothstep(0.7, 0.73, n2·0.75 + zone·0.45)`). Before: a uniform fade to transparent that read as "pale".
- **bubbles.ts — curved Plateau walls.** `wallSide()` returns the signed distance to the shared wall: a spherical cap of
  radius r₁r₂/|r₁−r₂| through the two junction points, bulging into the larger bubble (flat radical line when the radii
  differ by < 4 %). Ownership of pixels inside two cluster members follows the same test, so the silhouettes meet the
  wall exactly.
- **Look-independent glows.** The pop rim (1.1 / 0.6) and the wall glow (`softSky · 0.18`) no longer scale with the
  look's env gain (night is 2.75× brighter in gain and turned walls into flat white lines).
- **Per-look soft world.** `softSky` / `softGround` uniforms (defocused bubbles, wand film, wall glow) and `sunUV` / `warm`
  in post.ts, passed from `src/scene/looks.ts`.

## Scene-side visual touches (BubbleScene.tsx)

- **Star glints** where each rim mirrors the key light (half vector between view and light), twinkling, rays slowly
  turning; hidden when the rim point is buried inside a cluster neighbour.
- **Look crossfade**: pictures crossfade over 1.6 s; the env map swaps at the midpoint while the exposure glides between
  the looks with a 55 % dip, so the reflection swap isn't a visible jump.

## Night look

- Blender env bulbs are 1–3 px → aliasing in reflections. `tools/night_env.sh` blooms them and adds a broad warm "porch
  window" behind the camera so bubble fronts show their film colours (a night photographer's trick). env gain 5.5.

## v18 (art-director pass on v17, 7/10)

- **Night env softened** (`tools/night_env.sh`, blur 10 px / 16 px vertically before the bloom): sharp bulb strings mirrored
  on the giant read as a dotted "wireframe globe" and the horizon as a hard seam. Now soft warm swirls. v17's map is kept in
  `blender/textures/env/night_env_v17.jpg`.
- **Pops tear instead of drawing a halo**: the hole edge wanders with film noise (up to ±0.16 rad), the rim breaks into
  beads tinted by the film colour; big bubbles open slower (sweep time × (r/50)^0.75: 0.3 s for the giant).
- **Black-film spots are outlined** by a band of bright first-order film (~230 nm, white/gold) so the dark islands read.
- **Black film reads on any background** (v20): film thinner than ~70 nm gets 62 % opacity (front) / 30 % (back) with no
  reflection; against bright bokeh a physically transparent black film was invisible. Over the last 12 % of its life a
  bubble's spots merge into a black cap opening from the top (noisy edge, bright first-order rim). v21: the spots come from a
  low-frequency noise in a rigid, slowly turning frame; in the latitude-sheared swirl frame they had become thin dark
  "zebra" strokes after ~10 s of differential rotation.
- **Golden env** (`tools/golden_env.sh`, source `blender/textures/env/golden_env_sharp.jpg`): blurred 6/10 px, the lawn
  below the horizon at 45 % saturation and darker, so bubble bottoms show film colour instead of olive green.
- **Demo taps** only pick bubbles of r ≥ 16–22 pt that aren't cut by the screen edge, preferring cluster members.

## v26–v27 (photorealism pass; art director on v24: realism 6/10)

- **Env atlas, three levels** (`tools/env_atlas.sh`, replaces `night_env.sh` / `golden_env.sh` for the app; those stay
  for reference): sharp (σ 0.9 px + tight bulb glow), mid (σ 3.5–4.5), soft (the v18 map) stacked in one 2048×3072 JPEG.
  `envAt(d, fp)` in `app/src/shaders/env.ts` blends two levels from the reflection footprint `fp = 2 / (3 · r · n_z)` rad per
  device pixel: big bubbles mirror crisp little light strings, rims and small bubbles read the soft levels (no aliasing).
  The v17 "wireframe globe" came from aliasing and over-bright bulb bloom, not from sharpness.
- **Porch window** (night `win` / `winCol` in `looks.ts`): an analytic four-pane window up-left behind the camera, so the
  front surface mirrors it upright (upper left) and the back surface inverted (lower right): the double reflection of real
  bubble photos. The baked porch glow in the env is down to 30 %.
- **Fringe averaging**: each wavelength's `cos` term is damped by `exp(−½(4π n cosθₜ σ_d / λ)²)`, σ_d = 900 nm / (3 r n_z)
  per pixel, so rims and small bubbles wash out to silver instead of drawing neon outlines. Plus fine flow filaments (±35 nm).
- **Black film** is transparent again (veil 0.12 / 0.06): it reads as a hole in the reflections, outlined by the bright
  first-order band. Its cap is centred 20° toward the camera (curved edge) with a two-octave ragged edge.
- **Pops**: 35 ms sweep (×√(r/50), at most 50 ms: two or three frames), a thin silvery rim mirroring the world, 1.5 + r/16
  droplets per physics step (a few dozen), pin-head beads, fast ones drawn as shutter streaks along their velocity.
  No star glints, no demo fingertip.
- **Wobble**: a kick never snaps the axis of a visible wobble (it projects onto the current axis); amplitude capped at 12 %.
- **Wand** (night): wet clear coat, a liquid band on the inner edge of the ring, the porch window and bulbs as highlights
  (`blender/scripts/night_look.py`, `SB_WAND_WET`).

## v37–v39 (four looks; art director: golden 8, night 8, studio 6.5, dawn 5.5)

- **Per-look film parameters** (`looks.ts` → uniforms): `lookK` = (bulb lift, film colour amount, black-film veil, back
  surface gain) and `filmF` (swirl scale). A negative lift only takes the very core of a light (threshold 0.95: the studio
  softbox, not the diffuser around it); the lift only applies above the horizon (`d.y` > ~0.1), so lamps sagging low
  between the trees don't burn a dotted line across every equator.
- **Night**: back image at 0.42 (it doubled every reflection), bright sources shed the film tint on the back too (0.6:
  warm windows, not grey paper), the horizon band always read from the blurred atlas levels, the sky strip just above the
  horizon darker in the env (a cyan stripe), bulb cores as small round glows in the sharp level (a dilation in v38 caught the
  wires too: "barbed wire"; v40 uses a high threshold + Gaussian instead). The wand film is near invisible (×0.4 reflection,
  55 % colour, capped bright reflections). Near-lens ghosts drift along the frame edges.
- **Studio**: a broad diffuser centred behind the photographer (`tools/env_atlas.sh`, flat-topped, ±60° wide) gives every
  bubble face swirling colour on black, the softbox stays the crisp highlight; plate crushed to pure black.
- **Dawn**: env gain 0.14, the env ground ~6× darker than the sky, sky 1.5× more saturated toward peach, film colour 85 %,
  black-film veil 25 %. What still holds it back is the plate (flat beige middle band, a bright mist patch behind the
  cluster), not the bubbles.
- **Golden hour v2** (`golden2_look.py`, agent-built): backlit park at sunset; env gain 0.5 and no lift (the bright sky was
  lifted to white).
- **Known**: at app t ≈ 4.28 s the giant is pulled ~20 pt in a few frames when it sticks to the cluster (the bond spring
  starts far from its rest distance); clamping the spring changes the storyboard, so it waits for the next re-timing.

## Perf

All recordings 60/60 distinct frames/s on the sim (Release, TIMESCALE 0.5). Wall test adds a sqrt per cluster pair per
pixel only inside overlapping cluster members.
