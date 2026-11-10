# LEARNINGS

What Phase 0 taught us, in one page. Detail and sources: [docs/phone-audio-experiment.md](docs/phone-audio-experiment.md).
Interactive version: [demo/index.html](demo/index.html). It runs on one real GuitarSet solo, and you move the hint yourself.

## Method

- **Question:** can a phone recording alone produce the fret map (which string, which fret, bends, mutes)?
- **Prototype:** [`fretmap.py`](experiments/phone-audio/fretmap.py). pYIN finds pitch and onsets, and a bend is any rise in cents after the attack.
  A Viterbi pass over every playable (string, fret) then picks the path that moves the fretting hand least,
  with chords kept within a 4-fret span. `--around N` pulls that path toward fret N.
- **Test data:** [GuitarSet](https://zenodo.org/records/3371780) (Xi et al., ISMIR 2018, CC BY 4.0). It has 360 excerpts
  of about 30 s on one acoustic guitar, with the true string and fret from a hexaphonic pickup.
- **Placement-only scoring:** the true pitches go in with the strings hidden, which separates "where" from "what".
  Reproduce with `python eval_guitarset.py GUITARSET_DIR`. Rerun on 2026-11-10, it gave the same numbers as below.
- **Hints are ideal.** They are taken from the ground truth (the take's median fret, or the median within ±2 s).
  So every hint row below is an **upper bound**.

## Results (180 solos, 16,861 notes; placement only)

| Placement | Right string |
|---|---|
| Lowest fret (what a tuner app shows) | 31.0% |
| Least hand movement (`fretmap.py`) | **43.4%** |
| + one "around fret N" per take (**upper bound**, ideal hint) | **79.3%** |
| + rolling hint over ±2 s, like a camera would see (**upper bound**, ideal hint) | **88.6%** |

On chords (180 comps), the same four placements score 50.7% / 71.9% / 80.8% / 87.0%. The last two are **upper bounds**.
End to end from audio, Basic Pitch finds 82% of single notes (F1) and 71% of chord notes. A simulated
cheap phone (no bass under 120 Hz, 64 kbps AAC) costs 3.6 points of note F1 and nothing in string accuracy.

## What we learned

1. **String ID is a hand-position problem, not an audio problem.** When audio alone gets the string wrong,
   it moves the whole line to another place on the neck, so the shape is right and the place is wrong. One number
   ("around fret N") nearly doubles right-string placement (43% → 79%, **upper bound**). Smarter
   movement rules didn't help: a hand-window model scored 35–43% across seven settings.
2. **A wrong hint is worse than none.** In the demo's solo (`04_Jazz1-130-D`, first 12 s, 28 notes),
   no hint gets 12/28 right, "around 5" gets 23/28 and "around 7" gets 22/28 (**upper bounds**). "Around 12" gets 1/28.
   A real hint source has to be roughly right, or the app has to let you correct it quickly.
3. **TabCNN doesn't travel.** A CNN trained on GuitarSet gets about 90% of found pitches on the right string,
   but only when it is tested on the same guitar and mic. Pedroza et al. (DAFx 2024, [arXiv 2405.14679](https://arxiv.org/abs/2405.14679))
   show it degrading on other guitars and tones. A phone-only string ID learned from timbre would need
   calibrating per guitar. A position hint doesn't.
4. **The phone is not the bottleneck.** Its mic and codec cost little. What limits the result is the
   one-pitch tracker (pYIN) and the missing hand position.
5. **What only hardware gets:** muting, exactly which strings rang in a chord, and ≥ 95% string ID. That is why the
   String-ID clip becomes the premium tier, not the only way to get a fret map.

## Prior art

- **Hex pickups** already sense each string separately: Roland GK, Fishman TriplePlay, and Graph Tech ghost piezo
  saddles with the Hexpander. FretGPS has to win on being a removable clip, on working with acoustics, and on the
  app. These pickups could also feed the same note-event stream.
- **TabCNN** (Wiggins & Kim, ISMIR 2019) is learned tablature from audio. See point 3 for its limits.
- **Basic Pitch** (Spotify, ICASSP 2022) does polyphonic note transcription. It is the best note detector we tried.
- **Tuner and tab apps** show the lowest fret: 31% right string on solos.

## Physics errors in the concept art

The concept art ([docs/images/](docs/images/)) is a starting point, not a spec. [PLAN.md §6 and §8](docs/PLAN.md) has the full table.

- Six 20–27 mm piezo discs can't sit side by side. The strings are ~10.5 mm apart at the bridge, about 55 mm from E to e.
- A TL072 isn't rated for a 3.3 V supply, and 40–60 dB of gain would likely clip a piezo under string tension.
  The real issue is impedance, so use a rail-to-rail CMOS op-amp biased at mid-rail.
- An 80 Hz high-pass cuts the low E fundamental (82.4 Hz; drop D is 73.4 Hz). Use ~60 Hz.
- The ADS1115 tops out at 860 samples/s, which is far too slow for audio.
- The app mock's "G string · 196.0 Hz · fret 3" is the open string. The 3rd fret is 233.1 Hz.
- `{string: 3, pitch: 146.8Hz}` can't happen. D3 is below the open G string.
- "Zero crosstalk" is not a metric. Use "≥ 12 dB separation between adjacent strings at the attack" instead.
- "< $50" is a wish. Budget ~$60–100 for the first build.

## Limits

GuitarSet is one acoustic guitar on a good studio mic. The hint weights (`NUT_PULL`, `HINT_PULL`, the 4-fret span)
were picked by hand on this same data. The next measurement is a *real* hint (your "around N", a camera,
or a headstock distance sensor) on your own recordings: Phase 0b.
