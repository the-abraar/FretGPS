"""Tests for camera_hint: math verification, calibration projection, CSV output, and video processing."""

import math
import os
import subprocess
import sys
import tempfile
import cv2
import numpy as np

from camera_hint import (
    fret_from_ratio,
    ratio_from_fret,
    project_point_to_neck,
    write_csv,
    process_video,
)


def test_fret_math():
    # Nut
    assert abs(fret_from_ratio(0.0) - 0.0) < 1e-5
    assert abs(ratio_from_fret(0.0) - 0.0) < 1e-5

    # 12th fret (exact midpoint of scale length, octave)
    assert abs(fret_from_ratio(1.0) - 12.0) < 1e-5
    assert abs(ratio_from_fret(12.0) - 1.0) < 1e-5

    # Round trip for all frets 0 to 20
    for n in range(21):
        r = ratio_from_fret(float(n))
        n_calc = fret_from_ratio(r)
        assert abs(n_calc - n) < 1e-4, f"Mismatch at fret {n}: got {n_calc}"

    # Fret 5 is near r = 0.5017
    r5 = ratio_from_fret(5.0)
    assert 0.49 < r5 < 0.51
    assert abs(fret_from_ratio(r5) - 5.0) < 1e-4

    # Boundary conditions
    assert fret_from_ratio(-0.5) == 0.0
    assert fret_from_ratio(2.0) == 24.0


def test_neck_projection():
    nut = (100.0, 200.0)
    fret12 = (500.0, 200.0)  # horizontal neck, length 400 px

    # Point at nut
    r, perp = project_point_to_neck((100.0, 200.0), nut, fret12)
    assert abs(r - 0.0) < 1e-5
    assert abs(perp - 0.0) < 1e-5

    # Point at 12th fret
    r, perp = project_point_to_neck((500.0, 200.0), nut, fret12)
    assert abs(r - 1.0) < 1e-5
    assert abs(perp - 0.0) < 1e-5

    # Point at halfway (r = 0.5)
    r, perp = project_point_to_neck((300.0, 200.0), nut, fret12)
    assert abs(r - 0.5) < 1e-5
    assert abs(perp - 0.0) < 1e-5

    # Point with perpendicular offset of 30 px
    r, perp = project_point_to_neck((300.0, 230.0), nut, fret12)
    assert abs(r - 0.5) < 1e-5
    assert abs(perp - 30.0) < 1e-5

    # Angled neck (diagonal)
    nut = (50.0, 50.0)
    fret12 = (350.0, 450.0)  # dx=300, dy=400, len=500
    mid = (200.0, 250.0)
    r, perp = project_point_to_neck(mid, nut, fret12)
    assert abs(r - 0.5) < 1e-5
    assert abs(perp) < 1e-5


def test_csv_output():
    hints = [(0.0, 0.0), (0.25, 5.2), (0.50, 7.1)]
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".csv") as tmp:
        tmp_path = tmp.name

    try:
        write_csv(hints, tmp_path)
        with open(tmp_path) as f:
            lines = [line.strip() for line in f.readlines()]
        assert lines[0] == "t,fret"
        assert lines[1] == "0.00,0.0"
        assert lines[2] == "0.25,5.2"
        assert lines[3] == "0.50,7.1"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_video_pipeline():
    """Verify video loading, processing, and hint output end-to-end on a test video."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = f.name

    try:
        w, h, fps = 320, 240, 10
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(video_path, fourcc, fps, (w, h))
        for _ in range(10):  # 1 second
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            out.write(frame)
        out.release()

        nut = (50.0, 120.0)
        fret12 = (250.0, 120.0)
        hints = process_video(video_path, nut=nut, fret12=fret12, interval=0.25)
        assert len(hints) >= 4
        assert all(isinstance(t, float) and isinstance(f, float) for t, f in hints)
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)


if __name__ == "__main__":
    test_fret_math()
    test_neck_projection()
    test_csv_output()
    test_video_pipeline()
    print("ok")
