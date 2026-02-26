# Tennis Coach

AI-powered tennis coach that analyzes uploaded tennis videos using pose detection, produces an annotated video with skeleton overlay and joint angle labels, and delivers written coaching feedback via Claude.

## Features

- **Pose detection** — MediaPipe extracts 33 body landmarks per frame
- **Joint angle analysis** — elbow, shoulder, and knee angles with mean/min/max/std stats
- **Swing detection** — wrist speed peaks identify backswing/contact/follow-through events
- **Annotated video** — skeleton overlay, angle labels, and wrist trail rendered on every frame
- **AI coaching** — Claude Sonnet generates metrics-referenced feedback across 4 categories

## Setup

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # add your ANTHROPIC_API_KEY
streamlit run app.py
```

ffmpeg is recommended for browser-compatible H.264 output (the app falls back to mp4v if unavailable).

On first run the app downloads the MediaPipe pose landmarker model (~25 MB) into `models/` and caches it for subsequent runs.

## Usage

1. Enter your Anthropic API key in the sidebar (or set `ANTHROPIC_API_KEY` in `.env`)
2. Upload a tennis video (MP4, MOV, or AVI — ideally ≤10 seconds)
3. Adjust display and analysis options in the sidebar
4. Click **Analyze** and wait for the 5-step pipeline to complete
5. View the annotated video and coaching tabs (Swing / Footwork / Stance / Tactics / Priorities)
6. Download the annotated video with the download button

## Project Structure

```
tennis-coach/
├── app.py                  # Streamlit UI + orchestration
├── config.py               # Landmark indices, thresholds, constants
├── requirements.txt
├── .env.example
├── pipeline/
│   ├── video_io.py         # Frame extraction + H.264 reassembly
│   ├── pose_detector.py    # MediaPipe wrapper
│   ├── metrics.py          # Joint angles, swing detection, aggregation
│   ├── annotator.py        # Skeleton overlay, angle labels, wrist trail
│   └── coach.py            # Claude prompt builder + response parser
└── utils/
    └── math_helpers.py     # angle_between_three_points, find_peaks, etc.
```

## Tech Stack

| Component | Library |
|-----------|---------|
| UI | Streamlit |
| Pose detection | MediaPipe |
| Video processing | OpenCV (headless) |
| AI coaching | Anthropic Claude (`claude-sonnet-4-6`) |
| Math | NumPy |
