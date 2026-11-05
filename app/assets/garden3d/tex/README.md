# Garden 3D textures

All images were painted by the Codex CLI image generator (anime/Ghibli-like meadow style) and post-processed with Python (numpy/scipy/Pillow).
Transparent sprites were painted on a flat key colour (magenta #FF00FF for green subjects, green #00FF00 for clouds/butterfly), then keyed out: soft alpha from distance-to-key, local edge alpha re-estimation, key un-mixing + hue-based despill, and colour bleed into fully transparent pixels (mipmap-safe, no key fringe). Sprites are resized in premultiplied space.

- `ground_grass.jpg` 1024x1024: seamless top-down lawn with small clover; slightly desaturated, made tileable by blending with a half-offset copy (noise-broken crossfade).
- `path.jpg` 512x512: seamless top-down warm sandy path with pebbles; desaturated from the orange original, made tileable the same way.
- `bark.jpg` 512x512: seamless soft stylized bark (vertical grooves); made tileable the same way.
- `sky_gradient.jpg` 512x1024: procedural (not Codex) vertical gradient, vivid blue at the top to pale cyan-white at the horizon (bottom), dithered.
- `grass_tufts.png` 1024x512 RGBA: 4x2 atlas (256px cells) of lush leafy grass clumps, some with tiny daisies; each cell bottom-centred (2px bottom margin), fitted per cell. Magenta key.
- `flowers.png` 1024x1024 RGBA: 4x4 atlas (256px cells), bottom-centred. Rows 1-2: white daisies (single, three-quarter, tilted, clumps of 2-3, with buds). Row 3: buttercups, pink cosmos, red tulip, lavender. Row 4: forget-me-nots, orange poppy, white clover, mixed wildflower clump. Magenta key.
- `foliage.png` 512x512 RGBA: round cluster of fresh leaves for tree canopy cards, lit from the top-left, centred. Magenta key.
- `daisy_head.png` 256x256 RGBA: one face-on daisy head (camera-facing sprites / foreground bokeh), centred. Magenta key.
- `cloud_a.png` / `cloud_b.png` / `cloud_c.png` 1024x512 RGBA: fluffy anime cumulus (tall tower / wide bank / medium puffs), centred. Green key.
- `hills.png` 2048x512 RGBA: horizontally tileable distant rolling hills and tree lines with haze, transparent above the skyline. Magenta key; wrap made by crossfading the ends (colour) and interpolating the ridgeline (alpha).
- `butterfly.png` 256x256 RGBA: pastel butterfly from above, wings open; left half mirrored onto the right so it is exactly symmetric about the vertical centre line (x = 128). Green key.
- `leaf_card.png` 256x256 RGBA: single green leaf pointing up, stem at the bottom, centred. Magenta key.

### Painted trees, treeline, bushes (second batch)

Same Codex + magenta-key pipeline, with prompts in the Studio Ghibli painted-background style (soft brush leaf clusters, sunlit warm yellow-green tops, cool blue-green shaded undersides, light from the upper right). Extra clean-up for foliage: hue-aware re-solve of pink/salmon key mixes (incl. small gaps inside the crown), removal of stray orange-red specks, rim pixels clamped to the inner colour (removes the generator's over-saturated green halo), and a final purple-cast guard.

- `tree_a.png` 1024x1024 RGBA: tall slender tree, narrow oval crown, slightly leaning trunk. Trunk base at the bottom centre (x = 512, 2px bottom margin).
- `tree_b.png` 1024x1024 RGBA: broad spreading tree, wide dome crown on a short thick trunk with visible limbs. Trunk base at the bottom centre.
- `tree_c.png` 1024x1024 RGBA: medium tree, full rounded slightly asymmetric crown, curved trunk. Trunk base at the bottom centre.
- `treeline.png` 2048x512 RGBA: horizontally tileable forest edge (row of crowns of varied heights), transparent above the crowns, solid to the bottom edge, which is darkened slightly where it meets the meadow. Hazed toward pale blue (16%) and slightly desaturated so it sits behind the near trees. Wrap made by cutting where the silhouette height/slope match and crossfading 56 columns (premultiplied).
- `bush_a.png` 512x512 RGBA: soft round leafy shrub, bottom-centred.
- `bush_b.png` 512x512 RGBA: rounded flowering shrub with tiny white flowers, bottom-centred.
- `petal.png` 128x128 RGBA: single white daisy petal (diagonal), centred, for drifting particles.
- daisy_petals.png (2048², RGBA): NOT Codex: painted procedurally by `tools/paint_daisy.py` (numpy, 2× supersampled): a 2 × 2 atlas of four lawn-daisy heads from above (~30 narrow two-layer petals of uneven length, crease and veins, creamy-green bases, the front layer's soft shadow on the back one, a dome of golden-angle florets, closed and greener in the middle), colour bled into the transparent margin. Mapped onto the 3D daisies' cupped head disc (blender/scripts/garden3d_props.py `make_daisy_head_tex`), one head per flower.
- daisy_blur.png (256²): the first head of daisy_petals.png at 70 % saturation, 196 px, padded and Gaussian-blurred (σ 6 px, alpha too) for out-of-focus foreground daisies; made with ffmpeg.
- butterfly_soft.png (256²): butterfly.png at 55 % saturation: a soft wing painting that each butterfly tints (cream, lemon, lilac, blush, sky); ffmpeg `hue=s=0.55`.
