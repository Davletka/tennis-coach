"""
Pydantic request/response models for the CourtCoach API.
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
    target_angles: Optional[dict] = None   # keys: right_elbow, left_elbow, right_shoulder, left_shoulder, right_knee, left_knee


class ReferencePoseResult(BaseModel):
    """Average pose extracted from a reference video clip."""
    # 33 landmarks; each is [x, y] normalized [0,1], or null if not detected
    avg_landmarks: List[Optional[List[float]]]
    right_elbow: Optional[float] = None
    left_elbow: Optional[float] = None
    right_shoulder: Optional[float] = None
    left_shoulder: Optional[float] = None
    right_knee: Optional[float] = None
    left_knee: Optional[float] = None
    frames_analyzed: int = 0
    detection_rate: float = 0.0


class FrameData(BaseModel):
    """Per-frame landmark positions and joint angles for frontend canvas rendering."""
    # 33-element list; each element is [x, y, visibility] or null if below threshold.
    # None if no pose was detected for this frame.
    lm: Optional[List[Optional[List[float]]]] = None
    re: Optional[float] = None  # right elbow angle (degrees)
    le: Optional[float] = None  # left elbow angle
    rs: Optional[float] = None  # right shoulder angle
    ls: Optional[float] = None  # left shoulder angle
    rk: Optional[float] = None  # right knee angle
    lk: Optional[float] = None  # left knee angle


class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str
    picture: str
    created_at: datetime
    last_login: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PerSwingMetricsResult(BaseModel):
    swing_index: int
    peak_frame: int
    window_start_frame: int
    window_end_frame: int
    peak_wrist_speed: float
    com_x_at_peak: Optional[float] = None
    right_elbow: AngleStatResult = AngleStatResult()
    left_elbow: AngleStatResult = AngleStatResult()
    right_shoulder: AngleStatResult = AngleStatResult()
    left_shoulder: AngleStatResult = AngleStatResult()
    right_knee: AngleStatResult = AngleStatResult()
    left_knee: AngleStatResult = AngleStatResult()
    torso_rotation_mean: Optional[float] = None
    torso_rotation_max: Optional[float] = None
    stance_width_mean: Optional[float] = None
    com_x_range: Optional[float] = None


class SwingCoachingResult(BaseModel):
    swing_index: int = 0
    quick_note: str = ""
    swing_mechanics: str = ""
    footwork_movement: str = ""
    stance_posture: str = ""
    shot_selection_tactics: str = ""
    top_3_priorities: List[str] = []


class PerSwingAnalysis(BaseModel):
    swing_index: int
    peak_frame: int
    window_start_frame: int
    window_end_frame: int
    metrics: PerSwingMetricsResult
    coaching: SwingCoachingResult


class JobResultResponse(BaseModel):
    job_id: str
    status: JobStatus
    coaching_report: CoachingReportResult
    metrics: MetricsResult
    frame_data: List[FrameData]
    input_video_url: str
    fps: float
    total_source_frames: int
    per_swing_analyses: List[PerSwingAnalysis] = []


# ---------------------------------------------------------------------------
# History / Progress / Compare models
# ---------------------------------------------------------------------------

class SessionSummary(BaseModel):
    """One row returned by GET /users/{user_id}/history."""
    session_id: str
    job_id: str
    recorded_at: datetime
    original_filename: Optional[str]
    fps: float
    total_source_frames: int
    frames_analyzed: int
    detection_rate: float
    annotated_video_url: str
    input_video_url: str
    metrics: dict
    coaching: dict


class SessionListResponse(BaseModel):
    sessions: List[SessionSummary]
    total: int
    limit: int
    offset: int


class ProgressDataPoint(BaseModel):
    """One time-series data point for GET /users/{user_id}/progress."""
    session_id: str
    recorded_at: datetime
    right_elbow_mean: Optional[float] = None
    left_elbow_mean: Optional[float] = None
    right_shoulder_mean: Optional[float] = None
    left_shoulder_mean: Optional[float] = None
    right_knee_mean: Optional[float] = None
    left_knee_mean: Optional[float] = None
    torso_rotation_mean: Optional[float] = None
    stance_width_mean: Optional[float] = None
    com_x_range: Optional[float] = None
    swing_count: Optional[int] = None
    detection_rate: float


class ProgressResponse(BaseModel):
    data_points: List[ProgressDataPoint]
    total: int


class CompareRequest(BaseModel):
    session_a_id: str
    session_b_id: str


class MetricDelta(BaseModel):
    metric_name: str
    session_a_value: Optional[float]
    session_b_value: Optional[float]
    delta: Optional[float]        # B minus A
    direction: str                # "improved", "regressed", "unchanged"


class DeltaCoachingReport(BaseModel):
    overall_progress_summary: str = ""
    improvements: List[str] = []
    regressions: List[str] = []
    unchanged_areas: List[str] = []
    top_3_priorities: List[str] = []
    raw_response: str = ""


class CompareResponse(BaseModel):
    session_a_id: str
    session_b_id: str
    metric_deltas: List[MetricDelta]
    delta_coaching: DeltaCoachingReport
