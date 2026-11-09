"""Extract hand-position hints from video of guitar playing using MediaPipe.

Outputs a CSV of (t, fret) rows, matching the `--hints` format for fretmap.py:

    python camera_hint.py video.mp4 --out hints.csv
    python camera_hint.py video.mp4 --out hints.csv --calib calib.json
    python camera_hint.py video.mp4 --nut 210,180 --fret12 540,320 --out hints.csv

Guitar fret spacing follows the equal-temperament rule:
    d_n = L * (1 - 2^(-n/12))
where L is the scale length (Nut to Bridge), and the 12th fret is at d_12 = L / 2.
Thus, the fractional position r relative to the 12th fret is:
    r = d_n / d_12 = 2 * (1 - 2^(-n/12))
Inverting this gives the continuous fret position for any detected hand point:
    n = -12 * log2(1 - r / 2)
"""

import argparse
import csv
import hashlib
import json
import math
import os
import sys
import urllib.request

import cv2
import numpy as np

# Landmark names to indices in MediaPipe Hands
LANDMARK_MAP = {
    "wrist": 0,
    "thumb_tip": 4,
    "index_mcp": 5,   # knuckle at base of index finger (default)
    "index_pip": 6,
    "index_tip": 8,
    "middle_mcp": 9,
    "middle_tip": 12,
}

# Pinned model version; the hash is checked before MediaPipe loads the file.
TASK_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
TASK_MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"


def ensure_model(model_path):
    """Download the pinned hand landmarker model if missing; refuse it unless its SHA-256 matches."""
    if not os.path.exists(model_path):
        print(f"Downloading hand landmarker model to {model_path}...", file=sys.stderr)
        tmp = model_path + ".part"
        urllib.request.urlretrieve(TASK_MODEL_URL, tmp)
        os.replace(tmp, model_path)
    with open(model_path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    if digest != TASK_MODEL_SHA256:
        os.remove(model_path)
        raise RuntimeError(f"{model_path} failed its SHA-256 check (got {digest}); removed it, re-run to download again")


def fret_from_ratio(r: float) -> float:
    """Compute continuous fret position from fractional distance r along the neck
    (Nut = 0.0, 12th fret = 1.0)."""
    if r <= 0.0:
        return 0.0
    if r >= 1.95:
        return 24.0
    return max(0.0, -12.0 * math.log2(1.0 - r / 2.0))


def ratio_from_fret(n: float) -> float:
    """Compute fractional distance r along the neck for fret n."""
    return 2.0 * (1.0 - 2.0 ** (-n / 12.0))


def project_point_to_neck(p, nut, fret12):
    """Project 2D point p onto neck axis defined by nut -> fret12.

    Returns:
        ratio (float): distance along neck normalized so nut=0.0, fret12=1.0.
        perp_dist (float): perpendicular distance from p to the neck line.
    """
    u = np.array([fret12[0] - nut[0], fret12[1] - nut[1]], dtype=float)
    d12 = np.linalg.norm(u)
    if d12 < 1e-6:
        return 0.0, 0.0
    unit_u = u / d12
    w = np.array([p[0] - nut[0], p[1] - nut[1]], dtype=float)
    proj = float(np.dot(w, unit_u))
    ratio = proj / d12
    perp = float(np.linalg.norm(w - proj * unit_u))
    return ratio, perp


class HandTracker:
    """Wrapper supporting both modern MediaPipe Tasks (>=1.0) and Solutions (0.10.x)."""

    def __init__(self, model_cache_dir=None):
        import mediapipe as mp
        self.mp = mp
        self.mode = None
        self.detector = None

        if hasattr(mp, "solutions") and hasattr(mp.solutions, "hands"):
            # Legacy MediaPipe Solutions API
            self.mode = "solutions"
            self.detector = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        else:
            # Modern MediaPipe Tasks API
            self.mode = "tasks"
            from mediapipe.tasks.python import BaseOptions
            from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

            cache_dir = model_cache_dir or os.path.dirname(os.path.abspath(__file__))
            model_path = os.path.join(cache_dir, "hand_landmarker.task")
            ensure_model(model_path)

            options = HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=model_path),
                running_mode=RunningMode.IMAGE,
                num_hands=2,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.detector = HandLandmarker.create_from_options(options)

    def find_hands(self, frame_bgr):
        """Returns list of hands, each hand being a list of 21 (x_px, y_px) coordinates."""
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        hands_px = []

        if self.mode == "solutions":
            results = self.detector.process(rgb)
            if results and results.multi_hand_landmarks:
                for hand_lms in results.multi_hand_landmarks:
                    pts = [(lm.x * w, lm.y * h) for lm in hand_lms.landmark]
                    hands_px.append(pts)
        elif self.mode == "tasks":
            mp_image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
            results = self.detector.detect(mp_image)
            if results and results.hand_landmarks:
                for hand_lms in results.hand_landmarks:
                    pts = [(lm.x * w, lm.y * h) for lm in hand_lms]
                    hands_px.append(pts)

        return hands_px


def calibrate_interactive(frame):
    """Interactive neck calibration window. Click Nut, then 12th Fret."""
    clicks = []
    window_name = "Calibrate Guitar Neck (Click 1: Nut, Click 2: 12th Fret)"

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(clicks) < 2:
            clicks.append((float(x), float(y)))

    cv2.namedWindow(window_name)
    cv2.setMouseCallback(window_name, on_mouse)

    print("--- Neck Calibration ---")
    print("Click 1: Nut (center of fret 0)")
    print("Click 2: 12th Fret (center of 12th fret wire)")
    print("Keys: [c] or [Enter] to confirm, [r] to reset clicks, [q] to quit")

    while True:
        display = frame.copy()
        if len(clicks) >= 1:
            cv2.circle(display, (int(clicks[0][0]), int(clicks[0][1])), 6, (0, 0, 255), -1)
            cv2.putText(display, "Nut", (int(clicks[0][0]) + 8, int(clicks[0][1]) - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        if len(clicks) == 2:
            nut, f12 = clicks[0], clicks[1]
            cv2.circle(display, (int(f12[0]), int(f12[1])), 6, (0, 255, 0), -1)
            cv2.putText(display, "Fret 12", (int(f12[0]) + 8, int(f12[1]) - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.line(display, (int(nut[0]), int(nut[1])), (int(f12[0]), int(f12[1])), (255, 255, 0), 2)

            # Draw predicted fret guides (1, 3, 5, 7, 9, 12)
            u = np.array([f12[0] - nut[0], f12[1] - nut[1]], dtype=float)
            for fn in [1, 3, 5, 7, 9, 12, 15, 17, 19]:
                r = ratio_from_fret(fn)
                pt = np.array(nut) + r * u
                cv2.circle(display, (int(pt[0]), int(pt[1])), 3, (255, 128, 0), -1)
                cv2.putText(display, str(fn), (int(pt[0]), int(pt[1]) - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 128, 0), 1)

        cv2.imshow(window_name, display)
        key = cv2.waitKey(20) & 0xFF
        if key in [ord("c"), 13, 10] and len(clicks) == 2:  # 'c' or Enter
            break
        elif key == ord("r"):
            clicks.clear()
        elif key == ord("q"):
            cv2.destroyAllWindows()
            sys.exit(0)

    cv2.destroyAllWindows()
    return clicks[0], clicks[1]


def select_fretting_hand(hands, nut, fret12, landmark_idx=5):
    """Identify the fretting hand from detected hands based on neck proximity."""
    if not hands:
        return None, None

    u = np.array([fret12[0] - nut[0], fret12[1] - nut[1]], dtype=float)
    d12 = np.linalg.norm(u)
    max_perp_allowed = d12 * 0.45  # allowable off-neck tolerance

    best_hand = None
    best_perp = float("inf")
    best_ratio = None

    for hand in hands:
        pt = hand[landmark_idx]
        ratio, perp = project_point_to_neck(pt, nut, fret12)
        # Fretting hand sits along the neck between nut and body (r in [-0.2, 1.6])
        if -0.25 <= ratio <= 1.6 and perp < max_perp_allowed:
            if perp < best_perp:
                best_perp = perp
                best_hand = hand
                best_ratio = ratio

    return best_hand, best_ratio


def process_video(video_path, nut, fret12, landmark_name="index_mcp", interval=0.25,
                  smooth_window=3, show=False, out_video=None):
    """Process video file and extract (t, fret) estimate timeseries."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    step_frames = max(1, int(round(fps * interval)))

    tracker = HandTracker()
    landmark_idx = LANDMARK_MAP.get(landmark_name, 5)

    writer = None
    if out_video:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(out_video, fourcc, fps / step_frames, (w, h))

    records = []
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % step_frames == 0:
            t = round(frame_idx / fps, 3)
            hands = tracker.find_hands(frame)
            hand, ratio = select_fretting_hand(hands, nut, fret12, landmark_idx)

            if ratio is not None:
                fret_val = fret_from_ratio(ratio)
            else:
                fret_val = None

            records.append({"t": t, "fret": fret_val, "frame": frame if (show or writer) else None, "hand": hand})

        frame_idx += 1

    cap.release()

    # Impute missing detections using forward-fill / linear interpolation
    frets = [r["fret"] for r in records]
    valid_indices = [i for i, f in enumerate(frets) if f is not None]
    if valid_indices:
        # Backward fill start
        for i in range(valid_indices[0]):
            frets[i] = frets[valid_indices[0]]
        # Interpolate interior gaps
        for k in range(len(valid_indices) - 1):
            i0, i1 = valid_indices[k], valid_indices[k + 1]
            f0, f1 = frets[i0], frets[i1]
            for step, i in enumerate(range(i0 + 1, i1), 1):
                frets[i] = f0 + (f1 - f0) * (step / (i1 - i0))
        # Forward fill end
        for i in range(valid_indices[-1] + 1, len(frets)):
            frets[i] = frets[valid_indices[-1]]
    else:
        frets = [0.0] * len(records)

    # Rolling median smoothing
    if smooth_window > 1 and len(frets) >= smooth_window:
        half = smooth_window // 2
        smoothed = []
        for i in range(len(frets)):
            win = frets[max(0, i - half): min(len(frets), i + half + 1)]
            smoothed.append(float(np.median(win)))
        frets = smoothed

    # Render visualizations if requested
    for i, r in enumerate(records):
        fret_est = round(frets[i], 1)
        r["fret"] = fret_est

        if r["frame"] is not None:
            f = r["frame"]
            cv2.line(f, (int(nut[0]), int(nut[1])), (int(fret12[0]), int(fret12[1])), (255, 255, 0), 2)
            cv2.circle(f, (int(nut[0]), int(nut[1])), 5, (0, 0, 255), -1)
            cv2.circle(f, (int(fret12[0]), int(fret12[1])), 5, (0, 255, 0), -1)
            cv2.putText(f, f"t: {r['t']:.2f}s  Fret: {fret_est}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)

            if r["hand"]:
                pt = r["hand"][landmark_idx]
                cv2.circle(f, (int(pt[0]), int(pt[1])), 7, (0, 255, 255), -1)

            if writer:
                writer.write(f)
            if show:
                cv2.imshow("FretGPS Camera Tracking", f)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    if writer:
        writer.release()
    if show:
        cv2.destroyAllWindows()

    return [(r["t"], r["fret"]) for r in records]


def write_csv(hints, out_path):
    """Write hints as t,fret CSV."""
    f = sys.stdout if out_path == "-" else open(out_path, "w", newline="")
    try:
        w = csv.writer(f)
        w.writerow(["t", "fret"])
        for t, fret in hints:
            w.writerow([f"{t:.2f}", f"{fret:.1f}"])
    finally:
        if out_path != "-":
            f.close()


def main():
    ap = argparse.ArgumentParser(description="Extract hand-position hint CSV from video using MediaPipe.")
    ap.add_argument("video", help="Path to video file (phone on stand, neck in view)")
    ap.add_argument("--out", default="-", help="Output hints.csv file (default stdout)")
    ap.add_argument("--interval", type=float, default=0.25, help="Sampling interval in seconds (default 0.25)")
    ap.add_argument("--calib", help="Path to existing calibration JSON file")
    ap.add_argument("--save-calib", help="Save calibration to JSON file")
    ap.add_argument("--nut", help="Nut coordinates as 'x,y'")
    ap.add_argument("--fret12", help="12th fret coordinates as 'x,y'")
    ap.add_argument("--landmark", default="index_mcp", choices=list(LANDMARK_MAP.keys()),
                    help="Landmark to track (default index_mcp)")
    ap.add_argument("--smooth", type=int, default=3, help="Median filter window size (default 3, 0 or 1 to disable)")
    ap.add_argument("--show", action="store_true", help="Display tracking visualization")
    ap.add_argument("--save-video", help="Save visualization to an annotated MP4 video")
    args = ap.parse_args()

    # Determine calibration
    nut, fret12 = None, None
    if args.calib and os.path.exists(args.calib):
        with open(args.calib) as f:
            c = json.load(f)
            nut = tuple(c["nut"])
            fret12 = tuple(c["fret12"])
    elif args.nut and args.fret12:
        nut = tuple(float(v) for v in args.nut.split(","))
        fret12 = tuple(float(v) for v in args.fret12.split(","))
    else:
        # Interactive calibration on first frame
        cap = cv2.VideoCapture(args.video)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            sys.exit(f"Error: Could not read first frame of {args.video}")
        nut, fret12 = calibrate_interactive(frame)

    if args.save_calib:
        with open(args.save_calib, "w") as f:
            json.dump({"nut": list(nut), "fret12": list(fret12)}, f, indent=2)
        print(f"Calibration saved to {args.save_calib}", file=sys.stderr)

    hints = process_video(
        video_path=args.video,
        nut=nut,
        fret12=fret12,
        landmark_name=args.landmark,
        interval=args.interval,
        smooth_window=args.smooth,
        show=args.show,
        out_video=args.save_video,
    )

    write_csv(hints, args.out)
    if args.out != "-":
        print(f"Saved {len(hints)} hint rows to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
