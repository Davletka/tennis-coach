# CourtCoach

AI-powered sports coaching app that analyzes uploaded videos using pose detection, renders a live pose overlay on playback, and delivers written coaching feedback via Claude. Supports multiple activities (Tennis, Gym Workout) with a pluggable activity system.

## Features

- **Multi-activity support** — Tennis (swing detection via wrist speed peaks) and Gym Workout (rep detection via joint angle valleys); adding a new sport requires only a single new file in `activities/`
- **Pose detection** — MediaPipe extracts 33 body landmarks per frame
- **Joint angle analysis** — elbow, shoulder, and knee angles with mean/min/max/std stats
- **Event detection** — activity-specific: swing peaks for tennis, joint angle valleys for gym reps
- **Auto-zoom view** — video is auto-cropped to the player's bounding box using pose landmarks, with smooth lerp tracking
- **Form diff canvas** — side-by-side diff skeleton colored by deviation from Claude's target angles (green < 15°, yellow 15–30°, red > 30°)
- **Reference pose overlay** — upload a reference video clip to generate a ghost skeleton (dashed) overlaid on the diff canvas
- **AI coaching with target angles** — Claude Sonnet generates metrics-referenced feedback across 4 categories and recommends ideal joint angles for the player's shot type
- **Per-event breakdown** — each detected swing/rep is analyzed individually; collapsible cards show per-event metrics (joint angles, peak speed/depth, torso rotation) and AI coaching; clicking the timestamp chip seeks the video to that event
- **Learning track** — structured lessons with SVG diagrams for each sport; Tennis covers forehand grips (Eastern / Western / Continental / Semi-Western) → shot lessons; Gym covers exercises by muscle group + equipment, and multi-day workout plans (PPL, Full-Body); progress is synced to PostgreSQL per user and visualised with per-module completion rings

## Setup

```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in all required env vars (see .env.example)
```

On first run the app downloads the MediaPipe pose landmarker model (~25 MB) into `models/` and caches it for subsequent runs.

## Running the Next.js frontend (local dev)

```bash
cd frontend
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL if needed
npm install
npm run dev
```

Open http://localhost:3000. The frontend requires the FastAPI backend running (see below).

1. Sign in with Google (top-right) — required for history tracking and comparisons
2. Select the **Activity** (Tennis or Gym Workout) — drag-and-drop or browse to select a video (MP4, MOV, or AVI) on the **Analyze** tab
3. Click **Analyze Video** — progress is shown while the job runs
4. View the **side-by-side** result: left canvas shows auto-zoomed video tracking the player; right canvas shows the form diff skeleton colored by deviation from Claude's recommended angles
5. Use **Play / Pause** and the seek slider to scrub through the video — both canvases update in sync
6. Toggle **Ghost** to show/hide a dashed reference skeleton; toggle **Labels** to show/hide angle delta annotations
7. Click **+ Reference** to upload a short reference clip — its average pose is extracted and shown as the ghost skeleton on the diff canvas
8. Expand **Raw Metrics** for joint angle stats
6. Switch to **History** to browse all past sessions (expandable coaching + metrics per session)
7. Switch to **Compare** to select two sessions and get AI-generated delta coaching with metric changes
8. Switch to **Progress** to see SVG sparkline charts for each metric across up to 30 sessions
9. Switch to **Learn** to browse sport-specific lessons — choose a sport, a module, a grip/equipment variant, then work through lessons; each lesson has SVG diagrams and coaching text; mark lessons complete to track your progress

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
cp .env.example .env   # fill in ANTHROPIC_API_KEY, Cloudflare R2 credentials, etc.
docker compose up --build
```

| Service | URL |
|---------|-----|
| Next.js frontend | http://localhost:3000 |
| FastAPI docs | http://localhost:8000/docs |
| Redis | localhost:6379 |

Individual images:

```bash
docker build -f Dockerfile.frontend -t courtcoach-frontend .
docker build -f Dockerfile.api      -t courtcoach-api       .
docker build -f Dockerfile.worker   -t courtcoach-worker    .
```

> **Note:** `Dockerfile.api` uses `requirements-api.txt` (no MediaPipe/OpenCV) for a leaner image. `Dockerfile.frontend` is a 3-stage build producing a standalone Next.js bundle.

## Running the REST API (FastAPI + Celery + Redis + R2 + Postgres)

The API backend supports React web and React Native mobile clients.

**Prerequisites:** Redis server, PostgreSQL database, Cloudflare R2 bucket, and all env vars set in `.env`.

```bash
# One-time: create the database schema
psql -U postgres -d courtcoach -f db_schema.sql

# Terminal 1 — Redis
redis-server

# Terminal 2 — Celery worker (heavy video processing)
celery -A celery_app worker --loglevel=info --concurrency=2

# Terminal 3 — FastAPI server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Set `DATABASE_URL` in `.env` (default: `postgresql://postgres:postgres@localhost:5432/courtcoach`).

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
| `POST` | `/api/v1/analyze` | Required | Upload video → returns `job_id` (202 Accepted); deduplicates identical uploads per user via SHA-256 |
| `GET` | `/api/v1/jobs/{job_id}` | Required | Poll status + progress (0–100%) |
| `GET` | `/api/v1/jobs/{job_id}/result` | Required | Fetch coaching report, metrics, per-frame landmark data, and presigned input video URL |
| `POST` | `/api/v1/jobs/{job_id}/retry` | Required | Re-queue a failed job from the furthest checkpoint (coaching-only or full re-run) |
| `POST` | `/api/v1/reference` | Required | Upload a reference video clip → returns averaged pose landmarks + key joint angles for ghost skeleton overlay |
| `GET` | `/api/v1/users/{user_id}/history` | Required | Paginated session list with presigned URLs |
| `GET` | `/api/v1/users/{user_id}/progress` | Required | Time-series of scalar metrics for charting |
| `POST` | `/api/v1/users/{user_id}/compare` | Required | Delta coaching between two sessions |
| `GET` | `/api/v1/learn/progress` | Required | List all lesson IDs the user has marked complete |
| `POST` | `/api/v1/learn/progress` | Required | Mark a lesson complete `{ lesson_id }` (idempotent) |
| `DELETE` | `/api/v1/learn/progress/{lesson_id}` | Required | Unmark a lesson (idempotent) |

Sessions are persisted to PostgreSQL on every completed analysis. Ephemeral job state expires from Redis after 24h.

## Project Structure

```
tennis-coach/
├── frontend/               # Next.js 14 React frontend
│   ├── src/app/page.tsx    # Entire app: state machine + all components
│   ├── src/app/learn-tab.tsx  # Learning track tab component
│   ├── src/lib/api.ts      # TypeScript fetch helpers + API types
│   ├── src/lib/learn-content.ts  # Static lesson content + SVG diagrams
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
│   │   ├── history.py      # History / progress / compare endpoints
│   │   └── learn_progress.py  # Learning track progress endpoints
│   ├── services/
│   │   ├── storage.py      # R2 upload + presigned URLs
│   │   ├── job_store.py    # Redis job state (user-scoped)
│   │   ├── user_store.py   # Redis user records (90-day TTL)
│   │   └── history.py      # SQL service layer (players + sessions)
│   └── tasks/
│       └── analyze.py      # Celery task: full pipeline + Postgres persist
├── activities/
│   ├── __init__.py         # ActivityConfig dataclass + plugin registry
│   ├── tennis.py           # Tennis: swing detection via wrist speed peaks
│   └── gym.py              # Gym: rep detection via joint angle valleys
├── pipeline/
│   ├── video_io.py         # Frame extraction + H.264 reassembly
│   ├── pose_detector.py    # MediaPipe wrapper
│   ├── metrics.py          # Joint angles, event detection, aggregation
│   ├── annotator.py        # Skeleton overlay, angle labels, wrist trail
│   ├── coach.py            # Claude prompt builder + tool_use response parser
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
| File storage | Cloudflare R2 (boto3) |
| Pose detection | MediaPipe |
| Video processing | OpenCV (headless) |
| AI coaching | Anthropic Claude (`claude-sonnet-4-6`) |
| Math | NumPy |
| Auth | Google OAuth + python-jose (JWT) |
| Database | PostgreSQL (asyncpg / psycopg2) |
