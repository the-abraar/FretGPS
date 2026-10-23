"""How far does audio alone get? Scores fretmap against GuitarSet (Xi et al., ISMIR 2018):
360 acoustic-guitar excerpts recorded with a mic, with string + fret ground truth from a
hexaphonic pickup. Download annotation.zip and audio_mono-mic.zip from
https://zenodo.org/records/3371780 and unzip both into one folder.

    python eval_guitarset.py GUITARSET_DIR                      # placement only, true pitches (no audio)
    python eval_guitarset.py GUITARSET_DIR --audio [--phone]    # pYIN on the mic audio of the solos
    python eval_guitarset.py GUITARSET_DIR --notes BP_DIR       # Basic Pitch note events (solos + chords)

Add --around to the last two to give each take its (ideal) "around fret N" hint.
"""
import json
import os
import subprocess
import sys
from multiprocessing import Pool

import numpy as np

from fretmap import MAX_FRET, OPEN, SR, assign, detect_notes, load, read_basic_pitch

ROOT = sys.argv[1] if len(sys.argv) > 1 else sys.exit(__doc__)
AUDIO = "--audio" in sys.argv
NOTES = sys.argv[sys.argv.index("--notes") + 1] if "--notes" in sys.argv else None


def truth(stem):
    with open(f"{ROOT}/annotation/{stem}.jams") as f:
        d = json.load(f)
    notes = []
    for a in d["annotations"]:
        if a["namespace"] == "note_midi":
            s = int(a["annotation_metadata"]["data_source"])
            for o in a["data"]:
                m = round(o["value"])
                notes.append({"start": o["time"], "end": o["time"] + o["duration"], "midi": m, "string": s, "fret": m - OPEN[s]})
    return notes


def lowest_fret(notes):
    """Baseline: what a tuner app would do, every pitch on the lowest fret that plays it."""
    for n in notes:
        n["string"] = max(s for s in range(6) if 0 <= n["midi"] - OPEN[s] <= MAX_FRET)
    return notes


def hinted(notes, ref, window=None):
    """Ideal hand-position hint taken from the ground truth: the take's median fret, or
    with a window (seconds) the median fret of the true notes around each note."""
    def median_fret(rs):
        f = [r["fret"] for r in rs if r["fret"]]
        return float(np.median(f)) if f else None

    take = median_fret(ref) or 0.0
    for n in notes:
        n["around"] = take if window is None else median_fret([r for r in ref if abs(r["start"] - n["start"]) <= window]) or take
    return notes


def match(pred, ref, tol=0.05):
    """One-to-one pairs with the same pitch and onsets within 50 ms (mir_eval's default)."""
    pairs, used = [], set()
    for p in pred:
        js = [j for j, r in enumerate(ref) if j not in used and r["midi"] == p["midi"] and abs(r["start"] - p["start"]) <= tol]
        if js:
            j = min(js, key=lambda j: abs(ref[j]["start"] - p["start"]))
            used.add(j)
            pairs.append((p, ref[j]))
    return pairs


def phone(path):
    # stand-in for a cheap phone mic: bass under 120 Hz rolled off, then a 64 kbps AAC round trip
    enc = ["ffmpeg", "-v", "error", "-i", path, "-af", "highpass=f=120", "-c:a", "aac", "-b:a", "64k", "-f", "adts", "-"]
    dec = ["ffmpeg", "-v", "error", "-i", "-", "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"]
    aac = subprocess.run(enc, stdout=subprocess.PIPE, check=True).stdout
    return np.frombuffer(subprocess.run(dec, input=aac, stdout=subprocess.PIPE, check=True).stdout, np.float32)


def score(stem):
    ref = truth(stem)
    if not (AUDIO or NOTES):  # true pitches, strings hidden. Dropped notes count as wrong.
        hide = lambda: [{**r, "true": r["string"]} for r in ref]  # placers overwrite "string"
        placed = [lowest_fret(hide()), assign(hide()), assign(hinted(hide(), ref)), assign(hinted(hide(), ref, 2))]
        return [sum(n["string"] == n["true"] for n in p) for p in placed] + [len(ref)]
    if AUDIO:
        wav = f"{ROOT}/audio_mono-mic/{stem}_mic.wav"
        notes = detect_notes(phone(wav) if "--phone" in sys.argv else load(wav))
    else:
        notes = read_basic_pitch(f"{NOTES}/{stem}_mic_basic_pitch.csv")
    pred = assign(hinted(notes, ref) if "--around" in sys.argv else notes)
    pairs = match(pred, ref)
    return len(pred), len(ref), len(pairs), sum(p["string"] == r["string"] for p, r in pairs)


if __name__ == "__main__":
    stems = sorted(f[:-5] for f in os.listdir(f"{ROOT}/annotation") if f.endswith(".jams"))
    if AUDIO or NOTES:
        print("| excerpts | notes | note precision | note recall | note F1 | right string (of found notes) |")
    else:
        print("| excerpts | notes | lowest fret | fretmap | fretmap + one hint per take | fretmap + rolling hint (±2 s) |")
    print("|---" * 6 + "|")
    for kind in ("solo", "comp"):
        if AUDIO and kind == "comp":
            continue  # pYIN is monophonic; chords go through --notes
        group = [s for s in stems if s.endswith(kind)]
        with Pool() as pool:
            t = np.array(pool.map(score, group)).sum(0)
        if AUDIO or NOTES:
            p, r = t[2] / t[0], t[2] / t[1]
            cells, total = [p, r, 2 * p * r / (p + r), t[3] / t[2]], t[1]
        else:
            cells, total = t[:4] / t[4], t[4]
        print(f"| {kind} ({len(group)}) | {total} | " + " | ".join(f"{c:.1%}" for c in cells) + " |")
