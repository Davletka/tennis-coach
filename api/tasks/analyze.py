"""
Celery task: download video from S3, run the full pipeline, upload results.

Pipeline imports are deferred inside the task function so that MediaPipe is
not loaded in the FastAPI/API process — only in the Celery worker.
"""
from __future__ import annotations

import os
import sys
import tempfile

# Ensure the project root is on sys.path so pipeline imports work
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from celery_app import app
from api.services import job_store, storage


@app.task(bind=True, max_retries=0, name="api.tasks.analyze.run_analysis")
def run_analysis(
    self,
    job_id: str,
    input_s3_key: str,
    original_filename: str,
    user_id: str = None,
) -> None:
    """
    Full analysis pipeline as a Celery task.

    Progress checkpoints are written to Redis so the client can poll for status.
    All temporary files live inside a TemporaryDirectory — guaranteed cleanup.
    """
    # Deferred imports — keep MediaPipe out of the API process
    from pipeline.video_io import extract_frames, frames_to_video
    from pipeline.pose_detector import PoseDetector
    from pipeline.metrics import compute_frame_metrics, aggregate_metrics
    from pipeline.annotator import annotate_all_frames
    from pipeline.coach import get_coaching_feedback
    from api.settings import settings

    def _progress(pct: int, msg: str) -> None:
        job_store.update_job(job_id, status="running", progress=pct, message=msg)

    try:
        job_store.update_job(job_id, status="running", progress=5, message="Downloading video")

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

            agg = aggregate_metrics(frame_metrics, pose_results)

            # ----------------------------------------------------------------
            # 5. Annotate frames
            # ----------------------------------------------------------------
            _progress(70, "Annotating video")
            swing_indices = {e.frame_index for e in agg.swing_events}
            annotated_frames = annotate_all_frames(
                frames, pose_results, frame_metrics, swing_indices
            )

            # ----------------------------------------------------------------
            # 6. Encode annotated video
            # ----------------------------------------------------------------
            _progress(80, "Encoding annotated video")
            annotated_path = os.path.join(tmpdir, f"annotated_{original_filename}")
            frames_to_video(annotated_frames, annotated_path, fps)

            # ----------------------------------------------------------------
            # 7. Upload annotated video to S3
            # ----------------------------------------------------------------
            _progress(90, "Uploading to S3")
            annotated_s3_key = f"results/{job_id}/annotated_{original_filename}"
            storage.upload_file(annotated_path, annotated_s3_key)

            # ----------------------------------------------------------------
            # 8. Get Claude coaching feedback
            # ----------------------------------------------------------------
            _progress(95, "Generating coaching feedback")
            report = get_coaching_feedback(
                agg,
                fps,
                total_source_frames,
                api_key=settings.anthropic_api_key,
            )

            # ----------------------------------------------------------------
            # 9. Serialise metrics for Redis
            # ----------------------------------------------------------------
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
                    }
                    for e in agg.swing_events
                ],
                "frames_analyzed": agg.frames_analyzed,
                "pose_detected_frames": agg.pose_detected_frames,
                "detection_rate": round(agg.detection_rate, 3),
            }

            coaching_dict = {
                "swing_mechanics": report.swing_mechanics,
                "footwork_movement": report.footwork_movement,
                "stance_posture": report.stance_posture,
                "shot_selection_tactics": report.shot_selection_tactics,
                "top_3_priorities": report.top_3_priorities,
            }

            # ----------------------------------------------------------------
            # 10. Mark job completed
            # ----------------------------------------------------------------
            job_store.update_job(
                job_id,
                status="completed",
                progress=100,
                message="Analysis complete",
                input_s3_key=input_s3_key,
                annotated_s3_key=annotated_s3_key,
                fps=fps,
                total_source_frames=total_source_frames,
                metrics=metrics_dict,
                coaching_report=coaching_dict,
            )

            # ----------------------------------------------------------------
            # 11. Persist session to Postgres (only when user_id is provided)
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
                                annotated_s3_key,
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
