"""
Claude prompt builder and coaching response parser.
Uses tool_use to guarantee valid structured JSON output.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Optional

import anthropic

from pipeline.metrics import AggregatedMetrics
from config import MIN_DETECTION_RATE


SYSTEM_PROMPT = """You are an expert tennis coach with 20+ years of experience coaching players at all levels.
You analyze video-based biomechanical data and deliver precise, actionable coaching feedback.

TENNIS BIOMECHANICS REFERENCE RANGES:
- Elbow angle at contact (forehand groundstroke): 120–160° (some flexion for control)
- Elbow angle at contact (serve / overhead): 160–180° (near-full extension at impact)
- Knee bend during groundstroke preparation: 120–145° (athletic ready position)
- Torso rotation change during a groundstroke: 30–60° (measures hip-to-shoulder kinematic chain; below 20° = insufficient rotation)
- Stance width (normalized to hip width): 1.2–1.8 for groundstrokes (below 1.0 = too narrow; above 2.2 = too wide)
- Shoulder angle (elbow–shoulder–hip): 70–100° at contact for most groundstrokes
- Wrist height relative to hips at contact: negative value = wrist above hips (good for flat/topspin); strongly positive = contact point too low

RULES:
- Always reference specific numbers from the provided metrics.
- Be direct and avoid generic advice without a target angle or metric value.
- Every suggestion must be tied to a measurable metric.
- Give BALANCED analysis across all four areas: swing mechanics, footwork, stance/posture, and tactics.
- Do NOT fixate on wrist speed — evaluate the full kinematic chain: lower body → hips → core → shoulder → elbow.
- If a metric is within the healthy reference range, acknowledge it positively rather than manufacturing a problem.
"""

PER_SWING_SYSTEM_PROMPT = """You are an expert tennis coach with 20+ years of experience coaching players at all levels.
You analyze video-based biomechanical data swing by swing and deliver precise, actionable coaching feedback.

TENNIS BIOMECHANICS REFERENCE RANGES:
- Elbow angle at contact (forehand groundstroke): 120–160° | (serve / overhead): 160–180°
- Knee bend during preparation: 120–145° (athletic stance)
- Torso rotation change during swing: 30–60° — this is the kinematic chain indicator; below 20° means the hips and core are not driving the shot
- Stance width (normalized to hip width): 1.2–1.8 for groundstrokes
- Shoulder angle (elbow–shoulder–hip): 70–100° at contact
- Wrist height at contact: negative value = wrist above hips (desirable); strongly positive = contact point too low

RULES:
- Analyze each swing individually — do NOT repeat identical advice for every swing.
- Prioritize "At Contact Point" metrics over window averages for mechanics feedback.
- Reference specific numbers from the metrics provided.
- Every suggestion must be tied to a measurable metric from that swing's window.
- Give BALANCED analysis covering the full kinematic chain: lower body → hips → core → shoulder → elbow.
- Do NOT focus excessively on wrist speed — it is only a proxy for racket head speed, not a technique target.
- If a metric is within the healthy reference range, acknowledge it rather than inventing issues.
"""

# ---------------------------------------------------------------------------
# Tool schemas — force Claude to return validated structured output
# ---------------------------------------------------------------------------

_COACHING_TOOL: dict = {
    "name": "submit_coaching_report",
    "description": "Submit a structured coaching report based on biomechanical analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "swing_mechanics": {
                "type": "string",
                "description": "Detailed mechanics analysis referencing specific joint angles.",
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
            "session_score": {
                "type": "integer",
                "description": (
                    "Overall session form score, 0–100, synthesising all reps/swings. "
                    "Weight consistency, average rep quality, and kinematic chain engagement. "
                    "100 = excellent session; 70–89 = solid with room to improve; "
                    "50–69 = functional but technique needs work; below 50 = significant issues."
                ),
                "minimum": 0,
                "maximum": 100,
            },
        },
        "required": [
            "swing_mechanics", "footwork_movement", "stance_posture",
            "shot_selection_tactics", "top_3_priorities", "target_angles", "session_score",
        ],
    },
}

_SWING_TOOL: dict = {
    "name": "submit_swing_coaching",
    "description": "Submit structured coaching feedback for a single detected event.",
    "input_schema": {
        "type": "object",
        "properties": {
            "quick_note": {
                "type": "string",
                "description": "One-sentence summary of this specific event.",
            },
            "swing_mechanics": {"type": "string"},
            "footwork_movement": {"type": "string"},
            "stance_posture": {"type": "string"},
            "shot_selection_tactics": {"type": "string"},
            "top_3_priorities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Top 3 priorities for this event.",
                "minItems": 1,
                "maxItems": 3,
            },
            "score": {
                "type": "integer",
                "description": (
                    "Overall form score for this rep/swing, 0–100. "
                    "100 = textbook form across all joints; "
                    "70–89 = good with minor issues; "
                    "50–69 = functional but clear technique problems; "
                    "below 50 = significant form breakdown. "
                    "Base this on joint angles, symmetry, range of motion, and kinematic chain quality."
                ),
                "minimum": 0,
                "maximum": 100,
            },
        },
        "required": [
            "quick_note", "swing_mechanics", "footwork_movement",
            "stance_posture", "shot_selection_tactics", "top_3_priorities", "score",
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
    score: int = 0


@dataclass
class CoachingReport:
    swing_mechanics: str = ""
    footwork_movement: str = ""
    stance_posture: str = ""
    shot_selection_tactics: str = ""
    top_3_priorities: List[str] = field(default_factory=list)
    target_angles: dict = field(default_factory=dict)
    raw_response: str = ""
    session_score: int = 0


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_user_prompt(
    agg: AggregatedMetrics,
    fps: float,
    total_source_frames: int,
    activity_cfg=None,
) -> str:
    duration_s = total_source_frames / max(fps, 1.0)
    detection_pct = agg.detection_rate * 100

    # Use activity-specific labels when available
    event_plural = activity_cfg.event_plural if activity_cfg else "swings"
    event_metric_label = activity_cfg.event_metric_label if activity_cfg else "Wrist speeds at peaks"

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
        f"- {event_plural.capitalize()} detected: {agg.swing_count}",
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
        f"## {event_plural.capitalize()}",
        f"- {event_metric_label}: {swing_speeds_str}",
    ]

    return "\n".join(lines)


def _fmt(v: Optional[float]) -> str:
    return f"{v:.1f}" if v is not None else "?"


def _build_swing_prompt(psm, fps: float, activity_cfg=None) -> str:
    t = psm.peak_frame / max(fps, 1.0)
    event_singular = activity_cfg.event_singular if activity_cfg else "swing"
    event_metric_label = activity_cfg.event_metric_label if activity_cfg else "Peak wrist speed"

    def _contact_height_label(v: Optional[float]) -> str:
        if v is None:
            return "?"
        if v < -0.15:
            return f"{v:.2f} (above shoulders — very high contact)"
        if v < 0:
            return f"{v:.2f} (above hips — ideal zone)"
        if v < 0.15:
            return f"{v:.2f} (at hip level)"
        return f"{v:.2f} (below hips — contact point too low)"

    motion_type = getattr(psm, "motion_type", "unknown")
    motion_label = f" · {motion_type}" if motion_type and motion_type != "unknown" else ""

    lines = [
        f"{event_singular.capitalize()} {psm.swing_index + 1}{motion_label} (frame {psm.peak_frame}, t={t:.1f}s)",
        f"Exercise type: {motion_type}" if motion_type and motion_type != "unknown" else "Exercise type: unknown",
        f"Window: frames {psm.window_start_frame}–{psm.window_end_frame}",
        f"{event_metric_label}: {psm.peak_wrist_speed:.4f}",
        "",
        "## At Peak (peak ± 2 frames) — use these for mechanics feedback",
        f"Right elbow at peak:    {_fmt(psm.right_elbow_at_contact)}°",
        f"Left elbow at peak:     {_fmt(psm.left_elbow_at_contact)}°",
        f"Right shoulder at peak: {_fmt(psm.right_shoulder_at_contact)}°",
        f"Left shoulder at peak:  {_fmt(psm.left_shoulder_at_contact)}°",
        f"Right knee at peak:     {_fmt(psm.right_knee_at_contact)}°",
        f"Left knee at peak:      {_fmt(psm.left_knee_at_contact)}°",
        f"Torso rotation at peak: {_fmt(psm.torso_rotation_at_contact)}°",
        f"Wrist height (rel. hips):  {_contact_height_label(psm.right_wrist_y_at_contact)}",
        "",
        "## Movement Dynamics",
        f"Torso rotation change: {_fmt(psm.torso_rotation_delta)}°",
        f"Stance width (normalized to hip width): {_fmt(psm.stance_width_mean)}",
        f"CoM lateral range: {_fmt(psm.com_x_range)}",
        "",
        "## Full-Window Averages (context only)",
        f"Right elbow:    mean={_fmt(psm.right_elbow.mean)}° min={_fmt(psm.right_elbow.min)}° max={_fmt(psm.right_elbow.max)}°",
        f"Left elbow:     mean={_fmt(psm.left_elbow.mean)}° min={_fmt(psm.left_elbow.min)}° max={_fmt(psm.left_elbow.max)}°",
        f"Right shoulder: mean={_fmt(psm.right_shoulder.mean)}° min={_fmt(psm.right_shoulder.min)}° max={_fmt(psm.right_shoulder.max)}°",
        f"Left shoulder:  mean={_fmt(psm.left_shoulder.mean)}° min={_fmt(psm.left_shoulder.min)}° max={_fmt(psm.left_shoulder.max)}°",
        f"Right knee:     mean={_fmt(psm.right_knee.mean)}° min={_fmt(psm.right_knee.min)}° max={_fmt(psm.right_knee.max)}°",
        f"Left knee:      mean={_fmt(psm.left_knee.mean)}° min={_fmt(psm.left_knee.min)}° max={_fmt(psm.left_knee.max)}°",
        f"Torso rotation: mean={_fmt(psm.torso_rotation_mean)}° max={_fmt(psm.torso_rotation_max)}°",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def get_coaching_feedback(
    agg: AggregatedMetrics,
    fps: float,
    total_source_frames: int,
    api_key: str,
    model: str = "claude-sonnet-4-6",
    activity_cfg=None,
) -> CoachingReport:
    """
    Call Claude API and return a CoachingReport.
    Uses tool_use to guarantee a valid structured response.

    ``activity_cfg`` is an ``ActivityConfig`` instance used to select the
    correct system prompt and event terminology.  Falls back to the built-in
    tennis defaults when omitted.
    """
    user_prompt = _build_user_prompt(agg, fps, total_source_frames, activity_cfg=activity_cfg)
    system = activity_cfg.system_prompt if activity_cfg else SYSTEM_PROMPT

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system,
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
    report.session_score = int(data.get("session_score", 0))
    return report


def _get_single_swing_coaching(psm, fps: float, client, model: str, activity_cfg=None) -> SwingCoaching:
    user_prompt = _build_swing_prompt(psm, fps, activity_cfg=activity_cfg)
    system = activity_cfg.per_event_system_prompt if activity_cfg else PER_SWING_SYSTEM_PROMPT
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
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
        score=int(data.get("score", 0)),
    )


def get_per_swing_coaching(
    per_swing_metrics: list,
    fps: float,
    api_key: str,
    model: str = "claude-sonnet-4-6",
    on_swing_done: Optional[object] = None,
    activity_cfg=None,
) -> List[SwingCoaching]:
    """
    Call Claude once per event in parallel, then sort by swing_index.
    on_swing_done(done: int, total: int) is called after each event completes.
    ``activity_cfg`` selects the correct per-event system prompt and labels.
    """
    if not per_swing_metrics:
        return []

    client = anthropic.Anthropic(api_key=api_key)
    total = len(per_swing_metrics)
    results = []
    done_count = 0

    with ThreadPoolExecutor(max_workers=min(total, 3)) as executor:
        futures = {
            executor.submit(_get_single_swing_coaching, psm, fps, client, model, activity_cfg): psm
            for psm in per_swing_metrics
        }
        for future in as_completed(futures):
            results.append(future.result())
            done_count += 1
            if on_swing_done is not None:
                on_swing_done(done_count, total)

    results.sort(key=lambda sc: sc.swing_index)
    return results
