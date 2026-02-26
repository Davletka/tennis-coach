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
cp .env.example .env          # fill in all required env vars (see .env.example)
```

ffmpeg is recommended for browser-compatible H.264 output (the app falls back to mp4v if unavailable).

On first run the app downloads the MediaPipe pose landmarker model (~25 MB) into `models/` and caches it for subsequent runs.

## Running the Streamlit UI

```bash
streamlit run app.py
```

1. Enter your Anthropic API key in the sidebar (or set `ANTHROPIC_API_KEY` in `.env`)
2. Upload a tennis video (MP4, MOV, or AVI — ideally ≤10 seconds)
3. Adjust display and analysis options in the sidebar
4. Click **Analyze** and wait for the pipeline to complete
5. View the annotated video and coaching tabs (Swing / Footwork / Stance / Tactics / Priorities)
6. Download the annotated video with the download button

## Running the REST API (FastAPI + Celery + Redis + S3)

The API backend supports React web and React Native mobile clients.

**Prerequisites:** Redis server, AWS S3 bucket, and all env vars set in `.env`.

```bash
# Terminal 1 — Redis
redis-server

# Terminal 2 — Celery worker (heavy video processing)
celery -A celery_app worker --loglevel=info --concurrency=2

# Terminal 3 — FastAPI server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive API docs: `http://localhost:8000/docs`

### Authentication

All `/api/v1/*` routes require a `Authorization: Bearer <token>` header. Obtain a token via the OAuth flow:

1. Redirect the user to `GET /auth/google`
2. After consent, Google redirects to `/auth/callback`, which issues a JWT and redirects to `{FRONTEND_URL}/auth/callback?token=<jwt>`
3. Include the token in subsequent API requests

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/auth/google` | — | Start Google OAuth flow (302 redirect) |
| `GET` | `/auth/callback` | — | OAuth callback → sign JWT → redirect to frontend |
| `GET` | `/auth/me` | Required | Return authenticated user profile |
| `POST` | `/api/v1/analyze` | Required | Upload video → returns `job_id` (202 Accepted) |
| `GET` | `/api/v1/jobs/{job_id}` | Required | Poll status + progress (0–100%) |
| `GET` | `/api/v1/jobs/{job_id}/result` | Required | Fetch coaching report, metrics, and presigned video URLs |

## Project Structure

```
tennis-coach/
├── app.py                  # Streamlit UI + orchestration
├── config.py               # Landmark indices, thresholds, constants
├── celery_app.py           # Celery instance (broker=Redis)
├── requirements.txt
├── .env.example
├── api/
│   ├── main.py             # FastAPI app factory + CORS
│   ├── settings.py         # Pydantic settings (env vars)
│   ├── models.py           # Request/response Pydantic models
│   ├── auth/
│   │   ├── google.py       # Google OAuth URL builder + token exchange
│   │   ├── jwt.py          # JWT sign + verify (python-jose HS256)
│   │   └── dependencies.py # get_current_user FastAPI dependency
│   ├── routes/
│   │   ├── analysis.py     # REST endpoints (auth-protected)
│   │   └── auth.py         # /auth/google, /auth/callback, /auth/me
│   ├── services/
│   │   ├── storage.py      # S3 upload + presigned URLs
│   │   ├── job_store.py    # Redis job state (user-scoped)
│   │   └── user_store.py   # Redis user records (90-day TTL)
│   └── tasks/
│       └── analyze.py      # Celery task: full pipeline
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
| Streamlit UI | Streamlit |
| REST API | FastAPI + uvicorn |
| Async jobs | Celery + Redis |
| File storage | AWS S3 (boto3) |
| Pose detection | MediaPipe |
| Video processing | OpenCV (headless) |
| AI coaching | Anthropic Claude (`claude-sonnet-4-6`) |
| Math | NumPy |
