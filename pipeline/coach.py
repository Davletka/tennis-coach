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


# ---------------------------------------------------------------------------
# Human-readable metric interpreters
# Convert raw numbers → plain-language descriptions for the prompt.
# Claude sees the description + number in brackets, but is instructed
# to use only words in its output — not the numbers.
# ---------------------------------------------------------------------------

def _describe_elbow(angle: Optional[float]) -> str:
    if angle is None:
        return "нет данных"
    if angle < 90:
        return f"сильно согнута (глубокий хват) [{angle:.0f}°]"
    elif angle < 115:
        return f"хорошо согнута [{angle:.0f}°]"
    elif angle < 145:
        return f"слегка согнута [{angle:.0f}°]"
    elif angle < 165:
        return f"почти прямая [{angle:.0f}°]"
    else:
        return f"полностью выпрямлена [{angle:.0f}°]"


def _describe_knee(angle: Optional[float]) -> str:
    if angle is None:
        return "нет данных"
    if angle < 110:
        return f"очень глубокое приседание [{angle:.0f}°]"
    elif angle < 130:
        return f"глубоко согнуты — отличная атлетическая стойка [{angle:.0f}°] ✓"
    elif angle < 150:
        return f"хорошо согнуты [{angle:.0f}°] ✓"
    elif angle < 165:
        return f"слегка согнуты, можно ниже [{angle:.0f}°]"
    else:
        return f"почти прямые — нужно согнуть ниже [{angle:.0f}°]"


def _describe_torso_rotation(delta: Optional[float]) -> str:
    if delta is None:
        return "нет данных"
    if delta < 10:
        return f"корпус почти не разворачивается — удар только рукой [{delta:.0f}°]"
    elif delta < 25:
        return f"слабый поворот корпуса [{delta:.0f}°]"
    elif delta < 45:
        return f"хороший поворот корпуса [{delta:.0f}°] ✓"
    else:
        return f"отличный поворот корпуса — тело работает хорошо [{delta:.0f}°] ✓"


def _describe_torso_at_contact(angle: Optional[float]) -> str:
    if angle is None:
        return "нет данных"
    if angle < 10:
        return f"корпус смотрит прямо на сетку [{angle:.0f}°]"
    elif angle < 25:
        return f"небольшой разворот в сторону удара [{angle:.0f}°]"
    elif angle < 45:
        return f"хороший разворот плеч [{angle:.0f}°] ✓"
    else:
        return f"сильный разворот корпуса [{angle:.0f}°]"


def _describe_stance(width: Optional[float]) -> str:
    if width is None:
        return "нет данных"
    if width < 0.9:
        return f"стойка слишком узкая, ноги близко друг к другу [{width:.1f}×]"
    elif width < 1.2:
        return f"стойка немного узковата [{width:.1f}×]"
    elif width < 1.8:
        return f"правильная ширина стойки [{width:.1f}×] ✓"
    elif width < 2.2:
        return f"стойка чуть широковата [{width:.1f}×]"
    else:
        return f"стойка слишком широкая [{width:.1f}×]"


def _describe_wrist_height(val: Optional[float]) -> str:
    if val is None:
        return "нет данных"
    if val < -0.15:
        return f"удар на уровне плеч или выше — очень высокий контакт"
    elif val < 0:
        return f"удар выше бёдер — хорошая точка контакта ✓"
    elif val < 0.15:
        return f"удар на уровне бёдер"
    else:
        return f"удар ниже бёдер — точка контакта слишком низко"


def _describe_com_range(val: Optional[float]) -> str:
    if val is None:
        return "нет данных"
    if val < 0.05:
        return f"игрок почти не двигался [{val:.2f}]"
    elif val < 0.15:
        return f"небольшое перемещение по корту [{val:.2f}]"
    elif val < 0.30:
        return f"хорошее движение по корту [{val:.2f}] ✓"
    else:
        return f"активное перемещение по корту [{val:.2f}]"


SYSTEM_PROMPT = """Ты опытный профессиональный тренер по теннису с 20+ годами опыта. 
Ты анализируешь видео техники игрока так, как будто стоишь на корте и смотришь на него.

ТВОЙ СТИЛЬ ОБЩЕНИЯ:
- Отзывчивый, но честный — указываешь проблемы, но мотивируешь
- Конкретный, а не общий — не "улучши технику", а "разворачивай плечи раньше"
- Простой язык — "рука выпрямилась в момент удара", "ноги не успевают", "хороший вес на передней ноге"
- ЗАПРЕЩЕНО: числа, градусы, "биомеханика", киновидео связи, научные термины

СТРУКТУРА ОТВЕТА:
- Swing Mechanics: что хорошо в ударе, что нужно улучшить (2-3 предложения)
- Footwork: движение ног перед и во время удара (2 предложения)
- Stance: положение тела, баланс, вес (2 предложения)
- Tactics: почему этот удар полезен, где его использовать (1-2 предложения)
- Top 3 priorities: 3 главных совета для улучшения (конкретные, осуществимые)
- Target angles: конкретные числа ТОЛЬКО если они явно помогают

ВАЖНО: Говори как человек, а не как аналитик. Будь вдохновляющим.
"""

PER_EVENT_SYSTEM_PROMPT = """Ты профессиональный тренер по теннису. Комментируешь КАЖДЫЙ удар отдельно и уникально.

КАЖДЫЙ УДАР - ЭТО НОВАЯ ИСТОРИЯ:
- Не повторяй один и тот же совет на разные удары
- Найди уникальные сильные и слабые стороны каждого удара
- Говори, как если бы смотрел на монитор в реальном времени

ЯЗЫК:
- Простой, как разговор на корте
- "Рука ушла слишком далеко назад", "отличный контакт!", "ноги готовы"
- БЕЗ чисел, градусов, терминов

ОДИН КОММЕНТАРИЙ - ОДНА ИДЕЯ:
- Quick note: 1 предложение о главном (хорошо или нужно улучшить)
- Mechanics: что хорошо/плохо в ударе (1-2 предложения)
- Footwork: были ли ноги готовы (1 предложение)
- Stance: как выглядел баланс (1 предложение)
- Tactics: зачем этот удар, где его использовать (1 предложение)
- Top 3: 3 совета ДЛЯ ЭТОГО УДАРА (не общие)

ЭНЕРГИЯ: Будь энергичным, мотивирующим, как РЕАЛЬНЫЙ тренер на корте!
"""

# SYSTEM_PROMPT = """You are an expert tennis coach with 20+ years of experience coaching players at all levels.
# You analyze video-based biomechanical data and deliver precise, actionable coaching feedback.

# TENNIS BIOMECHANICS REFERENCE RANGES:
# - Elbow angle at contact (forehand groundstroke): 120–160° (some flexion for control)
# - Elbow angle at contact (serve / overhead): 160–180° (near-full extension at impact)
# - Knee bend during groundstroke preparation: 120–145° (athletic ready position)
# - Torso rotation change during a groundstroke: 30–60° (measures hip-to-shoulder kinematic chain; below 20° = insufficient rotation)
# - Stance width (normalized to hip width): 1.2–1.8 for groundstrokes (below 1.0 = too narrow; above 2.2 = too wide)
# - Shoulder angle (elbow–shoulder–hip): 70–100° at contact for most groundstrokes
# - Wrist height relative to hips at contact: negative value = wrist above hips (good for flat/topspin); strongly positive = contact point too low

# RULES:
# - Always reference specific numbers from the provided metrics.
# - Be direct and avoid generic advice without a target angle or metric value.
# - Every suggestion must be tied to a measurable metric.
# - Give BALANCED analysis across all four areas: swing mechanics, footwork, stance/posture, and tactics.
# - Do NOT fixate on wrist speed — evaluate the full kinematic chain: lower body → hips → core → shoulder → elbow.
# - If a metric is within the healthy reference range, acknowledge it positively rather than manufacturing a problem.
# """

# PER_SWING_SYSTEM_PROMPT = """You are an expert tennis coach with 20+ years of experience coaching players at all levels.
# You analyze video-based biomechanical data swing by swing and deliver precise, actionable coaching feedback.

# TENNIS BIOMECHANICS REFERENCE RANGES:
# - Elbow angle at contact (forehand groundstroke): 120–160° | (serve / overhead): 160–180°
# - Knee bend during preparation: 120–145° (athletic stance)
# - Torso rotation change during swing: 30–60° — this is the kinematic chain indicator; below 20° means the hips and core are not driving the shot
# - Stance width (normalized to hip width): 1.2–1.8 for groundstrokes
# - Shoulder angle (elbow–shoulder–hip): 70–100° at contact
# - Wrist height at contact: negative value = wrist above hips (desirable); strongly positive = contact point too low

# RULES:
# - Analyze each swing individually — do NOT repeat identical advice for every swing.
# - Prioritize "At Contact Point" metrics over window averages for mechanics feedback.
# - Reference specific numbers from the metrics provided.
# - Every suggestion must be tied to a measurable metric from that swing's window.
# - Give BALANCED analysis covering the full kinematic chain: lower body → hips → core → shoulder → elbow.
# - Do NOT focus excessively on wrist speed — it is only a proxy for racket head speed, not a technique target.
# - If a metric is within the healthy reference range, acknowledge it rather than inventing issues.
# """

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

    event_plural = activity_cfg.event_plural if activity_cfg else "swings"

    low_detection_warning = ""
    if agg.detection_rate < MIN_DETECTION_RATE:
        low_detection_warning = (
            f"\n⚠️  Поза определена только в {detection_pct:.0f}% кадров — уверенность снижена.\n"
        )

    shot_types = list({e.motion_type for e in agg.swing_events if e.motion_type != "unknown"})
    shot_types_str = ", ".join(shot_types) if shot_types else "не определён"

    lines = [
        "## Контекст видео",
        f"- Длительность: {duration_s:.1f}с",
        f"- Обнаружено ударов: {agg.swing_count} ({shot_types_str})",
        f"- Качество обнаружения позы: {detection_pct:.0f}%",
        low_detection_warning,
        "",
        "## Положение рук (средние значения за всю сессию)",
        f"- Правый локоть: {_describe_elbow(agg.right_elbow.mean)}",
        f"- Левый локоть:  {_describe_elbow(agg.left_elbow.mean)}",
        "",
        "## Положение ног",
        f"- Правое колено: {_describe_knee(agg.right_knee.mean)}",
        f"- Левое колено:  {_describe_knee(agg.left_knee.mean)}",
        f"- Ширина стойки: {_describe_stance(agg.stance_width_mean)}",
        "",
        "## Работа корпуса",
        f"- Поворот корпуса: {_describe_torso_rotation(agg.torso_rotation_max)}",
        f"- Перемещение по корту: {_describe_com_range(agg.com_x_range)}",
        "",
        "ВАЖНО ДЛЯ ОТВЕТА: Описывай движения словами — НЕ упоминай цифры в скобках, градусы или технические термины.",
    ]

    return "\n".join(lines)


def _fmt(v: Optional[float]) -> str:
    return f"{v:.1f}" if v is not None else "?"


def _build_swing_prompt(psm, fps: float, activity_cfg=None, model_prediction: Optional[dict] = None) -> str:
    t = psm.peak_frame / max(fps, 1.0)
    event_singular = activity_cfg.event_singular if activity_cfg else "swing"

    motion_type = getattr(psm, "motion_type", "unknown")
    SHOT_NAMES = {"forehand": "форхенд", "backhand": "бэкхенд", "serve": "подача", "unknown": "удар"}
    shot_name = SHOT_NAMES.get(motion_type, motion_type)

    lines = [
        f"## Удар #{psm.swing_index + 1} — {shot_name} (момент t={t:.1f}с)",
        "",
        "### В момент удара",
        f"- Правый локоть: {_describe_elbow(psm.right_elbow_at_contact)}",
        f"- Левый локоть:  {_describe_elbow(psm.left_elbow_at_contact)}",
        f"- Правое колено: {_describe_knee(psm.right_knee_at_contact)}",
        f"- Левое колено:  {_describe_knee(psm.left_knee_at_contact)}",
        f"- Разворот корпуса в момент удара: {_describe_torso_at_contact(psm.torso_rotation_at_contact)}",
        f"- Точка контакта (высота): {_describe_wrist_height(psm.right_wrist_y_at_contact)}",
        "",
        "### Динамика удара",
        f"- Поворот корпуса за весь удар: {_describe_torso_rotation(psm.torso_rotation_delta)}",
        f"- Ширина стойки: {_describe_stance(psm.stance_width_mean)}",
        f"- Перемещение по корту: {_describe_com_range(psm.com_x_range)}",
    ]

    # Add model prediction block if available
    if model_prediction:
        score = model_prediction.get("quality_score")
        errors = model_prediction.get("errors", [])
        source = model_prediction.get("source", "rule")
        lines += [
            "",
            f"### Оценка модели ({'ML' if source == 'ml' else 'правила'})",
            f"- Качество техники: {score}/100" if score is not None else "",
        ]
        if errors:
            lines.append(f"- Замеченные проблемы: {', '.join(errors)}")

    lines += [
        "",
        "ВАЖНО ДЛЯ ОТВЕТА: Описывай движения словами — НЕ упоминай числа в скобках или градусы.",
    ]
    return "\n".join(line for line in lines if line is not None)


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


def _get_single_swing_coaching(psm, fps: float, client, model: str, activity_cfg=None, model_prediction: Optional[dict] = None) -> SwingCoaching:
    user_prompt = _build_swing_prompt(psm, fps, activity_cfg=activity_cfg, model_prediction=model_prediction)
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
    Technique model predictions are injected into each prompt when available.
    """
    if not per_swing_metrics:
        return []

    # Pre-compute model predictions for all swings (fast, local inference)
    try:
        from pipeline.technique_model import get_model
        technique_model = get_model()
        model_predictions = {
            psm.swing_index: technique_model.predict(psm)
            for psm in per_swing_metrics
        }
    except Exception:
        model_predictions = {}

    client = anthropic.Anthropic(api_key=api_key)
    total = len(per_swing_metrics)
    results = []
    done_count = 0

    with ThreadPoolExecutor(max_workers=min(total, 3)) as executor:
        futures = {
            executor.submit(
                _get_single_swing_coaching,
                psm, fps, client, model, activity_cfg,
                model_predictions.get(psm.swing_index),
            ): psm
            for psm in per_swing_metrics
        }
        for future in as_completed(futures):
            results.append(future.result())
            done_count += 1
            if on_swing_done is not None:
                on_swing_done(done_count, total)

    results.sort(key=lambda sc: sc.swing_index)
    return results
