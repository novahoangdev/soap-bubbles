# Promo clip + audio

How to turn a simulator recording into the X clip (4:3 1920×1440, 60 fps, H.264 + AAC, −14 LUFS). Ported from
`../neon-sign` (beat sheet v12 style): the phone stays still in the centre for the whole demo, one straight cut to the
end card, frame 1 = the app's first frame, no status bar overlay.

## Files

| File | What |
|---|---|
| `tools/promo.sh` | one command: sync → audio (if stale) → Blender frames → ffmpeg export + loudness readout |
| `blender/scripts/promo.py` | the Blender scene: titanium iPhone mockup playing the recording, golden-hour background (gradient, drifting sun glow, bokeh, blurry iridescent bubbles), end card |
| `blender/scripts/beats/vN.json` | beat sheet per recording: every timing, colours, end card layout, SFX events, music |
| `blender/scripts/mix_clip.py` | clip audio: synthesised music + SFX on the beat sheet events, mastered to −14 LUFS / ≤ −1 dBTP |
| `blender/scripts/synth_audio.py` | SFX generators (shared with the mix) + export of the in-app one-shots to `app/assets/sfx/` |
| `tools/sheet.sh` | 3×2 contact sheet of the exported clip (frames from the beat sheet `sheet`) |
| `render/audio/mix_vN.wav` (+ `.json`) | the clip audio (app t = 0 at its start), tempo and measured loudness |
| `render/promo/caption.txt` | X caption |

## Make a clip

1. Record (main lane): `UDID=… TS=0.5 SECS=19 OUT=render/promo/v1 tools/rec.sh` → `render/promo/v1/screen.mp4`
   (1320×2868, 60 fps CFR, demo time). **SECS must cover `app_end + card` (+ the launch)**: the phone on the end card
   keeps playing the recording after `app_end`, so with v1 (14.8 + 3.0) record at least ~19 s of demo time.
2. Copy the beat sheet: `cp blender/scripts/beats/v1.json blender/scripts/beats/v2.json` for a new version, and set
   `"audio": "render/audio/mix_v2.wav"`.
3. Quick look (seconds in the clip, half resolution):

   ```sh
   PCT=50 tools/promo.sh --beats blender/scripts/beats/v1.json --screen render/promo/v1/screen.mp4 --stills 0,4,9.8,14.7,15.2,17.5
   ```

   Stills land in `render/promo/stills/`. `still_00.000.png` must show the app's first frame (garden + bubble cluster).
4. Full clip:

   ```sh
   tools/promo.sh --beats blender/scripts/beats/v1.json --screen render/promo/v1/screen.mp4 \
       --out render/promo/soap-bubbles-demo-v1.mp4
   ```

   Options: `--film-start S` (see below), `PCT=50` (test render), `WORKERS=2` (parallel Blender processes, default 2;
   use 1 to keep the machine free), `PROMO_FAST=1` (8 TAA samples), `LABEL=v1` (small corner label for comparisons).
   Timing: the test render (PCT=50, WORKERS=1) took 6.8 min for 1068 frames; expect roughly 15–25 min at full
   resolution with WORKERS=2.
5. Contact sheet: `tools/sheet.sh render/promo/soap-bubbles-demo-v1.mp4 render/promo/soap-bubbles-sheet-v1.jpg blender/scripts/beats/v1.json`
6. Final: copy the chosen clip to `render/promo/soap-bubbles-final.mp4` and the caption to `render/promo/caption-final.txt`.

### Sync (`--film-start`)

`--film-start S` = the second in `screen.mp4` that shows **app t = 0** (the first frame of the demo clock, after the
prewarm). Without it, promo.sh finds the first frame where the garden replaces the dark launch screen
(`#120c08`, big jump in mean brightness) and uses `that second − sync_offset` (beat sheet, default 0: the demo clock
starts on the first drawn frame, see `BubbleScene.tsx`). It prints what it found:

```
garden appears at 0.8000s (YAVG 157.7/26.0->158.7) → app t=0 at 0.8s in the recording
```

If `still_00.000.png` is black, half faded in, or the pops are visibly off the sounds, pass `--film-start` by hand
(e.g. step through `ffmpeg -ss 0.8 -i screen.mp4 -frames:v 1 x.png`). If the recording already starts on the app's first
frame (no launch screen), detection falls back to 0.

## Beat sheet (v1)

- `app_start` 0.0 / `app_end` 14.8 / `card` 3.0 → clip 17.8 s (1068 frames). Cut to the end card at app 14.8 s
  (0.8 s after the big pop at 14.0). Card at clip 14.8 s.
- `sync_offset`, `screen_gain` (screen brightness), `card_screen` (null = the end-card phone keeps playing the recording;
  a number = it restarts from that app second, e.g. 0.0 to show the opening cluster again).
- `bg`: `[timing, top, mid, bottom, sun glow colour, glow strength, cross-fade frames]` — gentle shifts at 7.0 and 12.4 s.
- `bokeh_n`, `bubbles_n`: background sprites. `camera_d` / `card_d`, `card_phone` (pose on the card), `card_x` (text column centre).
- `title`, `tagline`, `title_in`, `title_step`: letters pop in at card + title_in + k × title_step; the mix plays a tuned
  "pip" on each letter, so keep both in the beat sheet.
- `music`: `bars_to_card` 7, `t0` 0 → tempo = 7 bars between app 0 and `app_end` (113.5 BPM for 14.8 s), so the end-card
  chord lands on a downbeat. Changing `app_end` changes the tempo slightly.
- `events` (app seconds, from `app/src/demo/script.ts`): `breath` keyframes (copy of `DEMO.breath`), `grow`, `pinch`,
  `puffs`, `sticks` (physics-driven: **adjust after watching the recording**), `taps`, `big_pop`, `drips`.
  If the demo script changes, update these and rerun (audio rebuilds automatically when the beat sheet is newer).
- `sheet`: six app seconds for `tools/sheet.sh` (the last one on the end card).

## Audio

Rebuild by hand (≈5 s):

```sh
/Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 blender/scripts/mix_clip.py --beats blender/scripts/beats/v1.json
```

- Music (synthesised, no samples): C – Am – F – G at 113.5 BPM. Marimba hook from frame 1, shaker enters halfway through
  bar 1, bass + soft kick + finger snaps from bar 2, kalimba counter-line bars 3–6, hook doubled on glockenspiel in bars
  5–6, breakdown in bar 7, music stops dead on the big pop (reverb tail only), end card = C add9 + marimba roll +
  glockenspiel run, letters "pip" in on a rising arpeggio.
- Pops (v34, user feedback "harsh"): soft felt music-box notes on C major pentatonic (G4–G5, `synth_audio.pop_soft`), the
  taps play a rising-then-falling run; the giant = round low bloop + soft bell chord (`pop_big_soft`). The old click +
  glassy glints (`pop_core`, `sparkle`) stay in the file for reference. The app plays the same pops plus a quiet ambient loop
  (`music_loop` → `app/assets/sfx/music.wav`: Cmaj9 – Am9 – Fmaj9 – G6/9, airy pad + kalimba, no bass below ~250 Hz so the
  breath detector's low-band gate ignores it).
- SFX: breath whoosh following the scripted envelope (1.3–4.4 s, then three brighter puffs), quiet film shimmer during the
  growth, wobbly bloop at the pinch-off (3.9), bubble burbles after each puff (5.1 / 6.0 / 6.9), soft ticks on sticks,
  crisp pops + droplet sparkle on the 7 taps, the big delicate pop at 14.0 with a longer sparkle shower, droplets
  landing (14.4–14.7), very quiet garden bed (breeze + 3 distant bird chirps).
- Master: 48 kHz stereo 24-bit, two-pass ffmpeg loudnorm (linear) + 4× oversampled look-ahead limiter.
  v1: **−14.0 LUFS integrated, true peak −1.6 dBTP** (limiter gain reduction ≈ 1.7 dB). Values in `render/audio/mix_v1.json`;
  promo.sh also prints the ebur128 summary of the exported clip (test clip after AAC: −14.0 LUFS, peak −1.4 dBFS).

### In-app SFX

`app/assets/sfx/`: `pop_1..pop_4.wav`, `pop_big.wav`, `bloop.wav`, `puff.wav`, `stick.wav` — mono 44.1 kHz 16-bit,
peak −1 dBFS, 10–50 KB each. Regenerate:

```sh
/Applications/Blender.app/Contents/Resources/5.2/python/bin/python3.13 blender/scripts/synth_audio.py
```

They are peak-normalised, so balance them in code (suggested: pops 0.6–0.8, pop_big 0.9, bloop 0.6, puff 0.35, stick 0.3;
randomise the pop variant and a ±8 % playback rate if available).

## Testing without a recording

`render/promo/test/screen.mp4` is a stand-in (0.8 s dark launch screen, then a gradient with moving circles and a white
progress bar at the top that fills over 18 s of app time — handy to check the sync):

```sh
PCT=50 WORKERS=1 LABEL=test tools/promo.sh --beats blender/scripts/beats/v1.json --screen render/promo/test/screen.mp4 \
    --out render/promo/soap-bubbles-demo-test.mp4
```
