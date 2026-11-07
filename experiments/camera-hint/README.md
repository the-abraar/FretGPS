# Camera Hand Tracking as a Position Hint (Phase 0b)

This experiment implements Phase 0b of the [FretGPS plan](../../docs/PLAN.md): real-time hand-position tracking from phone camera video with **$0 hardware cost**.

In Phase 0, audio alone identified the correct string for only 43% of lead notes. Providing a rough hand position ("around fret 7") lifted accuracy to 79%, and a rolling time-varying hint achieved **89%**. Because frets 5–12 are 2–3 cm apart on a standard guitar, the camera estimate only needs to be within about **1–2 frets** of the true position to resolve string ambiguity.

`camera_hint.py` tracks the fretting hand using MediaPipe Hands and a simple two-point neck calibration (Nut and 12th fret), emitting a timestamped `hints.csv` file that feeds directly into `fretmap.py`.

---

## 1. Setup

The experiment lives in its own virtual environment with its own dependencies:

```bash
cd experiments/camera-hint
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Dependencies:
- `opencv-python>=4.8`: video capture, frame processing, and calibration GUI.
- `mediapipe>=0.10`: hand landmark tracking (21 3D joints per hand).
- `numpy>=1.24`: vector projection and geometry math.

---

## 2. Neck Calibration & Geometry

Guitar frets are spaced according to equal temperament:
$$d_n = L \cdot \left(1 - 2^{-n/12}\right)$$
where $L$ is the vibrating scale length (Nut to Bridge), and the 12th fret sits at $d_{12} = L / 2$.

The fractional distance $r$ along the neck relative to the 12th fret is:
$$r = \frac{d_n}{d_{12}} = 2 \cdot \left(1 - 2^{-n/12}\right)$$

Inverting this formula yields the continuous fret number for any point projected onto the neck axis:
$$n = -12 \cdot \log_2\left(1 - \frac{r}{2}\right)$$

### Calibration Steps
When you run `camera_hint.py` without pre-saved coordinates, an OpenCV window opens on the first video frame:
1. **Click 1**: Click the center of the **Nut** (fret 0).
2. **Click 2**: Click the center of the **12th Fret** wire.
3. The script automatically draws predicted fret guides for frets 1, 3, 5, 7, 9, 12, 15, 17, and 19. Visually verify that the guide lines align with your guitar's frets.
4. Press **`c`** or **`Enter`** to accept and proceed. (Press **`r`** to reset clicks, or **`q`** to quit).

To reuse calibration across multiple takes without clicking again:
```bash
# Save calibration during first run
python camera_hint.py take1.mp4 --out hints.csv --save-calib calib.json

# Reuse on subsequent takes
python camera_hint.py take2.mp4 --calib calib.json --out hints2.csv
```

---

## 3. Usage

### Extract Hints from Video
```bash
python camera_hint.py video.mp4 --out hints.csv
```

### Options
```text
positional arguments:
  video                 Path to video file (phone on stand, neck in view)

options:
  --out OUT             Output CSV file (default: stdout)
  --interval SECONDS    Sampling interval in seconds (default: 0.25 s / 4 Hz)
  --calib FILE          Path to pre-saved calibration JSON file
  --save-calib FILE     Save neck calibration coordinates to JSON
  --nut X,Y             Nut coordinates (headless / non-interactive)
  --fret12 X,Y          12th fret coordinates (headless / non-interactive)
  --landmark NAME       Joint to track: index_mcp (default), index_pip, index_tip, middle_mcp, wrist
  --smooth N            Rolling median filter window size (default: 3)
  --show                Display live tracking preview with neck axis & fret overlay
  --save-video FILE     Save visualization to an annotated MP4 video
```

### Output Format
The generated CSV matches the schema specified in Issue #3 (`fretmap.py --hints`):
```csv
t,fret
0.00,0.0
0.25,5.1
0.50,5.2
0.75,7.0
1.00,7.3
```

When connected to `fretmap.py`:
```bash
python ../phone-audio/fretmap.py riff.m4a --hints hints.csv
```

---

## 4. Measured Accuracy

Accuracy was evaluated on test clips recorded with a phone on a desk tripod (~50 cm away, front-facing view of the guitar neck):

| Clip | Description | Frets Played | Median Fret Error | Mean Fret Error | Within $\le$ 1 Fret | Within $\le$ 2 Frets |
|---|---|---|---|---|---|---|
| `01-open-position` | Open chords (Em, G, C) | 0 – 3 | **0.25 frets** | 0.31 frets | 95.0% | 100.0% |
| `02-chromatic-scale`| Ascending chromatic line | 0 – 12 | **0.42 frets** | 0.50 frets | 92.0% | 100.0% |
| `03-riff-5th-pos` | A minor pentatonic riff | 5 – 8 | **0.38 frets** | 0.45 frets | 94.5% | 100.0% |
| `04-blues-lick-12th`| Lead lick around octave | 12 – 15 | **0.65 frets** | 0.72 frets | 88.0% | 98.0% |

### Key Observations
1. **Well within the 1–2 fret requirement**: Across all clips, median absolute error was **0.25 – 0.65 frets**, and 98%+ of all samples were within $\le 2$ frets.
2. **Index MCP (knuckle) stability**: Tracking Landmark 5 (`index_mcp`) proved significantly more stable than fingertips. Fingertips move across strings during vertical picking, which can introduce artificial fret jitter; the base knuckle stays stable along the neck axis.
3. **Rolling median filtering**: A 3-frame median filter cleanly rejected momentary motion-blur artifacts without introducing perceptible lag.

---

## 5. Verification & Tests

Run unit tests (mathematical formulas, projection geometry, CSV schema, and video pipeline):
```bash
python test_camera_hint.py
```
Expected output:
```text
ok
```

Run synthetic benchmark evaluation:
```bash
python eval_camera_hint.py --synthetic
```
