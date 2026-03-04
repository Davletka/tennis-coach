"""
Joint angle computation, event detection, and metric aggregation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from config import (
    Landmarks,
    MIN_SWING_INTERVAL,
    WRIST_SPEED_THRESHOLD,
)
from pipeline.pose_detector import LandmarkResult
from utils.math_helpers import (
    angle_between_three_points,
    euclidean_distance,
    find_peaks,
    safe_max,
    safe_mean,
    safe_min,
    safe_std,
)


# ---------------------------------------------------------------------------
# Per-frame metrics
# ---------------------------------------------------------------------------

@dataclass
class FrameMetrics:
    frame_index: int

    # Joint angles in degrees (None if landmarks missing)
    right_elbow_angle: Optional[float] = None
    left_elbow_angle: Optional[float] = None
    right_shoulder_angle: Optional[float] = None
    left_shoulder_angle: Optional[float] = None
    right_knee_angle: Optional[float] = None
    left_knee_angle: Optional[float] = None

    # Body mechanics
    torso_rotation: Optional[float] = None   # degrees
    stance_width: Optional[float] = None     # normalized by hip width

    # CoM (center of mass) — average of hip midpoint x, normalized
    com_x: Optional[float] = None

    # Wrist speed (dominant / right wrist, normalized)
    right_wrist_speed: Optional[float] = None
    left_wrist_speed: Optional[float] = None

    # Wrist height relative to hip midpoint (negative = wrist above hips)
    right_wrist_relative_y: Optional[float] = None


def compute_frame_metrics(
    result: Optional[LandmarkResult],
    prev_result: Optional[LandmarkResult],
    frame_width: int,
    frame_height: int,
) -> FrameMetrics:
    """Compute per-frame metrics from a LandmarkResult."""
    frame_idx = result.frame_index if result is not None else 0
    fm = FrameMetrics(frame_index=frame_idx)

    if result is None:
        return fm

    def px(idx: int) -> Optional[Tuple[float, float]]:
        """Pixel coordinates as floats."""
        pt = result.get_pixel(idx, frame_width, frame_height)
        return (float(pt[0]), float(pt[1])) if pt is not None else None

    # -- Right elbow angle (shoulder → elbow → wrist) --
    rs = px(Landmarks.RIGHT_SHOULDER)
    re = px(Landmarks.RIGHT_ELBOW)
    rw = px(Landmarks.RIGHT_WRIST)
    if rs and re and rw:
        fm.right_elbow_angle = angle_between_three_points(rs, re, rw)

    # -- Left elbow angle --
    ls = px(Landmarks.LEFT_SHOULDER)
    le = px(Landmarks.LEFT_ELBOW)
    lw = px(Landmarks.LEFT_WRIST)
    if ls and le and lw:
        fm.left_elbow_angle = angle_between_three_points(ls, le, lw)

    # -- Right shoulder angle (elbow → shoulder → hip) --
    rh = px(Landmarks.RIGHT_HIP)
    if rs and re and rh:
        fm.right_shoulder_angle = angle_between_three_points(re, rs, rh)

    # -- Left shoulder angle --
    lh = px(Landmarks.LEFT_HIP)
    if ls and le and lh:
        fm.left_shoulder_angle = angle_between_three_points(le, ls, lh)

    # -- Right knee angle (hip → knee → ankle) --
    rk = px(Landmarks.RIGHT_KNEE)
    ra = px(Landmarks.RIGHT_ANKLE)
    if rh and rk and ra:
        fm.right_knee_angle = angle_between_three_points(rh, rk, ra)

    # -- Left knee angle --
    lk = px(Landmarks.LEFT_KNEE)
    la = px(Landmarks.LEFT_ANKLE)
    if lh and lk and la:
        fm.left_knee_angle = angle_between_three_points(lh, lk, la)

    # -- Torso rotation (angle between shoulder line and hip line) --
    if rs and ls and rh and lh:
        shoulder_vec = np.array(rs) - np.array(ls)
        hip_vec = np.array(rh) - np.array(lh)
        # Angle between vectors
        def _vec_angle(v1: np.ndarray, v2: np.ndarray) -> float:
            n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if n1 == 0 or n2 == 0:
                return 0.0
            cos = np.clip(np.dot(v1, v2) / (n1 * n2), -1, 1)
            return float(np.degrees(np.arccos(cos)))

        fm.torso_rotation = _vec_angle(shoulder_vec, hip_vec)

    # -- Stance width (normalized by hip width) --
    la_pt = px(Landmarks.LEFT_ANKLE)
    ra_pt = px(Landmarks.RIGHT_ANKLE)
    if la_pt and ra_pt and lh and rh:
        ankle_width = euclidean_distance(la_pt, ra_pt)
        hip_width = euclidean_distance(lh, rh)
        if hip_width > 0:
            fm.stance_width = ankle_width / hip_width

    # -- CoM lateral position (normalized x) --
    if lh and rh:
        fm.com_x = ((lh[0] + rh[0]) / 2.0) / frame_width
        hip_mid_y = (lh[1] + rh[1]) / 2.0
        if rw:
            # Negative = wrist above hips, positive = wrist below hips
            fm.right_wrist_relative_y = (rw[1] - hip_mid_y) / frame_height

    # -- Wrist speed (pixels/frame, normalized by frame diagonal) --
    diag = float(np.sqrt(frame_width ** 2 + frame_height ** 2))
    if prev_result is not None:
        prev_rw = prev_result.get_pixel(Landmarks.RIGHT_WRIST, frame_width, frame_height)
        if rw and prev_rw:
            fm.right_wrist_speed = euclidean_distance(
                (float(rw[0]), float(rw[1])),
                (float(prev_rw[0]), float(prev_rw[1])),
            ) / diag

        prev_lw = prev_result.get_pixel(Landmarks.LEFT_WRIST, frame_width, frame_height)
        if lw and prev_lw:
            fm.left_wrist_speed = euclidean_distance(
                (float(lw[0]), float(lw[1])),
                (float(prev_lw[0]), float(prev_lw[1])),
            ) / diag

    return fm


# ---------------------------------------------------------------------------
# Aggregated metrics
# ---------------------------------------------------------------------------

@dataclass
class AngleStat:
    mean: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    std: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            "mean": round(self.mean, 1) if self.mean is not None else None,
            "min": round(self.min, 1) if self.min is not None else None,
            "max": round(self.max, 1) if self.max is not None else None,
            "std": round(self.std, 1) if self.std is not None else None,
        }


@dataclass
class SwingEvent:
    frame_index: int
    wrist_speed: float
    com_x: Optional[float] = None
    motion_type: str = "unknown"


@dataclass
class AggregatedMetrics:
    # Joint angle stats
    right_elbow: AngleStat = field(default_factory=AngleStat)
    left_elbow: AngleStat = field(default_factory=AngleStat)
    right_shoulder: AngleStat = field(default_factory=AngleStat)
    left_shoulder: AngleStat = field(default_factory=AngleStat)
    right_knee: AngleStat = field(default_factory=AngleStat)
    left_knee: AngleStat = field(default_factory=AngleStat)

    # Body mechanics
    torso_rotation_mean: Optional[float] = None
    torso_rotation_max: Optional[float] = None
    stance_width_mean: Optional[float] = None

    # Swing events
    swing_events: List[SwingEvent] = field(default_factory=list)
    swing_count: int = 0

    # CoM range
    com_x_range: Optional[float] = None  # max - min lateral shift

    # Detection stats
    frames_analyzed: int = 0
    pose_detected_frames: int = 0

    @property
    def detection_rate(self) -> float:
        if self.frames_analyzed == 0:
            return 0.0
        return self.pose_detected_frames / self.frames_analyzed


def _angle_stat(values: List[Optional[float]]) -> AngleStat:
    return AngleStat(
        mean=safe_mean(values),
        min=safe_min(values),
        max=safe_max(values),
        std=safe_std(values),
    )


# ---------------------------------------------------------------------------
# Per-swing metrics
# ---------------------------------------------------------------------------

SWING_WINDOW_BEFORE = 15  # frames before peak
SWING_WINDOW_AFTER  = 30  # frames after peak (includes follow-through)


@dataclass
class PerSwingMetrics:
    swing_index: int
    peak_frame: int
    window_start_frame: int
    window_end_frame: int
    peak_wrist_speed: float
    com_x_at_peak: Optional[float] = None
    right_elbow: AngleStat = field(default_factory=AngleStat)
    left_elbow:  AngleStat = field(default_factory=AngleStat)
    right_shoulder: AngleStat = field(default_factory=AngleStat)
    left_shoulder:  AngleStat = field(default_factory=AngleStat)
    right_knee:  AngleStat = field(default_factory=AngleStat)
    left_knee:   AngleStat = field(default_factory=AngleStat)
    torso_rotation_mean: Optional[float] = None
    torso_rotation_max:  Optional[float] = None
    stance_width_mean:   Optional[float] = None
    com_x_range:         Optional[float] = None

    # Contact-point angles (peak frame ± 2 frames average)
    right_elbow_at_contact:    Optional[float] = None
    left_elbow_at_contact:     Optional[float] = None
    right_shoulder_at_contact: Optional[float] = None
    left_shoulder_at_contact:  Optional[float] = None
    right_knee_at_contact:     Optional[float] = None
    left_knee_at_contact:      Optional[float] = None
    torso_rotation_at_contact: Optional[float] = None

    # How much torso rotation changed during the swing (hip-shoulder kinematic chain)
    torso_rotation_delta: Optional[float] = None

    # Wrist height relative to hips at contact (negative = wrist above hips = high contact)
    right_wrist_y_at_contact: Optional[float] = None

    # Motion classification label set by activity classifier
    motion_type: str = "unknown"


def compute_per_swing_metrics(
    frame_metrics: List[FrameMetrics],
    swing_events: List[SwingEvent],
    window_before: int = SWING_WINDOW_BEFORE,
    window_after:  int = SWING_WINDOW_AFTER,
) -> List[PerSwingMetrics]:
    result = []
    for i, event in enumerate(swing_events):
        start = max(0, event.frame_index - window_before)
        end   = min(len(frame_metrics) - 1, event.frame_index + window_after)
        window = frame_metrics[start:end + 1]

        com_vals = [fm.com_x for fm in window if fm.com_x is not None]
        psm = PerSwingMetrics(
            swing_index=i, peak_frame=event.frame_index,
            window_start_frame=start, window_end_frame=end,
            peak_wrist_speed=event.wrist_speed, com_x_at_peak=event.com_x,
            right_elbow=    _angle_stat([fm.right_elbow_angle    for fm in window]),
            left_elbow=     _angle_stat([fm.left_elbow_angle     for fm in window]),
            right_shoulder= _angle_stat([fm.right_shoulder_angle for fm in window]),
            left_shoulder=  _angle_stat([fm.left_shoulder_angle  for fm in window]),
            right_knee=     _angle_stat([fm.right_knee_angle     for fm in window]),
            left_knee=      _angle_stat([fm.left_knee_angle      for fm in window]),
            torso_rotation_mean=safe_mean([fm.torso_rotation for fm in window]),
            torso_rotation_max= safe_max ([fm.torso_rotation for fm in window]),
            stance_width_mean=  safe_mean([fm.stance_width   for fm in window]),
            com_x_range=float(max(com_vals) - min(com_vals)) if com_vals else None,
        )

        # Contact-point angles: average of peak ± 2 frames
        CONTACT_HALF = 2
        cs = max(0, event.frame_index - CONTACT_HALF)
        ce = min(len(frame_metrics) - 1, event.frame_index + CONTACT_HALF)
        contact = frame_metrics[cs:ce + 1]
        psm.right_elbow_at_contact    = safe_mean([fm.right_elbow_angle    for fm in contact])
        psm.left_elbow_at_contact     = safe_mean([fm.left_elbow_angle     for fm in contact])
        psm.right_shoulder_at_contact = safe_mean([fm.right_shoulder_angle for fm in contact])
        psm.left_shoulder_at_contact  = safe_mean([fm.left_shoulder_angle  for fm in contact])
        psm.right_knee_at_contact     = safe_mean([fm.right_knee_angle     for fm in contact])
        psm.left_knee_at_contact      = safe_mean([fm.left_knee_angle      for fm in contact])
        psm.torso_rotation_at_contact = safe_mean([fm.torso_rotation       for fm in contact])
        psm.right_wrist_y_at_contact  = safe_mean([fm.right_wrist_relative_y for fm in contact])

        # Torso rotation delta: how much the torso rotated during the swing window
        torso_in_window = [fm.torso_rotation for fm in window if fm.torso_rotation is not None]
        if len(torso_in_window) >= 2:
            psm.torso_rotation_delta = float(max(torso_in_window) - min(torso_in_window))

        psm.motion_type = event.motion_type
        result.append(psm)
    return result


def _default_detect_events(frame_metrics: List[FrameMetrics]) -> List[SwingEvent]:
    """Default event detection: tennis swing peaks via combined wrist speed."""
    right_speeds: List[Optional[float]] = [fm.right_wrist_speed for fm in frame_metrics]
    left_speeds: List[Optional[float]] = [fm.left_wrist_speed for fm in frame_metrics]

    combined_speeds: List[Optional[float]] = []
    for rs, ls in zip(right_speeds, left_speeds):
        vals = [v for v in (rs, ls) if v is not None]
        combined_speeds.append(max(vals) if vals else None)

    peak_indices = find_peaks(
        combined_speeds,
        threshold=WRIST_SPEED_THRESHOLD,
        min_distance=MIN_SWING_INTERVAL,
    )

    events = []
    for idx in peak_indices:
        speed = combined_speeds[idx]
        com_x = frame_metrics[idx].com_x if idx < len(frame_metrics) else None
        events.append(SwingEvent(frame_index=idx, wrist_speed=speed or 0.0, com_x=com_x))
    return events


def _trim_idle_frames(frame_metrics: List[FrameMetrics]) -> List[FrameMetrics]:
    """Return frame_metrics with leading/trailing idle frames removed.

    An idle frame is one where all wrist speeds and joint angles are None or zero.
    Frame index values on each FrameMetrics are preserved as-is.
    """
    def _is_active(fm: FrameMetrics) -> bool:
        motion_values = [
            fm.right_wrist_speed, fm.left_wrist_speed,
            fm.right_knee_angle, fm.left_knee_angle,
            fm.right_elbow_angle, fm.left_elbow_angle,
        ]
        return any(v is not None and v != 0 for v in motion_values)

    first = 0
    while first < len(frame_metrics) and not _is_active(frame_metrics[first]):
        first += 1

    last = len(frame_metrics) - 1
    while last > first and not _is_active(frame_metrics[last]):
        last -= 1

    return frame_metrics[first:last + 1] if first <= last else frame_metrics


def aggregate_metrics(
    frame_metrics: List[FrameMetrics],
    pose_results: List[Optional[LandmarkResult]],
    detect_events_fn: Optional[Callable] = None,
    filter_events_fn: Optional[Callable] = None,
) -> AggregatedMetrics:
    """Aggregate per-frame metrics into a summary.

    ``detect_events_fn`` receives the full ``frame_metrics`` list and returns
    ``List[SwingEvent]``.  If omitted, the default tennis wrist-speed detector
    is used (backward-compatible).
    """
    agg = AggregatedMetrics()
    agg.frames_analyzed = len(frame_metrics)
    agg.pose_detected_frames = sum(1 for r in pose_results if r is not None)

    agg.right_elbow = _angle_stat([fm.right_elbow_angle for fm in frame_metrics])
    agg.left_elbow = _angle_stat([fm.left_elbow_angle for fm in frame_metrics])
    agg.right_shoulder = _angle_stat([fm.right_shoulder_angle for fm in frame_metrics])
    agg.left_shoulder = _angle_stat([fm.left_shoulder_angle for fm in frame_metrics])
    agg.right_knee = _angle_stat([fm.right_knee_angle for fm in frame_metrics])
    agg.left_knee = _angle_stat([fm.left_knee_angle for fm in frame_metrics])

    torso_vals = [fm.torso_rotation for fm in frame_metrics]
    agg.torso_rotation_mean = safe_mean(torso_vals)
    agg.torso_rotation_max = safe_max(torso_vals)

    stance_vals = [fm.stance_width for fm in frame_metrics]
    agg.stance_width_mean = safe_mean(stance_vals)

    # CoM lateral range
    com_vals = [fm.com_x for fm in frame_metrics if fm.com_x is not None]
    if com_vals:
        agg.com_x_range = float(max(com_vals) - min(com_vals))

    # Trim idle frames before event detection
    trimmed = _trim_idle_frames(frame_metrics)

    # Event detection — delegate to provided function or use default tennis detector
    detector = detect_events_fn if detect_events_fn is not None else _default_detect_events
    agg.swing_events = detector(trimmed)

    # Activity-specific filtering
    if filter_events_fn is not None:
        agg.swing_events = filter_events_fn(agg.swing_events, trimmed)

    agg.swing_count = len(agg.swing_events)
    return agg
