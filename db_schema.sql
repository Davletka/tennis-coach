-- CourtCoach — PostgreSQL schema
-- Run once against your Postgres database:
--   psql -U postgres -d courtcoach -f db_schema.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE players (
    user_id    UUID        PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE analysis_sessions (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    job_id              TEXT        NOT NULL UNIQUE,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    original_filename   TEXT,
    fps                 FLOAT       NOT NULL,
    total_source_frames INT         NOT NULL,
    frames_analyzed     INT         NOT NULL,
    detection_rate      FLOAT       NOT NULL,
    input_s3_key        TEXT        NOT NULL,
    annotated_s3_key    TEXT        NOT NULL,
    metrics             JSONB       NOT NULL,
    coaching            JSONB       NOT NULL
);

CREATE INDEX idx_sessions_user_recorded ON analysis_sessions (user_id, recorded_at DESC);
CREATE INDEX idx_sessions_job_id        ON analysis_sessions (job_id);
CREATE INDEX idx_sessions_metrics_gin   ON analysis_sessions USING GIN (metrics jsonb_path_ops);

-- Learning track progress
-- lesson_id is a dot-path key: e.g. "tennis.forehand.eastern.flat-forehand"
CREATE TABLE learn_progress (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID        NOT NULL REFERENCES players(user_id) ON DELETE CASCADE,
    activity_id  TEXT        NOT NULL,                 -- "tennis", "gym", …
    lesson_id    TEXT        NOT NULL,                 -- full dot-path
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, lesson_id)
);

CREATE INDEX idx_learn_progress_user ON learn_progress (user_id, activity_id);
