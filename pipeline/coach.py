"""
Claude prompt builder and coaching response parser.
Uses tool_use to guarantee valid structured JSON output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import anthropic

from pipeline.metrics import AggregatedMetrics
from config import MIN_DETECTION_RATE


SYSTEM_PROMPT = """You are an expert tennis coach with 20+ years of experience coaching players at all levels.
You analyze video-based biomechanical data and deliver precise, actionable coaching feedback.

RULES:
- Always reference specific numbers from the provided metrics.
- Be direct and avoid generic advice like "bend your knees more" without a target angle.
- Every suggestion must be tied to a measurable metric.
"""

PER_SWING_SYSTEM_PROMPT = """You are an expert tennis coach with 20+ years of experience coaching players at all levels.
You analyze video-based biomechanical data swing by swing and deliver precise, actionable coaching feedback.

RULES:
- Analyze each swing individually — do NOT repeat identical advice for every swing.
- Reference specific numbers from the provided metrics for that swing.
- Every suggestion must be tied to a measurable metric from that swing's window.
"""

# ---------------------------------------------------------------------------
# Tool schemas — force Claude to return validated structured output
# ---------------------------------------------------------------------------

_COACHING_TOOL: dict = {
    "name": "submit_coaching_report",
    "description": "Submit a structured tennis coaching report based on biomechanical analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "swing_mechanics": {
                "type": "string",
                "description": "Detailed swing mechanics analysis referencing specific joint angles.",
            },
            "footwork_movement": {
                "type": "string",
                "description": "Footwork and movement pattern analysis.",
            },
            "stance_posture": {
                "type": "string",
                "description": "Stance width, body posture, and balance analysis.",
            },
            "shot_selection_tactics": {
                "type": "string",
                "description": "Shot selection and tactical observations.",
            },
            "top_3_priorities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exactly 3 priority improvements for the player.",
                "minItems": 1,
                "maxItems": 3,
            },
            "target_angles": {
                "type": "object",
                "description": "Recommended target joint angles in degrees (null if insufficient data).",
                "properties": {
                    "right_elbow":    {"anyOf": [{"type": "number"}, {"type": "null"}]},
                    "left_elbow":     {"anyOf": [{"type": "number"}, {"type": "null"}]},
                    "right_shoulder": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                    "left_shoulder":  {"anyOf": [{"type": "number"}, {"type": "null"}]},
                    "right_knee":     {"anyOf": [{"type": "number"}, {"type": "null"}]},
                    "left_knee":      {"anyOf": [{"type": "number"}, {"type": "null"}]},
                },
                "required": [
                    "right_elbow", "left_elbow",
                    "right_shoulder", "left_shoulder",
                    "right_knee", "left_knee",
                ],
            },
        },
        "required": [
            "swing_mechanics", "footwork_movement", "stance_posture",
            "shot_selection_tactics", "top_3_priorities", "target_angles",
        ],
    },
}

_SWING_TOOL: dict = {
    "name": "submit_swing_coaching",
    "description": "Submit structured coaching feedback for a single tennis swing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "quick_note": {
                "type": "string",
                "description": "One-sentence summary of this specific swing.",
            },
            "swing_mechanics": {"type": "string"},
            "footwork_movement": {"type": "string"},
            "stance_posture": {"type": "string"},
            "shot_selection_tactics": {"type": "string"},
            "top_3_priorities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Top 3 priorities for this swing.",
                "minItems": 1,
                "maxItems": 3,
            },
        },
        "required": [
            "quick_note", "swing_mechanics", "footwork_movement",
            "stance_posture", "shot_selection_tactics", "top_3_priorities",
        ],
    },
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SwingCoaching:
    swing_index: int
    quick_note: str = ""
    swing_mechanics: str = ""
    footwork_movement: str = ""
    stance_posture: str = ""
    shot_selection_tactics: str = ""
    top_3_priorities: List[str] = field(default_factory=list)


@dataclass
class CoachingReport:
    swing_mechanics: str = ""
    footwork_movement: str = ""
    stance_posture: str = ""
    shot_selection_tactics: str = ""
    top_3_priorities: List[str] = field(default_factory=list)
    target_angles: dict = field(default_factory=dict)
    raw_response: str = ""


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_user_prompt(
    agg: AggregatedMetrics,
    fps: float,
    total_source_frames: int,
) -> str:
    duration_s = total_source_frames / max(fps, 1.0)
    detection_pct = agg.detection_rate * 100

    low_detection_warning = ""
    if agg.detection_rate < MIN_DETECTION_RATE:
        low_detection_warning = (
            "\n⚠️  WARNING: Pose was detected in only "
            f"{detection_pct:.0f}% of frames — confidence is reduced.\n"
        )

    swing_speeds = [f"{e.wrist_speed:.3f}" for e in agg.swing_events]
    swing_speeds_str = ", ".join(swing_speeds) if swing_speeds else "none detected"

    def fmt(val: Optional[float], unit: str = "°") -> str:
        return f"{val:.1f}{unit}" if val is not None else "N/A"

    lines = [
        "## Video Context",
        f"- Duration: {duration_s:.1f}s",
        f"- Frames analyzed: {agg.frames_analyzed}",
        f"- Pose detection rate: {detection_pct:.0f}%",
        f"- Swing events detected: {agg.swing_count}",
        low_detection_warning,
        "",
        "## Joint Angle Statistics (mean / min / max / std)",
        f"- Right elbow:    {fmt(agg.right_elbow.mean)} / {fmt(agg.right_elbow.min)} / {fmt(agg.right_elbow.max)} / {fmt(agg.right_elbow.std)}",
        f"- Left elbow:     {fmt(agg.left_elbow.mean)} / {fmt(agg.left_elbow.min)} / {fmt(agg.left_elbow.max)} / {fmt(agg.left_elbow.std)}",
        f"- Right shoulder: {fmt(agg.right_shoulder.mean)} / {fmt(agg.right_shoulder.min)} / {fmt(agg.right_shoulder.max)} / {fmt(agg.right_shoulder.std)}",
        f"- Left shoulder:  {fmt(agg.left_shoulder.mean)} / {fmt(agg.left_shoulder.min)} / {fmt(agg.left_shoulder.max)} / {fmt(agg.left_shoulder.std)}",
        f"- Right knee:     {fmt(agg.right_knee.mean)} / {fmt(agg.right_knee.min)} / {fmt(agg.right_knee.max)} / {fmt(agg.right_knee.std)}",
        f"- Left knee:      {fmt(agg.left_knee.mean)} / {fmt(agg.left_knee.min)} / {fmt(agg.left_knee.max)} / {fmt(agg.left_knee.std)}",
        "",
        "## Body Mechanics",
        f"- Torso rotation (mean/max): {fmt(agg.torso_rotation_mean)} / {fmt(agg.torso_rotation_max)}",
        f"- Stance width (normalized to hip width, mean): {fmt(agg.stance_width_mean, '')}",
        f"- CoM lateral range: {fmt(agg.com_x_range, ' (normalized 0-1)')}",
        "",
        "## Swing Events",
        f"- Wrist speeds at peaks: {swing_speeds_str}",
    ]

    return "\n".join(lines)


def _fmt(v: Optional[float]) -> str:
    return f"{v:.1f}" if v is not None else "?"


def _build_swing_prompt(psm, fps: float) -> str:
    t = psm.peak_frame / max(fps, 1.0)
    return "\n".join([
        f"Swing {psm.swing_index + 1} (frame {psm.peak_frame}, t={t:.1f}s)",
        f"Window: frames {psm.window_start_frame}–{psm.window_end_frame}",
        f"Peak wrist speed: {psm.peak_wrist_speed:.4f}",
        f"Right elbow:    mean={_fmt(psm.right_elbow.mean)}° min={_fmt(psm.right_elbow.min)}° max={_fmt(psm.right_elbow.max)}°",
        f"Left elbow:     mean={_fmt(psm.left_elbow.mean)}° min={_fmt(psm.left_elbow.min)}° max={_fmt(psm.left_elbow.max)}°",
        f"Right shoulder: mean={_fmt(psm.right_shoulder.mean)}° min={_fmt(psm.right_shoulder.min)}° max={_fmt(psm.right_shoulder.max)}°",
        f"Left shoulder:  mean={_fmt(psm.left_shoulder.mean)}° min={_fmt(psm.left_shoulder.min)}° max={_fmt(psm.left_shoulder.max)}°",
        f"Right knee:     mean={_fmt(psm.right_knee.mean)}° min={_fmt(psm.right_knee.min)}° max={_fmt(psm.right_knee.max)}°",
        f"Left knee:      mean={_fmt(psm.left_knee.mean)}° min={_fmt(psm.left_knee.min)}° max={_fmt(psm.left_knee.max)}°",
        f"Torso rotation: mean={_fmt(psm.torso_rotation_mean)}° max={_fmt(psm.torso_rotation_max)}°",
        f"Stance width (normalized): {_fmt(psm.stance_width_mean)}",
        f"CoM X range: {_fmt(psm.com_x_range)}",
    ])


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def get_coaching_feedback(
    agg: AggregatedMetrics,
    fps: float,
    total_source_frames: int,
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> CoachingReport:
    """
    Call Claude API and return a CoachingReport.
    Uses tool_use to guarantee a valid structured response.
    """
    user_prompt = _build_user_prompt(agg, fps, total_source_frames)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=[_COACHING_TOOL],
            tool_choice={"type": "tool", "name": "submit_coaching_report"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.AuthenticationError:
        report = CoachingReport()
        report.swing_mechanics = "❌ Authentication failed — check your Anthropic API key."
        return report
    except anthropic.RateLimitError:
        report = CoachingReport()
        report.swing_mechanics = "❌ Rate limit exceeded — please wait and retry."
        return report
    except anthropic.APIConnectionError:
        report = CoachingReport()
        report.swing_mechanics = "❌ Network error — check your internet connection."
        return report
    except anthropic.APIStatusError as exc:
        report = CoachingReport()
        report.swing_mechanics = f"❌ Claude API error ({exc.status_code}): {exc.message}"
        return report

    # Extract the tool_use input block — always present when tool_choice is forced
    data = None
    for block in message.content:
        if block.type == "tool_use":
            data = block.input
            break

    if data is None:
        report = CoachingReport()
        report.swing_mechanics = "⚠️ Coaching analysis could not be parsed. Please re-analyze the video."
        return report

    report = CoachingReport()
    report.swing_mechanics = data.get("swing_mechanics", "")
    report.footwork_movement = data.get("footwork_movement", "")
    report.stance_posture = data.get("stance_posture", "")
    report.shot_selection_tactics = data.get("shot_selection_tactics", "")
    report.top_3_priorities = data.get("top_3_priorities", [])
    report.target_angles = data.get("target_angles", {}) or {}
    return report


def _get_single_swing_coaching(psm, fps: float, client, model: str) -> SwingCoaching:
    user_prompt = _build_swing_prompt(psm, fps)
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=1024,
            system=PER_SWING_SYSTEM_PROMPT,
            tools=[_SWING_TOOL],
            tool_choice={"type": "tool", "name": "submit_swing_coaching"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except (
        anthropic.AuthenticationError,
        anthropic.RateLimitError,
        anthropic.APIConnectionError,
        anthropic.APIStatusError,
    ) as exc:
        return SwingCoaching(swing_index=psm.swing_index, quick_note=f"[Coach unavailable: {exc}]")

    data = None
    for block in msg.content:
        if block.type == "tool_use":
            data = block.input
            break

    if data is None:
        return SwingCoaching(swing_index=psm.swing_index, quick_note="[Parse error]")

    return SwingCoaching(
        swing_index=psm.swing_index,
        quick_note=data.get("quick_note", ""),
        swing_mechanics=data.get("swing_mechanics", ""),
        footwork_movement=data.get("footwork_movement", ""),
        stance_posture=data.get("stance_posture", ""),
        shot_selection_tactics=data.get("shot_selection_tactics", ""),
        top_3_priorities=data.get("top_3_priorities", []),
    )


def get_per_swing_coaching(
    per_swing_metrics: list,
    fps: float,
    api_key: str,
    model: str = "claude-sonnet-4-6",
    on_swing_done: Optional[object] = None,
) -> List[SwingCoaching]:
    """
    Call Claude once per swing so progress can be reported after each one.
    on_swing_done(done: int, total: int) is called after each swing completes.
    """
    if not per_swing_metrics:
        return []

    client = anthropic.Anthropic(api_key=api_key)
    results = []
    for psm in per_swing_metrics:
        results.append(_get_single_swing_coaching(psm, fps, client, model))
        if on_swing_done is not None:
            on_swing_done(len(results), len(per_swing_metrics))
    return results
