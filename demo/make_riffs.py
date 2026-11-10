"""Writes demo/data/riff_{lowest,least,around7}.json: three fretmap placements of one GuitarSet solo.

    python demo/make_riffs.py GUITARSET_DIR          # same folder eval_guitarset.py takes

Placement only: the true pitches go in with the strings hidden, like the "with true pitches" rows of
docs/phone-audio-experiment.md. The solo is picked by rule, not by eye: of the solos whose median
fret rounds to 7, take the one whose first 12 s score closest to the whole-dataset 43.4% / 79.3%.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "experiments" / "phone-audio"))
from eval_guitarset import ROOT, lowest_fret, truth  # noqa: E402  (reads GUITARSET_DIR from argv)
from fretmap import OPEN, assign  # noqa: E402

import numpy as np  # noqa: E402

UNTIL, AROUND, OUT = 12.0, 7, Path(__file__).resolve().parent / "data"


def excerpt(stem):
    return [{k: n[k] for k in ("start", "end", "midi")} | {"true_string": n["string"], "true_fret": n["fret"]}
            for n in sorted(truth(stem), key=lambda n: n["start"]) if n["start"] < UNTIL]


def placements(notes):
    hide = lambda **extra: [dict(n, **extra) for n in notes]
    lowest = [dict(n, fret=n["midi"] - OPEN[n["string"]]) for n in lowest_fret(hide())]  # lowest_fret sets the string only
    return {"lowest": lowest, "least": assign(hide()), f"around{AROUND}": assign(hide(around=AROUND))}


def right(placed, n):
    return sum(p["string"] == p["true_string"] for p in placed) / n


def pick():
    best = None
    for f in sorted(os.listdir(f"{ROOT}/annotation")):
        stem = f[:-5]
        if not stem.endswith("solo"):
            continue
        frets = [n["fret"] for n in truth(stem) if n["fret"]]
        notes = excerpt(stem)
        if round(float(np.median(frets))) != AROUND or not 20 <= len(notes) <= 60:
            continue
        p = placements(notes)
        gap = abs(right(p["least"], len(notes)) - 0.434) + abs(right(p[f"around{AROUND}"], len(notes)) - 0.793)
        if best is None or gap < best[0]:
            best = (gap, stem)
    return best[1]


if __name__ == "__main__":
    stem = pick()
    notes = excerpt(stem)
    for name, placed in placements(notes).items():
        doc = {
            "source": f"GuitarSet {stem}, first {UNTIL:.0f} s (Xi et al., ISMIR 2018, CC BY 4.0, zenodo.org/records/3371780)",
            "placement": name, "notes_in": len(notes),
            "right_string": sum(p["string"] == p["true_string"] for p in placed),
            "notes": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in p.items() if k != "around"}
                      for p in placed],
        }
        (OUT / f"riff_{name}.json").write_text(json.dumps(doc, indent=1) + "\n")
        print(f"{name:>8}: {doc['right_string']}/{len(notes)} on the right string")
