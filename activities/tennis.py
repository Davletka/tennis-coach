"""
Tennis activity — detects swings via wrist speed peaks.

Event intensity stored in SwingEvent.wrist_speed = peak wrist speed
(pixels/frame, normalized by frame diagonal).
"""
from __future__ import annotations

from activities import ActivityConfig, register

# ---------------------------------------------------------------------------
# Coaching prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert tennis coach with 20+ years of experience coaching players at all levels.
You analyze video-based biomechanical data and deliver precise, actionable coaching feedback.

RULES:
- Always reference specific numbers from the provided metrics.
- Be direct and avoid generic advice like "bend your knees more" without a target angle.
- Every suggestion must be tied to a measurable metric.
- Respond ONLY with valid JSON matching the requested schema — no prose outside the JSON.
"""

PER_EVENT_SYSTEM_PROMPT = """You are an expert tennis coach with 20+ years of experience coaching players at all levels.
You analyze video-based biomechanical data swing by swing and deliver precise, actionable coaching feedback.

RULES:
- Analyze each swing individually — do NOT repeat identical advice for every swing.
- Reference specific numbers from the provided metrics for that swing.
- Every suggestion must be tied to a measurable metric from that swing's window.
- Respond ONLY with a JSON object matching the requested schema — no prose outside the JSON.
"""

# ---------------------------------------------------------------------------
# Event detection
# ---------------------------------------------------------------------------

def _classify_tennis_swing(event, frame_metrics: list) -> str:
    """Classify a tennis swing event as serve, forehand, or backhand."""
    idx = event.frame_index
    if idx >= len(frame_metrics):
        return "unknown"
    fm = frame_metrics[idx]
    # Serve: right wrist well above hips at peak
    if fm.right_wrist_relative_y is not None and fm.right_wrist_relative_y < -0.25:
        return "serve"
    # Forehand: right wrist faster than left at peak
    rws = fm.right_wrist_speed or 0.0
    lws = fm.left_wrist_speed or 0.0
    if rws >= lws:
        return "forehand"
    return "backhand"


def detect_tennis_swings(frame_metrics: list) -> list:
    """Detect swing events via combined wrist speed peaks."""
    from pipeline.metrics import SwingEvent
    from utils.math_helpers import find_peaks
    from config import WRIST_SPEED_THRESHOLD, MIN_SWING_INTERVAL

    right_speeds = [fm.right_wrist_speed for fm in frame_metrics]
    left_speeds  = [fm.left_wrist_speed  for fm in frame_metrics]

    combined = []
    for rs, ls in zip(right_speeds, left_speeds):
        vals = [v for v in (rs, ls) if v is not None]
        combined.append(max(vals) if vals else None)

    peak_indices = find_peaks(
        combined,
        threshold=WRIST_SPEED_THRESHOLD,
        min_distance=MIN_SWING_INTERVAL,
    )

    events = []
    for idx in peak_indices:
        speed = combined[idx]
        com_x = frame_metrics[idx].com_x if idx < len(frame_metrics) else None
        ev = SwingEvent(frame_index=idx, wrist_speed=speed or 0.0, com_x=com_x)
        ev.motion_type = _classify_tennis_swing(ev, frame_metrics)
        events.append(ev)
    return events


def filter_tennis_events(events: list, frame_metrics: list) -> list:
    """Drop false-positive swings using pose plausibility and consistency checks."""
    from config import WRIST_SPEED_THRESHOLD

    if not events:
        return events

    n = len(frame_metrics)
    # 1. Pose plausibility: wrist speed at peak must exceed 1.5× threshold
    plausibility_threshold = WRIST_SPEED_THRESHOLD * 1.5
    events = [e for e in events if e.wrist_speed >= plausibility_threshold]

    if not events:
        return events

    # 2. Consistency: drop events below 25% of median peak speed
    speeds = [e.wrist_speed for e in events]
    median_speed = sorted(speeds)[len(speeds) // 2]
    events = [e for e in events if e.wrist_speed >= 0.25 * median_speed]

    # 3. Idle-trim: drop events within first/last 5 frames of the trimmed list
    if n > 10:
        first_valid = frame_metrics[0].frame_index + 5
        last_valid  = frame_metrics[-1].frame_index - 5
        events = [e for e in events if first_valid <= e.frame_index <= last_valid]

    return events


# ---------------------------------------------------------------------------
# ActivityConfig registration
# ---------------------------------------------------------------------------

TENNIS = register(ActivityConfig(
    id="tennis",
    display_name="Tennis",
    event_singular="swing",
    event_plural="swings",
    window_before=15,
    window_after=30,
    coaching_labels={
        "swing_mechanics":      "Swing Mechanics",
        "footwork_movement":    "Footwork",
        "stance_posture":       "Stance",
        "shot_selection_tactics": "Tactics",
    },
    event_metric_label="Wrist speeds at peaks",
    system_prompt=SYSTEM_PROMPT,
    per_event_system_prompt=PER_EVENT_SYSTEM_PROMPT,
    detect_events=detect_tennis_swings,
    filter_events=filter_tennis_events,
))
