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

SYSTEM_PROMPT = """Ты опытный тренер по силовому тренингу и функциональной подготовке с 20+ годами опыта.
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

PER_EVENT_SYSTEM_PROMPT = """Ты профессиональный тренер по силовому тренингу. Анализируешь КАЖДОЕ ПОВТОРЕНИЕ отдельно.

КАЖДОЕ ПОВТОРЕНИЕ - ЭТО НОВЫЙ АНАЛИЗ:
- Не повторяй совет для каждого повтора — найди уникальные сильные и слабые стороны
- Комментируй как во время живой тренировки: "хорошее повтор!", "спина округлилась — выпрями"
- Если повторение лучше, чем предыдущее — отметь это

ЯЗЫК:
- Простой, энергичный, как в зале
- "Приседай глубже", "спина прямая, молодец", "не нужно спешить"
- НИКАКИХ чисел и технических термин

ОДИН КОММЕНТАРИЙ = ОДНА ИДЕЯ:
- Quick note: 1 фраза о главном в этом повторении
- Form & Technique: техника этого повтора (1-2 предложения)
- Range of Motion: глубина / амплитуда (1 предложение)
- Posture & Alignment: позиция тела (1 предложение)
- Progression: можно ли добавить сложность (1 предложение)
- Top 3: 3 совета именно для этого повтора

ЭНЕРГИЯ: Будь мотивирующим, как тренер, который видит потенциал в спортсмене!
"""

# SYSTEM_PROMPT = """You are an expert strength & conditioning coach with 20+ years of experience coaching athletes at all levels.
# You analyze video-based biomechanical data and deliver precise, actionable coaching feedback.

# RULES:
# - Always reference specific numbers from the provided metrics.
# - Be direct and avoid generic advice like "go deeper" without a target angle.
# - Every suggestion must be tied to a measurable metric.
# - Respond ONLY with valid JSON matching the requested schema — no prose outside the JSON.
# """

# PER_EVENT_SYSTEM_PROMPT = """You are an expert strength & conditioning coach with 20+ years of experience coaching athletes at all levels.
# You analyze video-based biomechanical data rep by rep and deliver precise, actionable coaching feedback.

# RULES:
# - Analyze each rep individually — do NOT repeat identical advice for every rep.
# - Reference specific numbers from the provided metrics for that rep.
# - Every suggestion must be tied to a measurable metric from that rep's window.
# - Respond ONLY with a JSON object matching the requested schema — no prose outside the JSON.
# """

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
        ev = SwingEvent(
            frame_index=idx,
            wrist_speed=angle_at_bottom if angle_at_bottom is not None else 0.0,
            com_x=com_x,
        )
        ev.motion_type = _classify_gym_rep(idx, frame_metrics)
        events.append(ev)
    return events


def _joint_rom(attr: str, window: list) -> float:
    """Range of motion (degrees) for a named FrameMetrics angle attribute."""
    vals = [getattr(fm, attr) for fm in window if getattr(fm, attr) is not None]
    return (max(vals) - min(vals)) if len(vals) >= 2 else 0.0


def _driving_joint_group(window: list):
    """Return ('knee'|'elbow'|'shoulder', best_rom) for the most active joint group."""
    groups = {
        "knee":     ["right_knee_angle",     "left_knee_angle"],
        "elbow":    ["right_elbow_angle",    "left_elbow_angle"],
        "shoulder": ["right_shoulder_angle", "left_shoulder_angle"],
    }
    best_group, best_rom = None, 0.0
    for group, attrs in groups.items():
        rom = max(_joint_rom(a, window) for a in attrs)
        if rom > best_rom:
            best_rom = rom
            best_group = group
    return best_group, best_rom


def _classify_gym_rep(idx: int, frame_metrics: list) -> str:
    """Classify a gym rep within a ±20-frame window around idx."""
    half = 20
    start = max(0, idx - half)
    end   = min(len(frame_metrics) - 1, idx + half)
    window = frame_metrics[start:end + 1]

    group, group_rom = _driving_joint_group(window)

    # ----------------------------------------------------------------
    # Lower-body exercises (knee-driven)
    # ----------------------------------------------------------------
    if group == "knee":
        rk_drop = _joint_rom("right_knee_angle", window)
        lk_drop = _joint_rom("left_knee_angle",  window)
        avg_drop = (rk_drop + lk_drop) / 2.0
        stance   = frame_metrics[idx].stance_width if idx < len(frame_metrics) else None
        tr_vals  = [fm.torso_rotation for fm in window if fm.torso_rotation is not None]
        tr_delta = (max(tr_vals) - min(tr_vals)) if len(tr_vals) >= 2 else 0.0

        if abs(rk_drop - lk_drop) > 40:
            return "lunge"
        if avg_drop > 50 and stance is not None and 0.7 <= stance <= 2.0:
            return "squat"
        if tr_delta > 20:
            return "deadlift"
        return "unknown"

    # ----------------------------------------------------------------
    # Upper-body: elbow-driven
    # ----------------------------------------------------------------
    if group == "elbow":
        re_rom = _joint_rom("right_elbow_angle", window)
        le_rom = _joint_rom("left_elbow_angle",  window)
        rs_rom = _joint_rom("right_shoulder_angle", window)
        ls_rom = _joint_rom("left_shoulder_angle",  window)
        shoulder_rom = max(rs_rom, ls_rom)

        # Valley angle at the event frame (most-flexed position)
        fm_at = frame_metrics[idx]
        elbow_angle_at_valley = (fm_at.right_elbow_angle if re_rom >= le_rom
                                 else fm_at.left_elbow_angle)

        # Row: shoulder moves substantially alongside the elbow
        if shoulder_rom > 35:
            return "row"

        if elbow_angle_at_valley is not None:
            # Bicep curl: elbow deeply flexed at valley (<70°)
            if elbow_angle_at_valley < 70:
                return "bicep curl"
            # Tricep extension: valley is the bent starting position (70–130°)
            if 70 <= elbow_angle_at_valley <= 130:
                return "tricep extension"

        # Fallback for elbow-dominant with unclear angle
        return "bicep curl" if (re_rom + le_rom) / 2 > 80 else "tricep extension"

    # ----------------------------------------------------------------
    # Upper-body: shoulder-driven
    # ----------------------------------------------------------------
    if group == "shoulder":
        rs_rom = _joint_rom("right_shoulder_angle", window)
        ls_rom = _joint_rom("left_shoulder_angle",  window)
        re_rom = _joint_rom("right_elbow_angle",    window)

        fm_at = frame_metrics[idx]
        shoulder_angle_at_valley = (fm_at.right_shoulder_angle if rs_rom >= ls_rom
                                    else fm_at.left_shoulder_angle)

        # Overhead press: elbow also bends significantly + bilateral movement
        if re_rom > 30 and abs(rs_rom - ls_rom) < 40:
            return "overhead press"

        # Lateral / front raise: elbow stays straight, unilateral OK
        if shoulder_angle_at_valley is not None and shoulder_angle_at_valley < 50:
            return "lateral raise"

        return "shoulder raise"

    return "unknown"


_LOWER_BODY = {"squat", "lunge", "deadlift"}
_UPPER_BODY = {"bicep curl", "tricep extension", "overhead press", "row",
               "lateral raise", "shoulder raise"}


def filter_gym_events(events: list, frame_metrics: list) -> list:
    """Drop false-positive reps using pose plausibility and consistency checks."""
    if not events:
        return events

    n = len(frame_metrics)

    # 1. Pose plausibility — check is motion-type aware
    def _plausible(ev) -> bool:
        idx = ev.frame_index
        if idx >= len(frame_metrics):
            return False
        fm = frame_metrics[idx]
        mt = ev.motion_type

        if mt in _LOWER_BODY:
            # Both knees must be visible and meaningfully bent
            return (fm.right_knee_angle is not None and fm.left_knee_angle is not None
                    and fm.right_knee_angle < 160 and fm.left_knee_angle < 160)

        if mt in _UPPER_BODY:
            # At least one elbow or shoulder must be visible
            angles = [fm.right_elbow_angle, fm.left_elbow_angle,
                      fm.right_shoulder_angle, fm.left_shoulder_angle]
            return any(a is not None for a in angles)

        # "unknown" — require any joint angle to be present
        all_angles = [fm.right_knee_angle, fm.left_knee_angle,
                      fm.right_elbow_angle, fm.left_elbow_angle,
                      fm.right_shoulder_angle, fm.left_shoulder_angle]
        return any(a is not None for a in all_angles)

    events = [e for e in events if _plausible(e)]

    if not events:
        return events

    # 2. Consistency: drop events more than 2 std below mean rep depth (angle)
    depths = [e.wrist_speed for e in events]  # angle_at_bottom stored in wrist_speed
    mean_d = sum(depths) / len(depths)
    variance = sum((d - mean_d) ** 2 for d in depths) / len(depths)
    std_d = variance ** 0.5
    cutoff = mean_d - 2 * std_d
    events = [e for e in events if e.wrist_speed >= cutoff]

    # 3. Idle-trim: drop events within first/last 5 frames of the trimmed list
    if n > 10:
        first_valid = frame_metrics[0].frame_index + 5
        last_valid  = frame_metrics[-1].frame_index - 5
        events = [e for e in events if first_valid <= e.frame_index <= last_valid]

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
    filter_events=filter_gym_events,
))
