"""
Claude prompt builder and coaching response parser.
"""
from __future__ import annotations

import json
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
- Respond ONLY with valid JSON matching the requested schema — no prose outside the JSON.
"""


@dataclass
class CoachingReport:
    swing_mechanics: str = ""
    footwork_movement: str = ""
    stance_posture: str = ""
    shot_selection_tactics: str = ""
    top_3_priorities: List[str] = field(default_factory=list)
    raw_response: str = ""


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
        "",
        "## Required Output Format",
        "Respond with ONLY this JSON structure:",
        "{",
        '  "swing_mechanics": "...",',
        '  "footwork_movement": "...",',
        '  "stance_posture": "...",',
        '  "shot_selection_tactics": "...",',
        '  "top_3_priorities": ["...", "...", "..."]',
        "}",
    ]

    return "\n".join(lines)


def get_coaching_feedback(
    agg: AggregatedMetrics,
    fps: float,
    total_source_frames: int,
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> CoachingReport:
    """
    Call Claude API and return a CoachingReport.
    Handles API errors and JSON parse failures gracefully.
    """
    user_prompt = _build_user_prompt(agg, fps, total_source_frames)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = message.content[0].text.strip()
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

    # Parse JSON
    return _parse_response(raw_text)


def _parse_response(raw_text: str) -> CoachingReport:
    """Parse Claude's JSON response into a CoachingReport."""
    report = CoachingReport(raw_response=raw_text)

    # Extract JSON block if wrapped in markdown fences
    text = raw_text
    if "```" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]

    try:
        data = json.loads(text)
        report.swing_mechanics = data.get("swing_mechanics", "")
        report.footwork_movement = data.get("footwork_movement", "")
        report.stance_posture = data.get("stance_posture", "")
        report.shot_selection_tactics = data.get("shot_selection_tactics", "")
        report.top_3_priorities = data.get("top_3_priorities", [])
    except (json.JSONDecodeError, ValueError):
        # Fallback: dump raw text into swing_mechanics
        report.swing_mechanics = raw_text
        report.top_3_priorities = []

    return report
