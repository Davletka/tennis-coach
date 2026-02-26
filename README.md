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

## Running the Next.js frontend (local dev)

```bash
cd frontend
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL if needed
npm install
npm run dev
```

Open http://localhost:3000. The frontend requires the FastAPI backend running (see below).

1. Drag-and-drop or browse to select a tennis video (MP4, MOV, or AVI)
2. Click **Analyze Video** — progress is shown while the job runs
3. View the annotated video and coaching tabs (Swing / Footwork / Stance / Tactics / Priorities)
4. Download the annotated video or expand **Raw Metrics** for joint angle stats

## Running with Docker

The project ships with separate Dockerfiles for each service and a `docker-compose.yml` that orchestrates everything.

```bash
cp .env.example .env   # fill in ANTHROPIC_API_KEY, AWS credentials, etc.
docker compose up --build
```

| Service | URL |
|---------|-----|
| Next.js frontend | http://localhost:3000 |
| FastAPI docs | http://localhost:8000/docs |
| Redis | localhost:6379 |

Individual images:

```bash
docker build -f Dockerfile.frontend -t tennis-frontend .
docker build -f Dockerfile.api      -t tennis-api       .
docker build -f Dockerfile.worker   -t tennis-worker    .
```

> **Note:** `Dockerfile.api` uses `requirements-api.txt` (no MediaPipe/OpenCV) for a leaner image. `Dockerfile.frontend` is a 3-stage build producing a standalone Next.js bundle.

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

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/analyze` | Upload video → returns `job_id` (202 Accepted) |
| `GET` | `/api/v1/jobs/{job_id}` | Poll status + progress (0–100%) |
| `GET` | `/api/v1/jobs/{job_id}/result` | Fetch coaching report, metrics, and presigned video URLs |

## Project Structure

```
tennis-coach/
├── frontend/               # Next.js 14 React frontend
│   ├── src/app/page.tsx    # Entire app: state machine + all components
│   ├── src/lib/api.ts      # TypeScript fetch helpers + API types
│   └── next.config.mjs     # output: "standalone"
├── config.py               # Landmark indices, thresholds, constants
├── celery_app.py           # Celery instance (broker=Redis)
├── requirements.txt
├── requirements-api.txt    # Lean deps for the API service (no MediaPipe/OpenCV)
├── Dockerfile.frontend
├── Dockerfile.api
├── Dockerfile.worker
├── docker-compose.yml
├── .env.example
├── api/
│   ├── main.py             # FastAPI app factory + CORS
│   ├── settings.py         # Pydantic settings (env vars)
│   ├── models.py           # Request/response Pydantic models
│   ├── routes/
│   │   └── analysis.py     # REST endpoints
│   ├── services/
│   │   ├── storage.py      # S3 upload + presigned URLs
│   │   └── job_store.py    # Redis job state
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
| Frontend | Next.js 14 + TypeScript + Tailwind CSS |
| REST API | FastAPI + uvicorn |
| Async jobs | Celery + Redis |
| File storage | AWS S3 (boto3) |
| Pose detection | MediaPipe |
| Video processing | OpenCV (headless) |
| AI coaching | Anthropic Claude (`claude-sonnet-4-6`) |
| Math | NumPy |
