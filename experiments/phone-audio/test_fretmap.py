"""Self-check on a synthesized riff: python test_fretmap.py (needs ffmpeg on PATH)"""
import os
import subprocess
import tempfile
import time

import numpy as np

from fretmap import BEND_MIN, MAX_SECONDS, OPEN, SR, assign, candidates, detect_notes, load, tab


def pluck(midi, dur=0.4, bend_cents=0):
    t = np.arange(int(dur * SR)) / SR
    glide = bend_cents / 100 * np.clip((t - 0.12) / 0.12, 0, 1)  # bend rises 120-240 ms after the attack
    phase = 2 * np.pi * np.cumsum(440 * 2 ** ((midi + glide - 69) / 12)) / SR
    return sum(np.sin(k * phase) / k * np.exp(-t * (2 + k)) for k in range(1, 9)).astype(np.float32)


riff = [(45, 0), (48, 0), (50, 0), (52, 0), (52, 0), (55, 0), (57, 0), (62, 200), (64, 0)]
notes = detect_notes(np.concatenate([pluck(m, bend_cents=b) for m, b in riff]))

assert [n["midi"] for n in notes] == [m for m, _ in riff], notes  # the repeated E3 needs the onset split
bends = [n["bend_cents"] for n in notes]
assert 170 <= bends[7] <= 230 and max(bends[:7] + bends[8:]) < BEND_MIN, bends  # bend kept on its fret, not read as a new note

placed = assign(notes)
assert all(OPEN[n["string"]] + n["fret"] == n["midi"] for n in placed)
assert {s for s, _ in candidates([40, 47, 52])[0]} == {0, 1, 2}  # an E5 power chord uses three different strings
t0 = time.time()
assert candidates(list(range(55, 69))) == [] and time.time() - t0 < 0.1  # 14 notes can't fit 6 strings: reject before enumerating

with tempfile.TemporaryDirectory() as d:
    ff = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi"]
    # a 4-hour silent FLAC is ~1.5 MB on disk; load() must stop decoding at MAX_SECONDS
    subprocess.run(ff + ["-i", "anullsrc=r=8000:cl=mono", "-t", "14400", "-c:a", "flac", "-sample_fmt", "s16", f"{d}/long.flac"], check=True)
    assert len(load(f"{d}/long.flac")) <= MAX_SECONDS * SR
    # a bare name that looks like a URL must open the local file, not reach the network
    subprocess.run(ff + ["-i", "sine=f=440:d=1", f"{d}/http:127.0.0.1:1#x.wav"], check=True)
    cwd = os.getcwd()
    os.chdir(d)
    try:
        assert len(load("http:127.0.0.1:1#x.wav")) > 0.9 * SR
    finally:
        os.chdir(cwd)

print(tab(placed))
print("ok")
