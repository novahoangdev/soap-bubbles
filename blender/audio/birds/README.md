# Real birdsong for the 3D garden's soundtrack

Field recordings from Wikimedia Commons, all **public domain or CC0** (no attribution required; credited here anyway).
Used by `blender/scripts/mix_clip.py` when the beat sheet's music style is `"lofi"` or `"piano"` (the garden's bed instead of the
synthesised chirps, which the user found unnatural).

| File | Source (Wikimedia Commons) | Recordist | Licence | What |
|---|---|---|---|---|
| `dawn_chorus_a.flac`, `dawn_chorus_b.flac` | [File:Dawnchorus-uk.ogg](https://commons.wikimedia.org/wiki/File:Dawnchorus-uk.ogg) | Silas S. Brown | Public domain | A dawn chorus in Shipton Gorge, West Dorset, UK; two 56 s stretches (from 5:00 and 21:10, picked by birdsong-band energy over low rumble), one per stereo side for a wide bed |
| `blackbird_forest.flac` | [File:Turdus merula 2.ogg](https://commons.wikimedia.org/wiki/File:Turdus_merula_2.ogg) | Oona Räisänen (Mysid) | Public domain | A common blackbird singing in a forest in southern Finland (stereo, 25 s) |
| `blackcap_chaffinch.flac` | [File:Gentle breeze and birds singing.ogg](https://commons.wikimedia.org/wiki/File:Gentle_breeze_and_birds_singing.ogg) | ezwa | Public domain | A blackcap and a chaffinch in a gentle breeze (33 s) |
| `garden_birds.flac` | [File:Birds singing in garden.ogg](https://commons.wikimedia.org/wiki/File:Birds_singing_in_garden.ogg) | ezwa | Public domain | Birds singing in a garden in the afternoon (49 s) |

Processing (ffmpeg): high-pass 380 Hz (wind and traffic rumble), low-pass 11 kHz, light FFT denoise (`afftdn nr 12`),
loudness-normalised to about −24 LUFS, 48 kHz FLAC. The dawn-chorus stretches fade in and out over 1 s.
