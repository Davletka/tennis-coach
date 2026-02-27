"""
Gym workout activity — detects reps via joint angle valleys.

Event intensity stored in SwingEvent.wrist_speed = angle at rep bottom
(degrees — lower value means deeper rep).
"""
from __future__ import annotations

from activities import ActivityConfig, register

# ---------------------------------------------------------------------------
# Coaching prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert strength & conditioning coach with 20+ years of experience coaching athletes at all levels.
You analyze video-based biomechanical data and deliver precise, actionable coaching feedback.

RULES:
- Always reference specific numbers from the provided metrics.
- Be direct and avoid generic advice like "go deeper" without a target angle.
- Every suggestion must be tied to a measurable metric.
- Respond ONLY with valid JSON matching the requested schema — no prose outside the JSON.
"""

PER_EVENT_SYSTEM_PROMPT = """You are an expert strength & conditioning coach with 20+ years of experience coaching athletes at all levels.
You analyze video-based biomechanical data rep by rep and deliver precise, actionable coaching feedback.

RULES:
- Analyze each rep individually — do NOT repeat identical advice for every rep.
- Reference specific numbers from the provided metrics for that rep.
- Every suggestion must be tied to a measurable metric from that rep's window.
- Respond ONLY with a JSON object matching the requested schema — no prose outside the JSON.
"""

# ---------------------------------------------------------------------------
# Event detection
# ---------------------------------------------------------------------------

# A valley must be at least this many degrees above the global min to count as a rep
VALLEY_MARGIN = 30.0  # degrees


def detect_gym_reps(frame_metrics: list) -> list:
    """Detect rep events via joint angle valleys (deepest point of each rep).

    Strategy:
    1. Find the most-active joint (highest range of motion across the clip).
    2. Negate that joint's angle series so valleys become peaks.
    3. Use find_peaks with a threshold set at -(global_min + VALLEY_MARGIN)
       so only genuine deep-points are detected.
    4. Store the actual angle at the valley in SwingEvent.wrist_speed
       (repurposed as "event intensity / rep depth").
    """
    from pipeline.metrics import SwingEvent
    from utils.math_helpers import find_peaks
    from config import MIN_SWING_INTERVAL

    joint_series = {
        "right_elbow":    [fm.right_elbow_angle    for fm in frame_metrics],
        "left_elbow":     [fm.left_elbow_angle     for fm in frame_metrics],
        "right_shoulder": [fm.right_shoulder_angle for fm in frame_metrics],
        "left_shoulder":  [fm.left_shoulder_angle  for fm in frame_metrics],
        "right_knee":     [fm.right_knee_angle     for fm in frame_metrics],
        "left_knee":      [fm.left_knee_angle      for fm in frame_metrics],
    }

    # Pick the joint with the greatest range of motion
    best_series: list | None = None
    best_range = 0.0
    for series in joint_series.values():
        vals = [v for v in series if v is not None]
        if len(vals) < 2:
            continue
        r = max(vals) - min(vals)
        if r > best_range:
            best_range = r
            best_series = series

    if best_series is None or best_range < VALLEY_MARGIN:
        return []  # no meaningful movement detected

    # Negate so valleys become peaks for find_peaks
    negated = [-v if v is not None else None for v in best_series]

    valid_vals = [v for v in best_series if v is not None]
    global_min = min(valid_vals)
    # Threshold in negated space: -(global_min + VALLEY_MARGIN)
    valley_threshold = -(global_min + VALLEY_MARGIN)

    peak_indices = find_peaks(
        negated,
        threshold=valley_threshold,
        min_distance=MIN_SWING_INTERVAL,
    )

    events = []
    for idx in peak_indices:
        angle_at_bottom = best_series[idx]
        com_x = frame_metrics[idx].com_x if idx < len(frame_metrics) else None
        events.append(SwingEvent(
            frame_index=idx,
            wrist_speed=angle_at_bottom if angle_at_bottom is not None else 0.0,
            com_x=com_x,
        ))
    return events


# ---------------------------------------------------------------------------
# ActivityConfig registration
# ---------------------------------------------------------------------------

GYM = register(ActivityConfig(
    id="gym",
    display_name="Gym Workout",
    event_singular="rep",
    event_plural="reps",
    window_before=10,
    window_after=20,
    coaching_labels={
        "swing_mechanics":        "Form & Technique",
        "footwork_movement":      "Range of Motion",
        "stance_posture":         "Posture & Alignment",
        "shot_selection_tactics": "Progression",
    },
    event_metric_label="Rep depths (joint angle at bottom, °)",
    system_prompt=SYSTEM_PROMPT,
    per_event_system_prompt=PER_EVENT_SYSTEM_PROMPT,
    detect_events=detect_gym_reps,
))
