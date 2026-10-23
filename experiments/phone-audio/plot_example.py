"""Draws the fret-map figure in docs/images: GuitarSet ground truth vs fretmap on one solo,
without and with an "around fret N" hint.

    python plot_example.py GUITARSET_DIR STEM OUT.png
"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch, Rectangle

from eval_guitarset import ROOT, match, truth
from fretmap import NAMES, assign, detect_notes, load

STEM, OUT, UNTIL = sys.argv[2], sys.argv[3], 12.0
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
RIGHT, WRONG, EXTRA, TRUTH = "#2a78d6", "#eb6834", "#c3c2b7", "#52514e"

ref = truth(STEM)
around = round(float(np.median([r["fret"] for r in ref if r["fret"]])))
heard = detect_notes(load(f"{ROOT}/audio_mono-mic/{STEM}_mic.wav"))
plain = assign([dict(n) for n in heard])
hinted = assign([{**n, "around": around} for n in heard])
ref = [r for r in ref if r["start"] < UNTIL]


def draw(ax, notes, fill, title):
    ax.set_facecolor(SURFACE)
    for s in range(6):
        ax.axhline(s, color=GRID, lw=1, zorder=0)
    for n in notes:
        c = fill(n)
        ax.add_patch(Rectangle((n["start"], n["string"] - 0.36), max(n["end"] - n["start"], 0.05), 0.72, fc=c, ec=SURFACE, lw=2))
        ax.text(n["start"] + 0.03, n["string"], n["fret"], va="center", fontsize=7.5, color=INK if c == EXTRA else SURFACE, clip_on=True)
    ax.set_yticks(range(6), NAMES, color=MUTED)
    ax.set_ylim(-0.6, 5.6)
    ax.set_xlim(0, UNTIL)
    ax.tick_params(length=0, colors=MUTED)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_title(title, loc="left", fontsize=10, color=INK)


def scored(pred):
    pred = [p for p in pred if p["start"] < UNTIL]
    paired = {id(p): r for p, r in match(pred, ref)}
    color = lambda p: EXTRA if id(p) not in paired else RIGHT if paired[id(p)]["string"] == p["string"] else WRONG
    return pred, color, sum(color(p) == RIGHT for p in pred)


fig, axes = plt.subplots(3, 1, figsize=(12, 8.2), sharex=True, facecolor=SURFACE)
draw(axes[0], ref, lambda n: TRUTH, "What was played (hexaphonic pickup = ground truth). Numbers are frets.")
pred, color, right = scored(plain)
draw(axes[1], pred, color, f"fretmap.py from the mic alone: {right} of {len(ref)} notes on the right string")
pred, color, right = scored(hinted)
draw(axes[2], pred, color, f'Same audio + one hint, "around fret {around}": {right} of {len(ref)} on the right string')
axes[2].set_xlabel("seconds", color=MUTED)
axes[0].legend(handles=[Patch(color=RIGHT, label="right note, right string"), Patch(color=WRONG, label="right note, wrong string"),
                        Patch(color=EXTRA, label="extra or wrong note")],
               loc="lower right", bbox_to_anchor=(1, 1.08), ncol=3, frameon=False, fontsize=8.5, labelcolor=INK)
fig.suptitle(f"GuitarSet {STEM}, first {UNTIL:.0f} s", x=0.01, ha="left", fontsize=12, color=INK)
fig.tight_layout()
fig.savefig(OUT, dpi=150, facecolor=SURFACE)
