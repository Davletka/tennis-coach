"""
Celery task: download video from S3, run the full pipeline, upload results.

Pipeline imports are deferred inside the task function so that MediaPipe is
not loaded in the FastAPI/API process — only in the Celery worker.
"""
from __future__ import annotations

import os
import tempfile
from typing import Dict, Optional

from celery_app import app
from api.services import job_store, storage


# ---------------------------------------------------------------------------
# Helpers: reconstruct metrics dataclasses from stored dicts
# ---------------------------------------------------------------------------

def _metrics_from_dict(d: dict):
    """Reconstruct an AggregatedMetrics dataclass from a serialised metrics dict."""
    from pipeline.metrics import AggregatedMetrics, AngleStat, SwingEvent

    def _angle(ad: Optional[dict]) -> AngleStat:
        if ad is None:
            return AngleStat()
        return AngleStat(
            mean=ad.get("mean"),
            min=ad.get("min"),
            max=ad.get("max"),
            std=ad.get("std"),
        )

    swing_events = [
        SwingEvent(
            frame_index=e["frame_index"],
            wrist_speed=e["wrist_speed"],
            com_x=e.get("com_x"),
            motion_type=e.get("motion_type", "unknown"),
        )
        for e in d.get("swing_events", [])
    ]

    agg = AggregatedMetrics(
        right_elbow=_angle(d.get("right_elbow")),
        left_elbow=_angle(d.get("left_elbow")),
        right_shoulder=_angle(d.get("right_shoulder")),
        left_shoulder=_angle(d.get("left_shoulder")),
        right_knee=_angle(d.get("right_knee")),
        left_knee=_angle(d.get("left_knee")),
        torso_rotation_mean=d.get("torso_rotation_mean"),
        torso_rotation_max=d.get("torso_rotation_max"),
        stance_width_mean=d.get("stance_width_mean"),
        com_x_range=d.get("com_x_range"),
        swing_events=swing_events,
        swing_count=d.get("swing_count", 0),
        frames_analyzed=d.get("frames_analyzed", 0),
        pose_detected_frames=d.get("pose_detected_frames", 0),
    )
    return agg


def _per_swing_from_dict(d: dict):
    """Reconstruct a PerSwingMetrics dataclass from a serialised dict."""
    from pipeline.metrics import PerSwingMetrics, AngleStat

    def _angle(ad: Optional[dict]) -> AngleStat:
        if ad is None:
            return AngleStat()
        return AngleStat(
            mean=ad.get("mean"),
            min=ad.get("min"),
            max=ad.get("max"),
            std=ad.get("std"),
        )

    return PerSwingMetrics(
        swing_index=d["swing_index"],
        peak_frame=d["peak_frame"],
        window_start_frame=d["window_start_frame"],
        window_end_frame=d["window_end_frame"],
        peak_wrist_speed=d["peak_wrist_speed"],
        com_x_at_peak=d.get("com_x_at_peak"),
        right_elbow=_angle(d.get("right_elbow")),
        left_elbow=_angle(d.get("left_elbow")),
        right_shoulder=_angle(d.get("right_shoulder")),
        left_shoulder=_angle(d.get("left_shoulder")),
        right_knee=_angle(d.get("right_knee")),
        left_knee=_angle(d.get("left_knee")),
        torso_rotation_mean=d.get("torso_rotation_mean"),
        torso_rotation_max=d.get("torso_rotation_max"),
        stance_width_mean=d.get("stance_width_mean"),
        com_x_range=d.get("com_x_range"),
        motion_type=d.get("motion_type", "unknown"),
    )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@app.task(bind=True, max_retries=0, name="api.tasks.analyze.run_analysis")
def run_analysis(
    self,
    job_id: str,
    input_s3_key: str,
    original_filename: str,
    user_id: str = None,
    resume_from: str = "start",
    activity: str = "tennis",
) -> None:
    """
    Full analysis pipeline as a Celery task.

    Progress checkpoints are written to Redis so the client can poll for status.
    All temporary files live inside a TemporaryDirectory — guaranteed cleanup.

    ``resume_from`` controls where the pipeline begins:
      - ``"start"``    — full pipeline; video already on S3, no re-upload needed
      - ``"coaching"`` — skip download/pose/annotation; re-run Claude only
    """
    # Deferred imports — keep MediaPipe out of the API process
    from pipeline.video_io import extract_frames
    from pipeline.pose_detector import PoseDetector
    from pipeline.metrics import compute_frame_metrics, aggregate_metrics
    from pipeline.coach import get_coaching_feedback
    from config import VISIBILITY_THRESHOLD
    from api.settings import settings
    from activities import get_activity

    activity_cfg = get_activity(activity)

    def _progress(pct: int, msg: str) -> None:
        job_store.update_job(job_id, status="running", progress=pct, message=msg)

    try:
        # ----------------------------------------------------------------
        # Fast path: skip straight to coaching if checkpoint is available
        # ----------------------------------------------------------------
        if resume_from == "coaching":
            event_plural = activity_cfg.event_plural
            _progress(75, f"Generating per-{activity_cfg.event_singular} analysis")
            job = job_store.get_job(job_id)
            agg = _metrics_from_dict(job["metrics"])
            fps = job["fps"]
            total_source_frames = job["total_source_frames"]

            # Re-run per-event coaching if metrics are available
            from pipeline.coach import get_per_swing_coaching
            per_swing_raw = job.get("per_swing_metrics", [])
            if per_swing_raw:
                per_swing_list = [_per_swing_from_dict(d) for d in per_swing_raw]
                n_events = len(per_swing_list)

                def _swing_cb_retry(done: int, total: int) -> None:
                    pct = 75 + int((done / total) * 13)
                    job_store.update_job(job_id, status="running", progress=pct,
                                        message=f"Generating per-{activity_cfg.event_singular} analysis ({done}/{total} {event_plural})")

                swing_coaching_list = get_per_swing_coaching(
                    per_swing_list, fps, api_key=settings.anthropic_api_key,
                    on_swing_done=_swing_cb_retry, activity_cfg=activity_cfg,
                )
                per_swing_coaching_dicts = [
                    {
                        "swing_index": sc.swing_index,
                        "quick_note": sc.quick_note,
                        "swing_mechanics": sc.swing_mechanics,
                        "footwork_movement": sc.footwork_movement,
                        "stance_posture": sc.stance_posture,
                        "shot_selection_tactics": sc.shot_selection_tactics,
                        "top_3_priorities": sc.top_3_priorities,
                    }
                    for sc in swing_coaching_list
                ]
                job_store.update_job(job_id, per_swing_coaching=per_swing_coaching_dicts)

            _progress(88, "Generating coaching feedback")
            report = get_coaching_feedback(
                agg,
                fps,
                total_source_frames,
                api_key=settings.anthropic_api_key,
                activity_cfg=activity_cfg,
            )

            coaching_dict = {
                "swing_mechanics": report.swing_mechanics,
                "footwork_movement": report.footwork_movement,
                "stance_posture": report.stance_posture,
                "shot_selection_tactics": report.shot_selection_tactics,
                "top_3_priorities": report.top_3_priorities,
            }

            job_store.update_job(
                job_id,
                status="completed",
                progress=100,
                message="Analysis complete",
                coaching_report=coaching_dict,
            )
            return

        # ----------------------------------------------------------------
        # Full pipeline (resume_from == "start")
        # ----------------------------------------------------------------
        # Persist input_s3_key immediately so the retry endpoint can always read it
        job_store.update_job(
            job_id,
            status="running",
            progress=5,
            message="Downloading video",
            input_s3_key=input_s3_key,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            # ----------------------------------------------------------------
            # 1. Download input video from S3
            # ----------------------------------------------------------------
            local_input = os.path.join(tmpdir, original_filename)
            import boto3
            from botocore.client import Config as BotoConfig
            r2 = boto3.client(
                "s3",
                endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.r2_access_key_id,
                aws_secret_access_key=settings.r2_secret_access_key,
                config=BotoConfig(signature_version="s3v4"),
            )
            r2.download_file(settings.r2_bucket_name, input_s3_key, local_input)

            # ----------------------------------------------------------------
            # 2. Extract frames
            # ----------------------------------------------------------------
            _progress(15, "Extracting frames")
            frames, fps, total_source_frames = extract_frames(local_input)

            if not frames:
                raise ValueError("No frames could be extracted from the video.")

            h, w = frames[0].shape[:2]

            # Persist fps + total_source_frames early so retry can read them
            job_store.update_job(
                job_id,
                original_filename=original_filename,
                fps=fps,
                total_source_frames=total_source_frames,
            )

            # ----------------------------------------------------------------
            # 3. Pose detection (progress 25 → 55)
            # ----------------------------------------------------------------
            _progress(25, "Running pose detection")
            with PoseDetector() as detector:
                pose_results = []
                n = len(frames)
                for i, frame in enumerate(frames):
                    result = detector.detect(frame, i)
                    pose_results.append(result)

                    # Update progress every 10% of frames
                    if n > 0 and i % max(1, n // 10) == 0:
                        pct = 25 + int((i / n) * 30)
                        job_store.update_job(
                            job_id,
                            status="running",
                            progress=pct,
                            message="Running pose detection",
                        )

            # ----------------------------------------------------------------
            # 4. Compute metrics
            # ----------------------------------------------------------------
            _progress(55, "Computing metrics")
            frame_metrics = []
            prev = None
            for i, result in enumerate(pose_results):
                fm = compute_frame_metrics(result, prev, w, h)
                frame_metrics.append(fm)
                prev = result

            agg = aggregate_metrics(
                frame_metrics, pose_results,
                detect_events_fn=activity_cfg.detect_events,
                filter_events_fn=activity_cfg.filter_events,
            )

            # Compute per-event metrics using activity window sizes
            from pipeline.metrics import compute_per_swing_metrics
            per_swing_list = compute_per_swing_metrics(
                frame_metrics, agg.swing_events,
                window_before=activity_cfg.window_before,
                window_after=activity_cfg.window_after,
            )

            # Checkpoint metrics before annotation (enables coaching-only retry)
            metrics_dict = {
                "right_elbow": agg.right_elbow.to_dict(),
                "left_elbow": agg.left_elbow.to_dict(),
                "right_shoulder": agg.right_shoulder.to_dict(),
                "left_shoulder": agg.left_shoulder.to_dict(),
                "right_knee": agg.right_knee.to_dict(),
                "left_knee": agg.left_knee.to_dict(),
                "torso_rotation_mean": round(agg.torso_rotation_mean, 1) if agg.torso_rotation_mean is not None else None,
                "torso_rotation_max": round(agg.torso_rotation_max, 1) if agg.torso_rotation_max is not None else None,
                "stance_width_mean": round(agg.stance_width_mean, 3) if agg.stance_width_mean is not None else None,
                "com_x_range": round(agg.com_x_range, 3) if agg.com_x_range is not None else None,
                "swing_count": agg.swing_count,
                "swing_events": [
                    {
                        "frame_index": e.frame_index,
                        "wrist_speed": round(e.wrist_speed, 4),
                        "com_x": round(e.com_x, 3) if e.com_x is not None else None,
                        "motion_type": e.motion_type,
                    }
                    for e in agg.swing_events
                ],
                "frames_analyzed": agg.frames_analyzed,
                "pose_detected_frames": agg.pose_detected_frames,
                "detection_rate": round(agg.detection_rate, 3),
            }
            per_swing_metrics_dicts = [
                {
                    "swing_index": p.swing_index,
                    "peak_frame": p.peak_frame,
                    "window_start_frame": p.window_start_frame,
                    "window_end_frame": p.window_end_frame,
                    "peak_wrist_speed": round(p.peak_wrist_speed, 4),
                    "com_x_at_peak": round(p.com_x_at_peak, 3) if p.com_x_at_peak is not None else None,
                    "right_elbow": p.right_elbow.to_dict(),
                    "left_elbow": p.left_elbow.to_dict(),
                    "right_shoulder": p.right_shoulder.to_dict(),
                    "left_shoulder": p.left_shoulder.to_dict(),
                    "right_knee": p.right_knee.to_dict(),
                    "left_knee": p.left_knee.to_dict(),
                    "torso_rotation_mean": round(p.torso_rotation_mean, 1) if p.torso_rotation_mean is not None else None,
                    "torso_rotation_max": round(p.torso_rotation_max, 1) if p.torso_rotation_max is not None else None,
                    "stance_width_mean": round(p.stance_width_mean, 3) if p.stance_width_mean is not None else None,
                    "com_x_range": round(p.com_x_range, 3) if p.com_x_range is not None else None,
                    "motion_type": p.motion_type,
                }
                for p in per_swing_list
            ]
            job_store.update_job(job_id, metrics=metrics_dict, per_swing_metrics=per_swing_metrics_dicts)

            # ----------------------------------------------------------------
            # 5. Serialize per-frame landmark + angle data for frontend rendering
            # ----------------------------------------------------------------
            _progress(65, "Preparing frame data")
            frame_data = []
            for pose_result, fm in zip(pose_results, frame_metrics):
                if pose_result is None:
                    lm = None
                else:
                    lm = [
                        [round(x, 4), round(y, 4), round(vis, 3)]
                        if vis >= VISIBILITY_THRESHOLD else None
                        for x, y, z, vis in pose_result.landmarks
                    ]
                frame_data.append({
                    "lm": lm,
                    "re": round(fm.right_elbow_angle, 1) if fm.right_elbow_angle is not None else None,
                    "le": round(fm.left_elbow_angle, 1) if fm.left_elbow_angle is not None else None,
                    "rs": round(fm.right_shoulder_angle, 1) if fm.right_shoulder_angle is not None else None,
                    "ls": round(fm.left_shoulder_angle, 1) if fm.left_shoulder_angle is not None else None,
                    "rk": round(fm.right_knee_angle, 1) if fm.right_knee_angle is not None else None,
                    "lk": round(fm.left_knee_angle, 1) if fm.left_knee_angle is not None else None,
                })

            # Checkpoint frame_data before Claude (enables coaching-only retry)
            job_store.update_job(job_id, frame_data=frame_data)

            # ----------------------------------------------------------------
            # 6. Per-event Claude coaching
            # ----------------------------------------------------------------
            event_singular = activity_cfg.event_singular
            event_plural = activity_cfg.event_plural
            _progress(75, f"Generating per-{event_singular} analysis (0/{len(per_swing_list)} {event_plural})")
            from pipeline.coach import get_per_swing_coaching

            def _swing_cb(done: int, total: int) -> None:
                pct = 75 + int((done / total) * 13)
                job_store.update_job(job_id, status="running", progress=pct,
                                     message=f"Generating per-{event_singular} analysis ({done}/{total} {event_plural})")

            swing_coaching_list = get_per_swing_coaching(
                per_swing_list, fps, api_key=settings.anthropic_api_key,
                on_swing_done=_swing_cb, activity_cfg=activity_cfg,
            )
            per_swing_coaching_dicts = [
                {
                    "swing_index": sc.swing_index,
                    "quick_note": sc.quick_note,
                    "swing_mechanics": sc.swing_mechanics,
                    "footwork_movement": sc.footwork_movement,
                    "stance_posture": sc.stance_posture,
                    "shot_selection_tactics": sc.shot_selection_tactics,
                    "top_3_priorities": sc.top_3_priorities,
                }
                for sc in swing_coaching_list
            ]
            job_store.update_job(job_id, per_swing_coaching=per_swing_coaching_dicts)

            # ----------------------------------------------------------------
            # 7. Get Claude overall coaching feedback
            # ----------------------------------------------------------------
            _progress(88, "Generating coaching feedback")
            report = get_coaching_feedback(
                agg,
                fps,
                total_source_frames,
                api_key=settings.anthropic_api_key,
                activity_cfg=activity_cfg,
            )

            coaching_dict = {
                "swing_mechanics": report.swing_mechanics,
                "footwork_movement": report.footwork_movement,
                "stance_posture": report.stance_posture,
                "shot_selection_tactics": report.shot_selection_tactics,
                "top_3_priorities": report.top_3_priorities,
            }

            # ----------------------------------------------------------------
            # 8. Mark job completed
            # ----------------------------------------------------------------
            job_store.update_job(
                job_id,
                status="completed",
                progress=100,
                message="Analysis complete",
                input_s3_key=input_s3_key,
                fps=fps,
                total_source_frames=total_source_frames,
                metrics=metrics_dict,
                coaching_report=coaching_dict,
            )

            # ----------------------------------------------------------------
            # 9. Persist session to Postgres (only when user_id is provided)
            # Celery worker has no async event loop, so use psycopg2 (sync).
            # ----------------------------------------------------------------
            if user_id is not None:
                import json as _json
                import psycopg2

                with psycopg2.connect(settings.database_url) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO players (user_id)
                            VALUES (%s::uuid)
                            ON CONFLICT (user_id) DO UPDATE
                                SET updated_at = NOW()
                            """,
                            (user_id,),
                        )
                        cur.execute(
                            """
                            INSERT INTO analysis_sessions (
                                user_id, job_id, original_filename,
                                fps, total_source_frames, frames_analyzed, detection_rate,
                                input_s3_key, annotated_s3_key, metrics, coaching
                            )
                            VALUES (
                                %s::uuid, %s, %s,
                                %s, %s, %s, %s,
                                %s, %s, %s::jsonb, %s::jsonb
                            )
                            ON CONFLICT (job_id) DO NOTHING
                            """,
                            (
                                user_id,
                                job_id,
                                original_filename,
                                fps,
                                total_source_frames,
                                metrics_dict.get("frames_analyzed", 0),
                                metrics_dict.get("detection_rate", 0.0),
                                input_s3_key,
                                input_s3_key,  # annotated_s3_key column: reuse input (no separate annotated video)
                                _json.dumps(metrics_dict),
                                _json.dumps(coaching_dict),
                            ),
                        )
                    conn.commit()

    except Exception as exc:
        job_store.update_job(
            job_id,
            status="failed",
            progress=0,
            message="Analysis failed",
            error=str(exc),
        )
        raise
