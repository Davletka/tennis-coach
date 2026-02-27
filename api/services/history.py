"""
SQL service layer for player history and progress tracking.

All functions accept an asyncpg Pool (or Connection) and operate asynchronously.
They contain no HTTP concerns — call them from route handlers.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

import asyncpg


# ---------------------------------------------------------------------------
# Player management
# ---------------------------------------------------------------------------

async def upsert_player(pool: asyncpg.Pool, user_id: str) -> None:
    """
    Ensure a player row exists for *user_id*.
    On conflict (re-submit) just refreshes updated_at.
    """
    await pool.execute(
        """
        INSERT INTO players (user_id)
        VALUES ($1::uuid)
        ON CONFLICT (user_id) DO UPDATE
            SET updated_at = NOW()
        """,
        user_id,
    )


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------

async def create_session(pool: asyncpg.Pool, data: Dict[str, Any]) -> str:
    """
    Upsert the player then insert the analysis session.

    *data* keys (all required unless marked optional):
        user_id, job_id, original_filename (optional), fps,
        total_source_frames, frames_analyzed, detection_rate,
        input_s3_key, annotated_s3_key, metrics (dict), coaching (dict)

    Returns the new session UUID as a string.
    INSERT is ON CONFLICT DO NOTHING so retries are safe.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO players (user_id)
                VALUES ($1::uuid)
                ON CONFLICT (user_id) DO UPDATE
                    SET updated_at = NOW()
                """,
                data["user_id"],
            )

            row = await conn.fetchrow(
                """
                INSERT INTO analysis_sessions (
                    user_id, job_id, original_filename,
                    fps, total_source_frames, frames_analyzed, detection_rate,
                    input_s3_key, annotated_s3_key, metrics, coaching
                )
                VALUES (
                    $1::uuid, $2, $3,
                    $4, $5, $6, $7,
                    $8, $9, $10::jsonb, $11::jsonb
                )
                ON CONFLICT (job_id) DO NOTHING
                RETURNING id
                """,
                data["user_id"],
                data["job_id"],
                data.get("original_filename"),
                data["fps"],
                data["total_source_frames"],
                data["frames_analyzed"],
                data["detection_rate"],
                data["input_s3_key"],
                data["annotated_s3_key"],
                json.dumps(data["metrics"]),
                json.dumps(data["coaching"]),
            )

    if row is None:
        # Conflict — session already exists; fetch its id
        existing = await pool.fetchrow(
            "SELECT id FROM analysis_sessions WHERE job_id = $1",
            data["job_id"],
        )
        return str(existing["id"]) if existing else ""

    return str(row["id"])


# ---------------------------------------------------------------------------
# Session retrieval
# ---------------------------------------------------------------------------

async def list_sessions(
    pool: asyncpg.Pool,
    user_id: str,
    limit: int = 20,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Return (sessions, total_count) for *user_id*, newest first.
    """
    rows = await pool.fetch(
        """
        SELECT
            id, job_id, recorded_at, original_filename,
            fps, total_source_frames, frames_analyzed, detection_rate,
            input_s3_key, annotated_s3_key, metrics, coaching,
            COUNT(*) OVER () AS total_count
        FROM analysis_sessions
        WHERE user_id = $1::uuid
        ORDER BY recorded_at DESC
        LIMIT $2 OFFSET $3
        """,
        user_id,
        limit,
        offset,
    )

    if not rows:
        return [], 0

    total = rows[0]["total_count"]
    sessions = []
    for r in rows:
        sessions.append({
            "id": str(r["id"]),
            "job_id": r["job_id"],
            "recorded_at": r["recorded_at"],
            "original_filename": r["original_filename"],
            "fps": r["fps"],
            "total_source_frames": r["total_source_frames"],
            "frames_analyzed": r["frames_analyzed"],
            "detection_rate": r["detection_rate"],
            "input_s3_key": r["input_s3_key"],
            "annotated_s3_key": r["annotated_s3_key"],
            "metrics": json.loads(r["metrics"]) if isinstance(r["metrics"], str) else dict(r["metrics"]),
            "coaching": json.loads(r["coaching"]) if isinstance(r["coaching"], str) else dict(r["coaching"]),
        })

    return sessions, total


async def delete_session(
    pool: asyncpg.Pool,
    session_id: str,
    user_id: str,
) -> Optional[Dict[str, str]]:
    """
    Delete the session row and return its S3 keys for cleanup, or None if not found.
    """
    row = await pool.fetchrow(
        """
        DELETE FROM analysis_sessions
        WHERE id = $1::uuid AND user_id = $2::uuid
        RETURNING input_s3_key, annotated_s3_key
        """,
        session_id,
        user_id,
    )
    if row is None:
        return None
    return {
        "input_s3_key": row["input_s3_key"],
        "annotated_s3_key": row["annotated_s3_key"],
    }


async def get_session(
    pool: asyncpg.Pool,
    session_id: str,
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Return a single session dict, or None if not found / doesn't belong to user.
    """
    row = await pool.fetchrow(
        """
        SELECT
            id, job_id, recorded_at, original_filename,
            fps, total_source_frames, frames_analyzed, detection_rate,
            input_s3_key, annotated_s3_key, metrics, coaching
        FROM analysis_sessions
        WHERE id = $1::uuid AND user_id = $2::uuid
        """,
        session_id,
        user_id,
    )

    if row is None:
        return None

    return {
        "id": str(row["id"]),
        "job_id": row["job_id"],
        "recorded_at": row["recorded_at"],
        "original_filename": row["original_filename"],
        "fps": row["fps"],
        "total_source_frames": row["total_source_frames"],
        "frames_analyzed": row["frames_analyzed"],
        "detection_rate": row["detection_rate"],
        "input_s3_key": row["input_s3_key"],
        "annotated_s3_key": row["annotated_s3_key"],
        "metrics": json.loads(row["metrics"]) if isinstance(row["metrics"], str) else dict(row["metrics"]),
        "coaching": json.loads(row["coaching"]) if isinstance(row["coaching"], str) else dict(row["coaching"]),
    }


# ---------------------------------------------------------------------------
# Progress time-series
# ---------------------------------------------------------------------------

async def get_sessions_for_progress(
    pool: asyncpg.Pool,
    user_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Return scalar metric extractions for charting, chronological order.
    JSONB scalars are extracted inline in SQL for efficiency.
    """
    rows = await pool.fetch(
        """
        SELECT
            id,
            recorded_at,
            detection_rate,
            (metrics -> 'right_elbow'    ->> 'mean')::float   AS right_elbow_mean,
            (metrics -> 'left_elbow'     ->> 'mean')::float   AS left_elbow_mean,
            (metrics -> 'right_shoulder' ->> 'mean')::float   AS right_shoulder_mean,
            (metrics -> 'left_shoulder'  ->> 'mean')::float   AS left_shoulder_mean,
            (metrics -> 'right_knee'     ->> 'mean')::float   AS right_knee_mean,
            (metrics -> 'left_knee'      ->> 'mean')::float   AS left_knee_mean,
            (metrics ->> 'torso_rotation_mean')::float        AS torso_rotation_mean,
            (metrics ->> 'stance_width_mean')::float          AS stance_width_mean,
            (metrics ->> 'com_x_range')::float                AS com_x_range,
            (metrics ->> 'swing_count')::int                  AS swing_count
        FROM analysis_sessions
        WHERE user_id = $1::uuid
        ORDER BY recorded_at ASC
        LIMIT $2
        """,
        user_id,
        limit,
    )

    return [
        {
            "session_id": str(r["id"]),
            "recorded_at": r["recorded_at"],
            "detection_rate": r["detection_rate"],
            "right_elbow_mean": r["right_elbow_mean"],
            "left_elbow_mean": r["left_elbow_mean"],
            "right_shoulder_mean": r["right_shoulder_mean"],
            "left_shoulder_mean": r["left_shoulder_mean"],
            "right_knee_mean": r["right_knee_mean"],
            "left_knee_mean": r["left_knee_mean"],
            "torso_rotation_mean": r["torso_rotation_mean"],
            "stance_width_mean": r["stance_width_mean"],
            "com_x_range": r["com_x_range"],
            "swing_count": r["swing_count"],
        }
        for r in rows
    ]
