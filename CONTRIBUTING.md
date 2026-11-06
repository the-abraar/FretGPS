# Contributing to FretGPS

Thanks for helping. FretGPS is at the idea stage: the only code is the phone-audio
experiment in `experiments/phone-audio/`. Read [docs/PLAN.md](docs/PLAN.md) and
[docs/phone-audio-experiment.md](docs/phone-audio-experiment.md) first. They explain
what is measured, what is a guess, and what comes next.

## Set up and test

Needs Python 3.11 or 3.12 and `ffmpeg` (macOS: `brew install ffmpeg`, Debian/Ubuntu: `apt install ffmpeg`).

```bash
cd experiments/phone-audio
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python test_fretmap.py        # must print "ok"
```

To reproduce the measured numbers, download GuitarSet (`annotation.zip` and
`audio_mono-mic.zip` from https://zenodo.org/records/3371780) and run
`python eval_guitarset.py GUITARSET_DIR` (see the docstring for the other modes).

## Pick an issue

- Start with issues labelled `good first issue` or `difficulty: easy`.
- Comment on the issue before you start, so two people don't do the same work.
- Out of scope for now: anything in PLAN.md's "Parked" list (overlay, cloud, AI coach, ...).

## Pull requests

- One issue per PR. Say which issue it closes (`Closes #N`).
- `python test_fretmap.py` still prints `ok`. Add an assert for new logic.
- If you change a number in the docs, say how you measured it (command + dataset).
- Keep the note-event format from PLAN.md section 4 backward compatible: add fields, don't rename them.
- Keep it small and plain. No new dependency for something a few lines can do.

By contributing you agree that your work is released under the MIT License.
