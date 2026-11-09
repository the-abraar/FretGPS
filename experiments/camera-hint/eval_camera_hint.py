"""Evaluate camera hint accuracy against ground-truth frets.

Usage:
    python eval_camera_hint.py hints.csv truth.csv
    python eval_camera_hint.py --synthetic  # self-check benchmark

Reports Median Absolute Fret Error, Mean Absolute Fret Error, and percentage
of estimates within 1 and 2 frets of ground truth.
"""

import argparse
import csv
import math
import sys
import numpy as np


def load_csv(path):
    rows = []
    with open(path) as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for r in reader:
            if len(r) >= 2:
                try:
                    rows.append((float(r[0]), float(r[1])))
                except ValueError:
                    continue
    return rows


def evaluate(hints, truth, max_time_diff=0.15):
    """Align hints and ground truth by timestamp and calculate error metrics."""
    errors = []
    for t_pred, f_pred in hints:
        # Find closest ground truth within max_time_diff
        matches = [f_true for t_true, f_true in truth if abs(t_true - t_pred) <= max_time_diff]
        if matches:
            f_true = matches[0]
            errors.append(abs(f_pred - f_true))

    if not errors:
        return None

    errors = np.array(errors)
    return {
        "count": len(errors),
        "median_error": float(np.median(errors)),
        "mean_error": float(np.mean(errors)),
        "within_1_fret": float(np.mean(errors <= 1.0) * 100),
        "within_2_frets": float(np.mean(errors <= 2.0) * 100),
    }


def main():
    ap = argparse.ArgumentParser(description="Evaluate camera hint accuracy against ground truth.")
    ap.add_argument("hints", nargs="?", help="Path to hints.csv")
    ap.add_argument("truth", nargs="?", help="Path to ground truth truth.csv")
    ap.add_argument("--synthetic", action="store_true", help="Run benchmark on synthetic test cases")
    args = ap.parse_args()

    if args.synthetic or (not args.hints and not args.truth):
        # Synthetic evaluation benchmark
        # Simulates 4 clips: Open chords (fret 0-2), Chromatic 0-12, Riff at 5-7, Solo at 12-15
        clips = {
            "01-open-position (frets 0-3)": (
                [(t * 0.25, 1.0 + 0.3 * np.sin(t)) for t in range(20)],
                [(t * 0.25, 1.0) for t in range(20)],
            ),
            "02-chromatic-scale (frets 0-12)": (
                [(t * 0.25, min(12.0, t * 0.6) + 0.4 * np.cos(t)) for t in range(25)],
                [(t * 0.25, min(12.0, t * 0.6)) for t in range(25)],
            ),
            "03-riff-5th-pos (frets 5-8)": (
                [(t * 0.25, 5.2 + 0.5 * (t % 4)) for t in range(20)],
                [(t * 0.25, 5.0 + 0.5 * (t % 4)) for t in range(20)],
            ),
            "04-blues-lick-12th (frets 12-15)": (
                [(t * 0.25, 12.3 + 0.6 * np.sin(t * 0.8)) for t in range(20)],
                [(t * 0.25, 12.0 + 0.6 * np.sin(t * 0.8)) for t in range(20)],
            ),
        }
        print("| Clip | Median Fret Error | Mean Error | Within <= 1 Fret | Within <= 2 Frets |")
        print("|---|---|---|---|---|")
        for name, (pred, true) in clips.items():
            metrics = evaluate(pred, true)
            print(f"| {name} | {metrics['median_error']:.2f} frets | {metrics['mean_error']:.2f} frets | "
                  f"{metrics['within_1_fret']:.1f}% | {metrics['within_2_frets']:.1f}% |")
        return

    hints = load_csv(args.hints)
    truth = load_csv(args.truth)
    metrics = evaluate(hints, truth)
    if not metrics:
        sys.exit("No aligned samples found between hints and truth.")

    print(f"Evaluated {metrics['count']} time points:")
    print(f"  Median Absolute Fret Error: {metrics['median_error']:.2f} frets")
    print(f"  Mean Absolute Fret Error:   {metrics['mean_error']:.2f} frets")
    print(f"  Within <= 1 fret:          {metrics['within_1_fret']:.1f}%")
    print(f"  Within <= 2 frets:         {metrics['within_2_frets']:.1f}%")


if __name__ == "__main__":
    main()
