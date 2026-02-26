"""
History / Progress / Compare routes:

  GET  /api/v1/users/{user_id}/history          — paginated session list
  GET  /api/v1/users/{user_id}/progress         — time-series scalar metrics
  POST /api/v1/users/{user_id}/compare          — delta coaching between two sessions

All routes require authentication. The authenticated user may only access their
own sessions; requesting another user's data returns 403.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from api import db
from api.auth.dependencies import get_current_user
from api.models import (
    CompareRequest,
    CompareResponse,
    DeltaCoachingReport,
    MetricDelta,
    ProgressDataPoint,
    ProgressResponse,
    SessionListResponse,
    SessionSummary,
)
from api.services import history, storage
from api.settings import settings
from pipeline.compare_coach import compute_metric_deltas, get_delta_coaching

router = APIRouter(prefix="/api/v1/users/{user_id}")


def _validate_uuid(value: str, field: str) -> str:
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"{field} '{value}' is not a valid UUID.")
    return value


def _check_ownership(user_id: str, current_user: dict) -> None:
    """Raise 403 if the path user_id doesn't match the authenticated user."""
    if user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Access denied.")


# ---------------------------------------------------------------------------
# GET /api/v1/users/{user_id}/history
# ---------------------------------------------------------------------------

@router.get("/history", response_model=SessionListResponse)
async def get_history(
    user_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """
    Return a paginated list of analysis sessions for the authenticated player.
    Presigned S3 URLs are generated fresh on each call.
    """
    _validate_uuid(user_id, "user_id")
    _check_ownership(user_id, current_user)

    pool = db.get_pool()
    sessions_raw, total = await history.list_sessions(pool, user_id, limit=limit, offset=offset)

    if not sessions_raw:
        raise HTTPException(status_code=404, detail=f"No sessions found for user '{user_id}'.")

    summaries = []
    for s in sessions_raw:
        annotated_url = storage.presigned_url(s["annotated_s3_key"])
        input_url = storage.presigned_url(s["input_s3_key"])
        summaries.append(
            SessionSummary(
                session_id=s["id"],
                job_id=s["job_id"],
                recorded_at=s["recorded_at"],
                original_filename=s.get("original_filename"),
                fps=s["fps"],
                total_source_frames=s["total_source_frames"],
                frames_analyzed=s["frames_analyzed"],
                detection_rate=s["detection_rate"],
                annotated_video_url=annotated_url,
                input_video_url=input_url,
                metrics=s["metrics"],
                coaching=s["coaching"],
            )
        )

    return SessionListResponse(
        sessions=summaries,
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# GET /api/v1/users/{user_id}/progress
# ---------------------------------------------------------------------------

@router.get("/progress", response_model=ProgressResponse)
async def get_progress(
    user_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """
    Return chronological time-series of scalar metrics for charting.
    No presigned URLs — numeric data only, fast.
    """
    _validate_uuid(user_id, "user_id")
    _check_ownership(user_id, current_user)

    pool = db.get_pool()
    rows = await history.get_sessions_for_progress(pool, user_id, limit=limit)

    if not rows:
        raise HTTPException(status_code=404, detail=f"No sessions found for user '{user_id}'.")

    data_points = [
        ProgressDataPoint(
            session_id=r["session_id"],
            recorded_at=r["recorded_at"],
            right_elbow_mean=r.get("right_elbow_mean"),
            left_elbow_mean=r.get("left_elbow_mean"),
            right_shoulder_mean=r.get("right_shoulder_mean"),
            left_shoulder_mean=r.get("left_shoulder_mean"),
            right_knee_mean=r.get("right_knee_mean"),
            left_knee_mean=r.get("left_knee_mean"),
            torso_rotation_mean=r.get("torso_rotation_mean"),
            stance_width_mean=r.get("stance_width_mean"),
            com_x_range=r.get("com_x_range"),
            swing_count=r.get("swing_count"),
            detection_rate=r["detection_rate"],
        )
        for r in rows
    ]

    return ProgressResponse(data_points=data_points, total=len(data_points))


# ---------------------------------------------------------------------------
# POST /api/v1/users/{user_id}/compare
# ---------------------------------------------------------------------------

@router.post("/compare", response_model=CompareResponse)
async def compare_sessions(
    user_id: str,
    body: CompareRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Compare two sessions belonging to the authenticated player and return delta coaching.

    Both sessions must belong to *user_id*. Claude is called synchronously (2-5s,
    acceptable for on-demand comparison).
    """
    _validate_uuid(user_id, "user_id")
    _check_ownership(user_id, current_user)
    _validate_uuid(body.session_a_id, "session_a_id")
    _validate_uuid(body.session_b_id, "session_b_id")

    if body.session_a_id == body.session_b_id:
        raise HTTPException(status_code=400, detail="session_a_id and session_b_id must be different.")

    pool = db.get_pool()
    session_a = await history.get_session(pool, body.session_a_id, user_id)
    if session_a is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{body.session_a_id}' not found or does not belong to user.",
        )

    session_b = await history.get_session(pool, body.session_b_id, user_id)
    if session_b is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{body.session_b_id}' not found or does not belong to user.",
        )

    # Compute metric deltas
    raw_deltas = compute_metric_deltas(session_a, session_b)
    metric_deltas = [
        MetricDelta(
            metric_name=d["metric_name"],
            session_a_value=d["session_a_value"],
            session_b_value=d["session_b_value"],
            delta=d["delta"],
            direction=d["direction"],
        )
        for d in raw_deltas
    ]

    # Get Claude delta coaching (synchronous — runs in request handler)
    pipeline_report = get_delta_coaching(
        session_a,
        session_b,
        api_key=settings.anthropic_api_key,
    )

    delta_coaching = DeltaCoachingReport(
        overall_progress_summary=pipeline_report.overall_progress_summary,
        improvements=pipeline_report.improvements,
        regressions=pipeline_report.regressions,
        unchanged_areas=pipeline_report.unchanged_areas,
        top_3_priorities=pipeline_report.top_3_priorities,
        raw_response=pipeline_report.raw_response,
    )

    return CompareResponse(
        session_a_id=body.session_a_id,
        session_b_id=body.session_b_id,
        metric_deltas=metric_deltas,
        delta_coaching=delta_coaching,
    )
