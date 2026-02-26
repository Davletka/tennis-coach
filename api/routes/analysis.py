"""
Analysis routes:
  POST /api/v1/analyze              — upload video, enqueue job
  GET  /api/v1/jobs/{job_id}        — poll job status
  GET  /api/v1/jobs/{job_id}/result — fetch completed result
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse

from api.auth.dependencies import get_current_user
from api.models import (
    AnalyzeResponse,
    AngleStatResult,
    CoachingReportResult,
    JobResultResponse,
    JobStatusResponse,
    MetricsResult,
    SwingEventResult,
)
from api.services import job_store, storage
from api.tasks.analyze import run_analysis

router = APIRouter(prefix="/api/v1")

_ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
async def create_analysis(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Accept an uploaded video, push it to S3, and enqueue a Celery analysis task.
    The authenticated user's ID (from JWT) is passed to the task so the completed
    session is persisted to Postgres for history/progress tracking.
    """
    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    job_id = str(uuid.uuid4())
    s3_key = f"uploads/{job_id}/{file.filename}"

    # Stream file directly to S3 — avoids holding the whole video in memory
    storage.upload_fileobj(file.file, s3_key)

    # Create Redis job record (user-scoped)
    user_id = current_user["sub"]
    job_store.create_job(job_id, user_id=user_id)

    # Enqueue Celery task; user_id always present (auth is mandatory)
    run_analysis.delay(job_id, s3_key, file.filename, user_id=user_id)

    return AnalyzeResponse(job_id=job_id, status="pending")


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, current_user: dict = Depends(get_current_user)):
    """Return current status for a job (for polling)."""
    record = job_store.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if record.get("user_id") != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Access denied.")

    return JobStatusResponse(
        job_id=record["job_id"],
        status=record["status"],
        progress=record.get("progress", 0),
        message=record.get("message", ""),
        created_at=datetime.fromisoformat(record["created_at"]),
        updated_at=datetime.fromisoformat(record["updated_at"]),
    )


@router.get("/jobs/{job_id}/result", response_model=JobResultResponse)
async def get_job_result(job_id: str, current_user: dict = Depends(get_current_user)):
    """
    Return the full result for a completed job.
    Presigned S3 URLs are generated fresh on each call.
    """
    record = job_store.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if record.get("user_id") != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Access denied.")

    status = record["status"]

    if status in ("pending", "running"):
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' is still {status} (progress: {record.get('progress', 0)}%).",
        )

    if status == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"Job '{job_id}' failed: {record.get('error', 'unknown error')}",
        )

    # status == "completed"
    metrics_raw = record["metrics"]
    coaching_raw = record["coaching_report"]

    def _angle(d: dict) -> AngleStatResult:
        return AngleStatResult(**d)

    metrics = MetricsResult(
        right_elbow=_angle(metrics_raw["right_elbow"]),
        left_elbow=_angle(metrics_raw["left_elbow"]),
        right_shoulder=_angle(metrics_raw["right_shoulder"]),
        left_shoulder=_angle(metrics_raw["left_shoulder"]),
        right_knee=_angle(metrics_raw["right_knee"]),
        left_knee=_angle(metrics_raw["left_knee"]),
        torso_rotation_mean=metrics_raw.get("torso_rotation_mean"),
        torso_rotation_max=metrics_raw.get("torso_rotation_max"),
        stance_width_mean=metrics_raw.get("stance_width_mean"),
        com_x_range=metrics_raw.get("com_x_range"),
        swing_count=metrics_raw.get("swing_count", 0),
        swing_events=[SwingEventResult(**e) for e in metrics_raw.get("swing_events", [])],
        frames_analyzed=metrics_raw.get("frames_analyzed", 0),
        pose_detected_frames=metrics_raw.get("pose_detected_frames", 0),
        detection_rate=metrics_raw.get("detection_rate", 0.0),
    )

    coaching = CoachingReportResult(**coaching_raw)

    # Generate fresh presigned URLs — not stored, so they never expire in Redis
    annotated_url = storage.presigned_url(record["annotated_s3_key"])
    input_url = storage.presigned_url(record["input_s3_key"])

    return JobResultResponse(
        job_id=job_id,
        status="completed",
        coaching_report=coaching,
        metrics=metrics,
        annotated_video_url=annotated_url,
        input_video_url=input_url,
        fps=record["fps"],
        total_source_frames=record["total_source_frames"],
    )
