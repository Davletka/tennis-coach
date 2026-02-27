"""
Activity plugin registry.

Each activity is a self-contained ActivityConfig that encapsulates:
  - Event detection algorithm (detect_events callable)
  - Per-event analysis window (window_before / window_after frames)
  - Claude coaching prompts (system_prompt, per_event_system_prompt)
  - Display labels for coaching categories and event terminology

Adding a new sport:
    1. Create activities/<sport>.py
    2. Instantiate ActivityConfig and call register(cfg)
    3. Import the module at the bottom of this file so it auto-registers

The pipeline, API, and frontend need zero changes for new activities.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List


@dataclass
class ActivityConfig:
    # Identity
    id: str                          # "tennis", "gym", "badminton"
    display_name: str                # "Tennis", "Gym Workout", "Badminton"

    # Event terminology used throughout the UI
    event_singular: str              # "swing", "rep", "shot"
    event_plural: str                # "swings", "reps", "shots"

    # Frames around each detected event for per-event metrics
    window_before: int               # frames before event peak
    window_after: int                # frames after event peak

    # Coaching category labels — maps API field name → display label.
    # The four API field names are always: swing_mechanics, footwork_movement,
    # stance_posture, shot_selection_tactics.  Each activity gives them meaning.
    coaching_labels: Dict[str, str]

    # Label for the per-event intensity metric (shown in prompts + UI)
    event_metric_label: str          # "Wrist speeds at peaks", "Rep depths (°)"

    # Claude system prompts
    system_prompt: str               # for the overall coaching call
    per_event_system_prompt: str     # for the per-event coaching call

    # Event detection function: (frame_metrics: list) -> list[SwingEvent]
    # Receives the full List[FrameMetrics] and returns List[SwingEvent].
    # SwingEvent.wrist_speed is repurposed as "event intensity" per activity.
    detect_events: Callable


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: Dict[str, ActivityConfig] = {}


def register(cfg: ActivityConfig) -> ActivityConfig:
    """Register an ActivityConfig and return it (so it can be used as a module-level constant)."""
    _REGISTRY[cfg.id] = cfg
    return cfg


def get_activity(activity_id: str) -> ActivityConfig:
    if activity_id not in _REGISTRY:
        raise ValueError(
            f"Unknown activity '{activity_id}'. Available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[activity_id]


def list_activities() -> List[str]:
    return list(_REGISTRY.keys())


def activity_choices() -> List[Dict[str, str]]:
    """Return [{id, display_name}] for all registered activities."""
    return [{"id": cfg.id, "display_name": cfg.display_name} for cfg in _REGISTRY.values()]


# ---------------------------------------------------------------------------
# Auto-register built-in activities (import triggers register() calls)
# ---------------------------------------------------------------------------

from activities import tennis   # noqa: E402, F401
from activities import gym      # noqa: E402, F401
