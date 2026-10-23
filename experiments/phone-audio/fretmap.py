"""Phone recording -> fret map, with no FretGPS hardware.

    python fretmap.py riff.m4a                 # ASCII tab
    python fretmap.py riff.m4a --json          # event stream (same shape the hardware will emit)
    python fretmap.py riff.m4a --around 7      # "I'm playing around fret 7": fixes most wrong-string guesses
    python fretmap.py riff_basic_pitch.csv     # chords: note events from Spotify's Basic Pitch

Single notes come from pYIN pitch tracking plus onset detection. Audio alone cannot
say which string a pitch came from, so the (string, fret) choice is a Viterbi path
that keeps the fretting hand moving as little as possible.
"""
import argparse
import csv
import itertools
import json
import subprocess

import librosa
import numpy as np
from scipy.signal import medfilt

SR = 22050
HOP = 256  # 11.6 ms per frame
OPEN = [40, 45, 50, 55, 59, 64]  # MIDI of open strings, index 0 = low E (standard tuning)
NAMES = ["E", "A", "D", "G", "B", "e"]
MAX_FRET = 20
MAX_SPAN = 4  # widest fret stretch allowed inside one chord
MIN_FRAMES = 5  # notes shorter than ~58 ms are pitch-tracker noise
JUMP = 0.7  # semitones between two frames: a new fretted note (hammer-on, pull-off, slide step), not a bend
BEND_MIN = 50  # cents above the attack pitch before the tab marks a bend
CHORD_WINDOW = 0.03  # seconds: notes starting this close together are one chord
NUT_PULL = 0.1  # per fret: with equal hand movement and no hint, prefer the lower position
HINT_PULL = 1.0  # per fret away from a note's "around" hint


def load(path):
    # ffmpeg decodes whatever the phone saved (m4a, aac, wav, ...) to mono float32
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"]
    return np.frombuffer(subprocess.run(cmd, stdout=subprocess.PIPE, check=True).stdout, np.float32)


def detect_notes(y):
    """Monophonic notes: [{start, end, midi, hz, bend_cents}]. Chords come out as noise."""
    f0, voiced, _ = librosa.pyin(y, fmin=70, fmax=1400, sr=SR, frame_length=2048, hop_length=HOP)
    midi = librosa.hz_to_midi(f0)
    onset = np.zeros(len(f0), bool)
    hits = librosa.onset.onset_detect(y=y, sr=SR, hop_length=HOP)
    onset[hits[hits < len(f0)]] = True

    runs, cur = [], None
    for i in np.flatnonzero(voiced):
        if cur and i == cur[-1] + 1 and not onset[i] and abs(midi[i] - midi[i - 1]) < JUMP:
            cur.append(i)
        else:
            cur = [i]
            runs.append(cur)

    notes = []
    for r in runs:
        if len(r) < MIN_FRAMES:
            continue
        m = midi[r]
        attack = float(np.median(m[:5]))  # the fret is the pitch at the attack; anything above it later is a bend
        notes.append({
            "start": r[0] * HOP / SR,
            "end": (r[-1] + 1) * HOP / SR,
            "midi": round(attack),
            "hz": round(float(librosa.midi_to_hz(attack)), 1),
            "bend_cents": round(max(0.0, medfilt(m, 5).max() - attack) * 100),  # median: ignore 1-2 frame glides into the next note
        })
    return notes


def read_basic_pitch(path):
    """Notes from `basic-pitch OUT_DIR rec.wav --save-note-events`. Handles chords; bends are not read."""
    with open(path) as f:
        rows = list(csv.reader(f))[1:]
    return [{"start": float(r[0]), "end": float(r[1]), "midi": int(r[2]),
             "hz": round(float(librosa.midi_to_hz(int(r[2]))), 1), "bend_cents": 0} for r in rows]


def chords(notes):
    groups = []
    for n in sorted(notes, key=lambda n: n["start"]):
        if groups and n["start"] - groups[-1][0]["start"] < CHORD_WINDOW:
            groups[-1].append(n)
        else:
            groups.append([n])
    return groups


def candidates(pitches):
    """Every playable (string, fret) assignment for pitches sounding together."""
    options = [[(s, p - OPEN[s]) for s in range(6) if 0 <= p - OPEN[s] <= MAX_FRET] for p in pitches]
    out = []
    for combo in itertools.product(*options):
        fretted = [f for _, f in combo if f]
        if len({s for s, _ in combo}) == len(combo) and (not fretted or max(fretted) - min(fretted) <= MAX_SPAN):
            out.append(combo)
    return out


def position(combo):
    fretted = [f for _, f in combo if f]
    return min(fretted) if fretted else 0


def assign(notes):
    """Set note["string"] and note["fret"] along the least-hand-movement path. A note may carry
    "around" (roughly where the hand is: from the user, or later a camera) to pull the path there.
    Returns the assigned notes; pitches no string can play are dropped."""
    steps = [(g, c) for g in chords(notes) if (c := candidates([n["midi"] for n in g]))]
    if not steps:
        return []
    pos = [np.array([position(x) for x in c], float) for _, c in steps]
    pull = [HINT_PULL * np.abs(p - g[0]["around"]) if "around" in g[0] else NUT_PULL * p for (g, _), p in zip(steps, pos)]
    total, back = pull[0], []
    for i in range(1, len(steps)):
        # shortcut: cost is fret distance only, ignores fingering and string skips; a learned model is the upgrade
        trans = total[:, None] + np.abs(pos[i - 1][:, None] - pos[i][None, :])
        back.append(trans.argmin(0))
        total = trans.min(0) + pull[i]
    k = int(total.argmin())
    for i in range(len(steps) - 1, -1, -1):
        group, combos = steps[i]
        for n, (s, f) in zip(group, combos[k]):
            n["string"], n["fret"] = s, f
        if i:
            k = int(back[i - 1][k])
    return [n for g, _ in steps for n in g]


def tab(notes, width=72):
    rows, blocks = [""] * 6, []
    for g in chords(notes):
        cell = {n["string"]: f'{n["fret"]}{"b" if n.get("bend_cents", 0) >= BEND_MIN else ""}' for n in g}
        w = max(map(len, cell.values())) + 1
        rows = [r + cell.get(s, "").ljust(w, "-") for s, r in enumerate(rows)]
        if len(rows[0]) >= width:
            blocks.append(rows)
            rows = [""] * 6
    blocks.append(rows)
    return "\n\n".join("\n".join(f"{NAMES[s]}|-{b[s]}|" for s in reversed(range(6))) for b in blocks if b[0])


def event(n):
    # strings numbered like guitarists do: 1 = high e, 6 = low E
    return {
        "t": round(n["start"], 3), "dur": round(n["end"] - n["start"], 3),
        "string": 6 - n["string"], "fret": n["fret"],
        "note": librosa.midi_to_note(n["midi"], unicode=False), "hz": n["hz"], "bend_cents": n["bend_cents"],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Phone recording -> fret map (tab or JSON note events)")
    ap.add_argument("recording", help="audio file, or a Basic Pitch note-events .csv for chords")
    ap.add_argument("--json", action="store_true", help="print note events instead of tab")
    ap.add_argument("--around", type=int, metavar="FRET", help="roughly where your fretting hand is")
    a = ap.parse_args()
    notes = read_basic_pitch(a.recording) if a.recording.endswith(".csv") else detect_notes(load(a.recording))
    if a.around is not None:
        for n in notes:
            n["around"] = a.around
    notes = assign(notes)
    print(json.dumps([event(n) for n in notes], indent=1) if a.json else tab(notes))
