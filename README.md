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

## Makefile

A `Makefile` is provided for common development tasks:

```bash
make help            # list all targets

# Setup
make install         # create .venv and install full Python deps + pytest
make install-api     # lightweight API-only deps (no MediaPipe/OpenCV)
make install-frontend

# Local dev (each in its own terminal)
make dev-redis
make dev-api
make dev-worker
make dev-frontend

# Docker
make docker-build
make docker-up
make docker-down
make docker-logs

# Quality
make test            # run pytest (68 tests)
make lint            # flake8 + eslint
make clean
```

## Testing

Unit tests live in `tests/` and cover math helpers, metrics aggregation, and all Pydantic API models.

```bash
make test
# or directly:
PYTHONPATH=. .venv/bin/pytest tests/ -v
```

No external services (Redis, S3, Postgres) are required to run the test suite.

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

## Running the REST API (FastAPI + Celery + Redis + S3 + Postgres)

The API backend supports React web and React Native mobile clients.

**Prerequisites:** Redis server, PostgreSQL database, AWS S3 bucket, and all env vars set in `.env`.

```bash
# One-time: create the database schema
psql -U postgres -d tennis_coach -f db_schema.sql

# Terminal 1 — Redis
redis-server

# Terminal 2 — Celery worker (heavy video processing)
celery -A celery_app worker --loglevel=info --concurrency=2

# Terminal 3 — FastAPI server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Set `DATABASE_URL` in `.env` (default: `postgresql://postgres:postgres@localhost:5432/tennis_coach`).

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
| `GET` | `/api/v1/users/{user_id}/history` | Required | Paginated session list with presigned URLs |
| `GET` | `/api/v1/users/{user_id}/progress` | Required | Time-series of scalar metrics for charting |
| `POST` | `/api/v1/users/{user_id}/compare` | Required | Delta coaching between two sessions |

Sessions are persisted to PostgreSQL on every completed analysis. Ephemeral job state expires from Redis after 24h.

## Project Structure

```
tennis-coach/
├── frontend/               # Next.js 14 React frontend
│   ├── src/app/page.tsx    # Entire app: state machine + all components
│   ├── src/lib/api.ts      # TypeScript fetch helpers + API types
│   └── next.config.mjs     # output: "standalone"
├── config.py               # Landmark indices, thresholds, constants
├── celery_app.py           # Celery instance (broker=Redis)
├── db_schema.sql           # PostgreSQL schema (run once manually)
├── requirements.txt
├── requirements-api.txt    # Lean deps for the API service (no MediaPipe/OpenCV)
├── Dockerfile.frontend
├── Dockerfile.api
├── Dockerfile.worker
├── docker-compose.yml
├── .env.example
├── Makefile                # dev/test/docker targets
├── tests/                  # pytest suite (math helpers, metrics, models)
├── api/
│   ├── main.py             # FastAPI app factory + CORS + lifespan DB pool
│   ├── settings.py         # Pydantic settings (env vars)
│   ├── models.py           # Request/response Pydantic models
│   ├── db.py               # asyncpg connection pool singleton
│   ├── auth/
│   │   ├── google.py       # Google OAuth URL builder + token exchange
│   │   ├── jwt.py          # JWT sign + verify (python-jose HS256)
│   │   └── dependencies.py # get_current_user FastAPI dependency
│   ├── routes/
│   │   ├── analysis.py     # Job endpoints (analyze / status / result)
│   │   ├── auth.py         # /auth/google, /auth/callback, /auth/me
│   │   └── history.py      # History / progress / compare endpoints
│   ├── services/
│   │   ├── storage.py      # S3 upload + presigned URLs
│   │   ├── job_store.py    # Redis job state (user-scoped)
│   │   ├── user_store.py   # Redis user records (90-day TTL)
│   │   └── history.py      # SQL service layer (players + sessions)
│   └── tasks/
│       └── analyze.py      # Celery task: full pipeline + Postgres persist
├── pipeline/
│   ├── video_io.py         # Frame extraction + H.264 reassembly
│   ├── pose_detector.py    # MediaPipe wrapper
│   ├── metrics.py          # Joint angles, swing detection, aggregation
│   ├── annotator.py        # Skeleton overlay, angle labels, wrist trail
│   ├── coach.py            # Claude prompt builder + response parser
│   └── compare_coach.py    # Delta coaching between two sessions
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
| Auth | Google OAuth + python-jose (JWT) |
| Database | PostgreSQL (asyncpg / psycopg2) |
