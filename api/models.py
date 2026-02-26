"""
Pydantic request/response models for the Tennis Coach API.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared / base
# ---------------------------------------------------------------------------

JobStatus = Literal["pending", "running", "completed", "failed"]


# ---------------------------------------------------------------------------
# POST /api/v1/analyze  — response
# ---------------------------------------------------------------------------

class AnalyzeResponse(BaseModel):
    job_id: str
    status: JobStatus = "pending"


# ---------------------------------------------------------------------------
# GET /api/v1/jobs/{job_id}  — response
# ---------------------------------------------------------------------------

class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int = 0          # 0–100
    message: str = ""
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# GET /api/v1/jobs/{job_id}/result  — response
# ---------------------------------------------------------------------------

class AngleStatResult(BaseModel):
    mean: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    std: Optional[float] = None


class SwingEventResult(BaseModel):
    frame_index: int
    wrist_speed: float
    com_x: Optional[float] = None


class MetricsResult(BaseModel):
    right_elbow: AngleStatResult
    left_elbow: AngleStatResult
    right_shoulder: AngleStatResult
    left_shoulder: AngleStatResult
    right_knee: AngleStatResult
    left_knee: AngleStatResult
    torso_rotation_mean: Optional[float] = None
    torso_rotation_max: Optional[float] = None
    stance_width_mean: Optional[float] = None
    com_x_range: Optional[float] = None
    swing_count: int = 0
    swing_events: List[SwingEventResult] = []
    frames_analyzed: int = 0
    pose_detected_frames: int = 0
    detection_rate: float = 0.0


class CoachingReportResult(BaseModel):
    swing_mechanics: str = ""
    footwork_movement: str = ""
    stance_posture: str = ""
    shot_selection_tactics: str = ""
    top_3_priorities: List[str] = []


class JobResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    coaching_report: CoachingReportResult
    metrics: MetricsResult
    annotated_video_url: str
    input_video_url: str
    fps: float
    total_source_frames: int
