"""
Analysis routes:
  POST /api/v1/analyze                   — upload video, enqueue job
  GET  /api/v1/jobs/{job_id}             — poll job status
  GET  /api/v1/jobs/{job_id}/result      — fetch completed result
  POST /api/v1/jobs/{job_id}/retry       — re-queue a failed job
"""
from __future__ import annotations

import hashlib
import io
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File

from api.auth.dependencies import get_current_user
from api.models import (
    AnalyzeResponse,
    AngleStatResult,
    CoachingReportResult,
    FrameData,
    JobResultResponse,
    JobStatusResponse,
    MetricsResult,
    PerSwingAnalysis,
    PerSwingMetricsResult,
    ReferencePoseResult,
    SwingCoachingResult,
    SwingEventResult,
)
from api.services import job_store, storage
from api.tasks.analyze import run_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

_ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
_CHUNK_SIZE = 65536  # 64 KB
_MAX_REFERENCE_MB = 50


@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
async def create_analysis(
    file: UploadFile = File(...),
    activity: str = Form("tennis"),
    current_user: dict = Depends(get_current_user),
):
    """
    Accept an uploaded video, push it to S3, and enqueue a Celery analysis task.
    The authenticated user's ID (from JWT) is passed to the task so the completed
    session is persisted to Postgres for history/progress tracking.

    Same video file (identified by SHA-256) is deduplicated per user — the S3
    upload is skipped and the existing object reused.
    """
    from activities import get_activity
    import os

    # Validate activity before doing any expensive work
    try:
        get_activity(activity)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    user_id = current_user["sub"]

    # Read the upload into memory while computing its SHA-256 hash
    sha256 = hashlib.sha256()
    buf = io.BytesIO()
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        sha256.update(chunk)
        buf.write(chunk)
    file_hash = sha256.hexdigest()
    buf.seek(0)

    # Check video deduplication cache
    cached_s3_key = job_store.get_video_cache(user_id, file_hash)
    if cached_s3_key:
        logger.info("Video cache hit for user=%s hash=%s key=%s", user_id, file_hash, cached_s3_key)
        s3_key = cached_s3_key
    else:
        job_id_for_key = str(uuid.uuid4())
        s3_key = f"uploads/{job_id_for_key}/{file.filename}"
        storage.upload_fileobj(buf, s3_key)
        job_store.set_video_cache(user_id, file_hash, s3_key)
        logger.info("Video uploaded to S3 for user=%s hash=%s key=%s", user_id, file_hash, s3_key)

    # Create Redis job record (user-scoped)
    job_id = str(uuid.uuid4())
    original_filename = file.filename or ""
    job_store.create_job(job_id, user_id=user_id, original_filename=original_filename, activity=activity)

    # Enqueue Celery task; user_id always present (auth is mandatory)
    run_analysis.delay(job_id, s3_key, original_filename, user_id=user_id, activity=activity)

    return AnalyzeResponse(job_id=job_id, status="pending")


@router.post("/jobs/{job_id}/retry", response_model=AnalyzeResponse, status_code=202)
async def retry_analysis(
    job_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Re-queue a failed or stuck-running job from the furthest completed checkpoint.

    - If ``frame_data`` AND ``metrics`` are both set → skip to coaching step
    - Otherwise → re-run from the beginning (video is already on S3)

    Accepts jobs in ``failed`` or ``running`` state so users can cancel a
    frozen pipeline and restart from the last good checkpoint.
    """
    record = job_store.get_job(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if record.get("user_id") != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Access denied.")
    if record.get("status") not in ("failed", "running", "completed"):
        raise HTTPException(
            status_code=409,
            detail=f"Job '{job_id}' cannot be retried: status is '{record.get('status')}'.",
        )

    # Completed jobs always resume from coaching (video + metrics already done).
    # Failed/running jobs resume from the furthest good checkpoint.
    if record.get("status") == "completed" or (record.get("frame_data") and record.get("metrics")):
        resume_from = "coaching"
    else:
        resume_from = "start"

    logger.info("Retrying job=%s resume_from=%s", job_id, resume_from)

    # Reset job state so the client can poll again
    job_store.update_job(
        job_id,
        status="pending",
        progress=0,
        message="Retrying…",
        error=None,
    )

    original_filename = record.get("original_filename", "")
    run_analysis.delay(
        job_id,
        record["input_s3_key"],
        original_filename,
        user_id=record.get("user_id"),
        resume_from=resume_from,
    )

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

    # Build per-swing analyses by joining metrics + coaching dicts
    psm_raw = record.get("per_swing_metrics", [])
    psc_raw = record.get("per_swing_coaching", [])

    per_swing_analyses = [
        PerSwingAnalysis(
            swing_index=m["swing_index"],
            peak_frame=m["peak_frame"],
            window_start_frame=m["window_start_frame"],
            window_end_frame=m["window_end_frame"],
            metrics=PerSwingMetricsResult(**m),
            coaching=SwingCoachingResult(
                **(psc_raw[i] if i < len(psc_raw) else {"swing_index": m["swing_index"]})
            ),
        )
        for i, m in enumerate(psm_raw)
    ]

    # Load activity config for display metadata
    from activities import get_activity as _get_activity
    activity_id = record.get("activity", "tennis")
    try:
        activity_cfg = _get_activity(activity_id)
        activity_display_name = activity_cfg.display_name
        coaching_labels = activity_cfg.coaching_labels
        event_singular = activity_cfg.event_singular
        event_plural = activity_cfg.event_plural
    except ValueError:
        activity_display_name = activity_id.capitalize()
        coaching_labels = {}
        event_singular = "swing"
        event_plural = "swings"

    # Generate fresh presigned URL for the original video
    input_url = storage.presigned_url(record["input_s3_key"])

    return JobResultResponse(
        job_id=job_id,
        status="completed",
        coaching_report=coaching,
        metrics=metrics,
        frame_data=[FrameData(**fd) for fd in record.get("frame_data", [])],
        input_video_url=input_url,
        fps=record["fps"],
        total_source_frames=record["total_source_frames"],
        per_swing_analyses=per_swing_analyses,
        activity=activity_id,
        activity_display_name=activity_display_name,
        coaching_labels=coaching_labels,
        event_singular=event_singular,
        event_plural=event_plural,
    )


@router.post("/reference", response_model=ReferencePoseResult)
async def analyze_reference_video(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Accept a short reference video clip, run pose detection, and return the
    averaged pose landmarks and key joint angles.  The result is used by the
    frontend diff canvas to render a ghost reference skeleton.
    """
    import asyncio
    import os

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    buf = await file.read()
    if len(buf) > _MAX_REFERENCE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Reference video too large (max {_MAX_REFERENCE_MB} MB)",
        )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _process_reference, buf)
    return result


def _process_reference(video_bytes: bytes) -> ReferencePoseResult:
    """Run in thread pool: pose-detect reference video, return averaged pose."""
    import os
    import tempfile

    import cv2
    import numpy as np

    from pipeline.pose_detector import PoseDetector
    from utils.math_helpers import angle_between_three_points

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name
    try:
        cap = cv2.VideoCapture(tmp_path)
        detector = PoseDetector()
        all_lm: list = []   # list of 33-landmark frames
        total = 0
        detected = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            total += 1
            lr = detector.detect(frame, total - 1)
            if lr is not None:
                detected += 1
                all_lm.append(lr.landmarks)
        cap.release()
        detector.close()
    finally:
        os.unlink(tmp_path)

    if not all_lm:
        return ReferencePoseResult(avg_landmarks=[None] * 33)

    # Average each landmark across all detected frames
    avg_lm = []
    for idx in range(33):
        pts = [lm[idx] for lm in all_lm if lm[idx] is not None]
        if pts:
            avg_lm.append([
                float(np.mean([p[0] for p in pts])),
                float(np.mean([p[1] for p in pts])),
            ])
        else:
            avg_lm.append(None)

    def safe_angle(a: int, b: int, c: int):
        if avg_lm[a] and avg_lm[b] and avg_lm[c]:
            return angle_between_three_points(avg_lm[a], avg_lm[b], avg_lm[c])
        return None

    return ReferencePoseResult(
        avg_landmarks=avg_lm,
        right_elbow=safe_angle(12, 14, 16),   # shoulder-elbow-wrist
        left_elbow=safe_angle(11, 13, 15),
        right_shoulder=safe_angle(14, 12, 24), # elbow-shoulder-hip
        left_shoulder=safe_angle(13, 11, 23),
        right_knee=safe_angle(24, 26, 28),     # hip-knee-ankle
        left_knee=safe_angle(23, 25, 27),
        frames_analyzed=total,
        detection_rate=detected / max(total, 1),
    )
