"""
Delta coaching: compare two analysis sessions and produce progress feedback.

Mirrors the patterns of pipeline/coach.py — dataclass report, system prompt
enforcing JSON-only, graceful fallback on parse failure.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import anthropic


DELTA_SYSTEM_PROMPT = """Ты опытный тренер по силовому тренингу и функциональной подготовке с 20+ годами опыта.
Ты анализируешь видео техники упражнения, как будто стоишь рядом в зале и смотришь на спортсмена.

ТВОЙ СТИЛЬ ОБЩЕНИЯ:
- Отзывчивый и мотивирующий — указываешь ошибки, но вдохновляешь на исправление
- Конкретный, практичный — "опусти бёдра ниже", "не закругляй спину", "держи локти ближе к телу"
- Понятный язык — простые слова вместо "биомеханика", "кинематическая цепь", "амплитуда движения"
- БЕЗ ЧИСЕЛ: не упоминай градусы, только описывай положение

СТРУКТУРА ОТВЕТА:
- Form & Technique: какие части упражнения сделаны хорошо, что нужно исправить (2-3 предложения)
- Range of Motion: глубина приседа, амплитуда движения, "насколько глубоко ты опускаешься" (2 предложения)
- Posture & Alignment: положение спины, головы, напряжение корпуса (2 предложения)
- Progression: как усложнить, добавить вес или объём (1-2 предложения)
- Top 3 priorities: 3 конкретных совета для улучшения техники
- Target angles: рекомендуемые углы в суставах на основе анализа

ВАЖНО: Будь как реальный тренер — поддерживай, мотивируй, давай чёткие команды на исправление.
"""

# Metrics where a LARGER value is better (e.g. fuller elbow extension)
_HIGHER_IS_BETTER = {
    "right_elbow_mean",
    "left_elbow_mean",
    "right_shoulder_mean",
    "left_shoulder_mean",
    "right_knee_mean",
    "left_knee_mean",
    "torso_rotation_mean",
    "swing_count",
}

# Metrics where a SMALLER value is better — none currently, placeholder for future
_LOWER_IS_BETTER: set = set()

# Thresholds below which a change is considered noise
_ANGLE_NOISE = 1.0       # degrees
_NORM_NOISE = 0.05       # normalized (0-1)

_NORM_METRICS = {"stance_width_mean", "com_x_range"}


@dataclass
class DeltaCoachingReport:
    overall_progress_summary: str = ""
    improvements: List[str] = field(default_factory=list)
    regressions: List[str] = field(default_factory=list)
    unchanged_areas: List[str] = field(default_factory=list)
    top_3_priorities: List[str] = field(default_factory=list)
    raw_response: str = ""


def _noise_threshold(metric_name: str) -> float:
    return _NORM_NOISE if metric_name in _NORM_METRICS else _ANGLE_NOISE


def _direction(metric_name: str, delta: float, threshold: float) -> str:
    if abs(delta) < threshold:
        return "unchanged"
    if metric_name in _HIGHER_IS_BETTER:
        return "improved" if delta > 0 else "regressed"
    if metric_name in _LOWER_IS_BETTER:
        return "improved" if delta < 0 else "regressed"
    # Unknown metric — report direction by sign only
    return "improved" if delta > 0 else "regressed"


def compute_metric_deltas(
    session_a: Dict[str, Any],
    session_b: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Return a list of delta dicts for all comparable scalar metrics.
    Each dict: {metric_name, session_a_value, session_b_value, delta, direction}.
    """
    _SCALAR_METRICS = [
        "right_elbow_mean",
        "left_elbow_mean",
        "right_shoulder_mean",
        "left_shoulder_mean",
        "right_knee_mean",
        "left_knee_mean",
        "torso_rotation_mean",
        "stance_width_mean",
        "com_x_range",
        "swing_count",
        "detection_rate",
    ]

    metrics_a = session_a.get("metrics", {})
    metrics_b = session_b.get("metrics", {})

    def _get(metrics: Dict[str, Any], name: str) -> Optional[float]:
        """Extract scalar; handles nested joint dicts and top-level scalars."""
        joint_map = {
            "right_elbow_mean": ("right_elbow", "mean"),
            "left_elbow_mean": ("left_elbow", "mean"),
            "right_shoulder_mean": ("right_shoulder", "mean"),
            "left_shoulder_mean": ("left_shoulder", "mean"),
            "right_knee_mean": ("right_knee", "mean"),
            "left_knee_mean": ("left_knee", "mean"),
        }
        if name in joint_map:
            joint, stat = joint_map[name]
            joint_dict = metrics.get(joint, {})
            val = joint_dict.get(stat) if isinstance(joint_dict, dict) else None
        else:
            val = metrics.get(name)
        return float(val) if val is not None else None

    deltas = []
    for name in _SCALAR_METRICS:
        a_val = _get(metrics_a, name)
        b_val = _get(metrics_b, name)

        if a_val is None and b_val is None:
            continue

        delta = (b_val - a_val) if (a_val is not None and b_val is not None) else None
        threshold = _noise_threshold(name)
        if delta is not None:
            dir_ = _direction(name, delta, threshold)
        else:
            dir_ = "unchanged"

        deltas.append({
            "metric_name": name,
            "session_a_value": a_val,
            "session_b_value": b_val,
            "delta": delta,
            "direction": dir_,
        })

    return deltas


def _build_delta_prompt(
    session_a: Dict[str, Any],
    session_b: Dict[str, Any],
    metric_deltas: List[Dict[str, Any]],
) -> str:
    ts_a = session_a.get("recorded_at", "Session A")
    ts_b = session_b.get("recorded_at", "Session B")

    def _fmt(v: Optional[float], is_norm: bool = False) -> str:
        if v is None:
            return "N/A"
        return f"{v:.3f}" if is_norm else f"{v:.1f}°"

    # Build delta table
    delta_lines = ["| Metric | Session A | Session B | Delta | Direction |",
                   "|--------|-----------|-----------|-------|-----------|"]
    for d in metric_deltas:
        name = d["metric_name"]
        is_norm = name in _NORM_METRICS or name == "detection_rate"
        a_s = _fmt(d["session_a_value"], is_norm)
        b_s = _fmt(d["session_b_value"], is_norm)
        delta_s = (
            f"{d['delta']:+.3f}" if is_norm and d["delta"] is not None
            else (f"{d['delta']:+.1f}°" if d["delta"] is not None else "N/A")
        )
        delta_lines.append(
            f"| {name} | {a_s} | {b_s} | {delta_s} | {d['direction']} |"
        )

    lines = [
        f"## Session A — {ts_a}",
        f"- Filename: {session_a.get('original_filename', 'unknown')}",
        f"- Frames analyzed: {session_a.get('frames_analyzed', 'N/A')}",
        f"- Detection rate: {session_a.get('detection_rate', 'N/A')}",
        "",
        f"## Session B — {ts_b}",
        f"- Filename: {session_b.get('original_filename', 'unknown')}",
        f"- Frames analyzed: {session_b.get('frames_analyzed', 'N/A')}",
        f"- Detection rate: {session_b.get('detection_rate', 'N/A')}",
        "",
        "## Metric Deltas (B minus A)",
        *delta_lines,
        "",
        "## Required Output Format",
        "Respond with ONLY this JSON structure:",
        "{",
        '  "overall_progress_summary": "2-3 sentence narrative",',
        '  "improvements": ["metric improved: was X, now Y (+Z) — note on significance"],',
        '  "regressions": ["metric worsened: was X, now Y (-Z) — target to aim for"],',
        '  "unchanged_areas": ["metric within noise: X → Y (+Z)"],',
        '  "top_3_priorities": ["Priority with target number", ...]',
        "}",
    ]

    return "\n".join(lines)


def _parse_delta_response(raw_text: str) -> DeltaCoachingReport:
    report = DeltaCoachingReport(raw_response=raw_text)

    text = raw_text
    if "```" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]

    try:
        data = json.loads(text)
        report.overall_progress_summary = data.get("overall_progress_summary", "")
        report.improvements = data.get("improvements", [])
        report.regressions = data.get("regressions", [])
        report.unchanged_areas = data.get("unchanged_areas", [])
        report.top_3_priorities = data.get("top_3_priorities", [])
    except (json.JSONDecodeError, ValueError):
        report.overall_progress_summary = raw_text

    return report


def get_delta_coaching(
    session_a: Dict[str, Any],
    session_b: Dict[str, Any],
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> DeltaCoachingReport:
    """
    Call Claude with delta metrics and return a DeltaCoachingReport.
    metric_deltas are computed internally; callers can reuse via compute_metric_deltas().
    """
    metric_deltas = compute_metric_deltas(session_a, session_b)
    user_prompt = _build_delta_prompt(session_a, session_b, metric_deltas)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=1024,
            system=DELTA_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = message.content[0].text.strip()
    except anthropic.AuthenticationError:
        r = DeltaCoachingReport()
        r.overall_progress_summary = "Authentication failed — check your Anthropic API key."
        return r
    except anthropic.RateLimitError:
        r = DeltaCoachingReport()
        r.overall_progress_summary = "Rate limit exceeded — please wait and retry."
        return r
    except anthropic.APIConnectionError:
        r = DeltaCoachingReport()
        r.overall_progress_summary = "Network error — check your internet connection."
        return r
    except anthropic.APIStatusError as exc:
        r = DeltaCoachingReport()
        r.overall_progress_summary = f"Claude API error ({exc.status_code}): {exc.message}"
        return r

    return _parse_delta_response(raw_text)


@app.task(bind=True, max_retries=0, name="api.tasks.analyze.run_analysis")
def run_analysis(
    self,
    job_id: str,
    input_s3_key: str,
    original_filename: str,
    user_id: str = None,
    resume_from: str = "start",
    activity: str = "tennis",
) -> None:
    # НОВОЕ: Перезагрузить activities модуль каждый раз
    import importlib
    import activities
    importlib.reload(activities)  # ← Это гарантирует свежие промты
    
    from pipeline.video_io import extract_frames
    # ... остаток кода
