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

PER_SWING_SYSTEM_PROMPT = """You are an expert tennis coach with 20+ years of experience coaching players at all levels.
You analyze video-based biomechanical data swing by swing and deliver precise, actionable coaching feedback.

RULES:
- Analyze each swing individually — do NOT repeat identical advice for every swing.
- Reference specific numbers from the provided metrics for that swing.
- Every suggestion must be tied to a measurable metric from that swing's window.
- Respond ONLY with a JSON array matching the requested schema — no prose outside the JSON.
"""


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
        '  "top_3_priorities": ["...", "...", "..."],',
        '  "target_angles": {',
        '    "right_elbow": <target degrees as number, or null if not applicable>,',
        '    "left_elbow": <target degrees, or null>,',
        '    "right_shoulder": <target degrees, or null>,',
        '    "left_shoulder": <target degrees, or null>,',
        '    "right_knee": <target degrees, or null>,',
        '    "left_knee": <target degrees, or null>',
        '  }',
        "}",
        "",
        "Set target_angles to the ideal joint angles you recommend for this player's shot type. Use null for joints where current data is insufficient.",
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


def get_per_swing_coaching(
    per_swing_metrics: list,
    fps: float,
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> List[SwingCoaching]:
    """
    Batch-call Claude for per-swing coaching analysis.
    All swings sent in a single API call; returns one SwingCoaching per swing.
    """
    if not per_swing_metrics:
        return []

    def _fmt(v: Optional[float]) -> str:
        return f"{v:.1f}" if v is not None else "?"

    swing_blocks = []
    for psm in per_swing_metrics:
        t = psm.peak_frame / max(fps, 1.0)
        block = "\n".join([
            f"### Swing {psm.swing_index + 1} (frame {psm.peak_frame}, t={t:.1f}s)",
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
        swing_blocks.append(block)

    user_prompt = "\n\n".join([
        "Analyze each swing individually. Do NOT repeat advice that applies identically to all swings.",
        *swing_blocks,
        """Respond ONLY with a JSON array, one object per swing, in this exact schema:
[
  {
    "swing_index": 0,
    "quick_note": "one-sentence summary of this swing",
    "swing_mechanics": "...",
    "footwork_movement": "...",
    "stance_posture": "...",
    "shot_selection_tactics": "...",
    "top_3_priorities": ["...", "...", "..."]
  }
]""",
    ])

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=4096,
            system=PER_SWING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return _parse_per_swing_response(msg.content[0].text.strip(), len(per_swing_metrics))
    except (
        anthropic.AuthenticationError,
        anthropic.RateLimitError,
        anthropic.APIConnectionError,
        anthropic.APIStatusError,
    ) as exc:
        note = f"[Coach unavailable: {exc}]"
        return [SwingCoaching(swing_index=i, quick_note=note) for i in range(len(per_swing_metrics))]


def _parse_per_swing_response(raw: str, swing_count: int) -> List[SwingCoaching]:
    text = raw
    if "```" in text:
        s = text.find("[")
        e = text.rfind("]") + 1
        if s != -1 and e > s:
            text = text[s:e]
    try:
        data = json.loads(text)
        assert isinstance(data, list)
        return [
            SwingCoaching(
                swing_index=item.get("swing_index", i),
                quick_note=item.get("quick_note", ""),
                swing_mechanics=item.get("swing_mechanics", ""),
                footwork_movement=item.get("footwork_movement", ""),
                stance_posture=item.get("stance_posture", ""),
                shot_selection_tactics=item.get("shot_selection_tactics", ""),
                top_3_priorities=item.get("top_3_priorities", []),
            )
            for i, item in enumerate(data)
        ]
    except (json.JSONDecodeError, AssertionError):
        return [
            SwingCoaching(swing_index=i, quick_note="[Parse error — raw response unavailable]")
            for i in range(swing_count)
        ]


def _parse_response(raw_text: str) -> CoachingReport:
    """Parse Claude's JSON response into a CoachingReport."""
    report = CoachingReport(raw_response=raw_text)

    # Always extract the outermost {...} block (handles both plain JSON and
    # markdown-fenced responses like ```json\n{...}\n```).
    start = raw_text.find("{")
    end = raw_text.rfind("}") + 1
    text = raw_text[start:end] if start != -1 and end > start else raw_text

    try:
        data = json.loads(text)
        report.swing_mechanics = data.get("swing_mechanics", "")
        report.footwork_movement = data.get("footwork_movement", "")
        report.stance_posture = data.get("stance_posture", "")
        report.shot_selection_tactics = data.get("shot_selection_tactics", "")
        report.top_3_priorities = data.get("top_3_priorities", [])
        report.target_angles = data.get("target_angles", {}) or {}
    except (json.JSONDecodeError, ValueError):
        report.swing_mechanics = "⚠️ Coaching analysis could not be parsed. Please re-analyze the video."
        report.top_3_priorities = []

    return report
