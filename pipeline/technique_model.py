"""
Technique quality model for tennis stroke analysis.

Two modes:
  1. Rule-based (always available) — flags errors using reference biomechanics ranges.
     Works out of the box without any training data.
  2. ML model (optional) — sklearn model trained on labeled datasets.
     Activated when a .pkl file is present. Overrides the rule-based score.

Usage:
    from pipeline.technique_model import get_model

    model = get_model()             # loads from default path if available
    prediction = model.predict(psm) # psm = PerSwingMetrics instance
    # Returns: {'quality_score': 72, 'errors': ['корпус почти не разворачивается'],
    #           'confidence': 0.84, 'source': 'ml'} or source='rule'

Training:
    python scripts/train_model.py --dataset data/tennis_swings.csv
"""
from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default model file path
# ---------------------------------------------------------------------------

DEFAULT_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "models", "tennis_technique.pkl"
)

# ---------------------------------------------------------------------------
# Feature definition
# ---------------------------------------------------------------------------

FEATURE_NAMES = [
    "right_elbow_at_contact",
    "left_elbow_at_contact",
    "right_shoulder_at_contact",
    "right_knee_at_contact",
    "left_knee_at_contact",
    "torso_rotation_at_contact",
    "torso_rotation_delta",
    "stance_width",
    "com_x_range",
]

# Human-readable error labels (Russian) — used in the coaching prompt
ERROR_LABELS: Dict[str, str] = {
    "arm_too_straight":       "локоть слишком прямой в момент удара",
    "arm_too_bent":           "локоть слишком сильно согнут",
    "insufficient_rotation":  "корпус почти не разворачивается",
    "contact_too_low":        "точка контакта слишком низкая",
    "narrow_stance":          "стойка слишком узкая",
    "knees_not_bent":         "колени почти прямые — нужно ниже",
    "wide_stance":            "стойка слишком широкая",
}

# ---------------------------------------------------------------------------
# Rule-based predictor (always available, no training required)
# ---------------------------------------------------------------------------

# Rules format: (error_key, test_fn, shot_types_to_check)
# test_fn receives a dict of feature values; returns True if error detected.
# shot_types: None = all shots, or set of specific types like {"forehand", "backhand"}
_RULES = [
    (
        "arm_too_straight",
        lambda f: (f.get("right_elbow_at_contact") or 140) > 165,
        {"forehand", "backhand"},
    ),
    (
        "arm_too_bent",
        lambda f: (f.get("right_elbow_at_contact") or 130) < 90,
        None,
    ),
    (
        "insufficient_rotation",
        lambda f: (f.get("torso_rotation_delta") or 30) < 20,
        {"forehand", "backhand"},
    ),
    (
        "contact_too_low",
        lambda f: (f.get("contact_height") or 0) > 0.15,
        {"forehand", "backhand"},
    ),
    (
        "narrow_stance",
        lambda f: (f.get("stance_width") or 1.5) < 1.0,
        None,
    ),
    (
        "wide_stance",
        lambda f: (f.get("stance_width") or 1.5) > 2.2,
        None,
    ),
    (
        "knees_not_bent",
        lambda f: (f.get("right_knee_at_contact") or 140) > 165,
        None,
    ),
]


def _rule_based_predict(features: dict, shot_type: str = "unknown") -> dict:
    """Apply biomechanics rules and return quality score + error list."""
    errors = []
    for error_key, test_fn, applicable_shots in _RULES:
        if applicable_shots is not None and shot_type not in applicable_shots:
            continue
        try:
            if test_fn(features):
                errors.append(ERROR_LABELS[error_key])
        except Exception:
            pass

    # Quality score: start at 85, deduct per error (max deduction 60)
    deduction = min(len(errors) * 15, 60)
    quality_score = max(25, 85 - deduction)

    return {
        "quality_score": quality_score,
        "errors": errors,
        "confidence": 0.6,
        "source": "rule",
    }


# ---------------------------------------------------------------------------
# TechniqueModel
# ---------------------------------------------------------------------------

@dataclass
class ModelBundle:
    """Holds both sub-models saved to disk."""
    quality_model: object      # sklearn regressor  → predicts 0-100 score
    error_model: object        # sklearn classifier → predicts error flags
    error_keys: List[str]      # ordered list matching error_model output columns
    feature_names: List[str]   # ordered list of features


class TechniqueModel:
    """
    Tennis technique quality model.

    Call .load() once at startup; .predict() thereafter.
    If no model file is found, falls back to rule-based predictions.
    """

    def __init__(self, model_path: str = DEFAULT_MODEL_PATH):
        self.model_path = model_path
        self._bundle: Optional[ModelBundle] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> bool:
        """
        Attempt to load the trained model from disk.
        Returns True if loaded, False if no file exists.
        """
        if not os.path.isfile(self.model_path):
            logger.info("No trained model at %s — using rule-based predictor", self.model_path)
            return False
        try:
            with open(self.model_path, "rb") as f:
                self._bundle = pickle.load(f)
            logger.info("Loaded technique model from %s", self.model_path)
            return True
        except Exception as exc:
            logger.warning("Failed to load model from %s: %s", self.model_path, exc)
            return False

    def save(self, bundle: ModelBundle, path: Optional[str] = None) -> None:
        """Save a trained ModelBundle to disk."""
        target = path or self.model_path
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as f:
            pickle.dump(bundle, f)
        logger.info("Saved technique model to %s", target)
        self._bundle = bundle

    def is_ml_available(self) -> bool:
        return self._bundle is not None

    def predict(self, psm) -> Optional[dict]:
        """
        Predict technique quality for a single swing.

        psm: PerSwingMetrics instance (from pipeline.metrics)
        Returns dict or None if the swing has no usable data.
        """
        features = self._extract_features(psm)
        if features is None:
            return None

        shot_type = getattr(psm, "motion_type", "unknown")

        # Build a plain dict for rule-based logic
        feat_dict = dict(zip(FEATURE_NAMES, features))
        feat_dict["contact_height"] = getattr(psm, "right_wrist_y_at_contact", None)

        if self._bundle is not None:
            return self._ml_predict(features, feat_dict, shot_type)
        return _rule_based_predict(feat_dict, shot_type)

    # ------------------------------------------------------------------
    # Training helpers (called from scripts/train_model.py)
    # ------------------------------------------------------------------

    def train(
        self,
        X: np.ndarray,
        y_quality: np.ndarray,
        y_errors: np.ndarray,
        error_keys: List[str],
    ) -> ModelBundle:
        """
        Train both sub-models on labeled data.

        X:         shape (n_samples, len(FEATURE_NAMES))
        y_quality: shape (n_samples,)  — quality scores 0-100
        y_errors:  shape (n_samples, len(error_keys)) — binary flags
        error_keys: list of error key strings (matching ERROR_LABELS keys)
        """
        try:
            from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier
            from sklearn.multioutput import MultiOutputClassifier
            from sklearn.preprocessing import StandardScaler
            from sklearn.pipeline import Pipeline
        except ImportError:
            raise ImportError(
                "scikit-learn is required for training. "
                "Install it with: pip install scikit-learn pandas"
            )

        # Quality regression model
        quality_model = Pipeline([
            ("scaler", StandardScaler()),
            ("regressor", GradientBoostingRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42
            )),
        ])
        quality_model.fit(X, y_quality)

        # Error classification model (multi-label)
        error_model = Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", MultiOutputClassifier(
                RandomForestClassifier(n_estimators=200, random_state=42)
            )),
        ])
        error_model.fit(X, y_errors)

        bundle = ModelBundle(
            quality_model=quality_model,
            error_model=error_model,
            error_keys=error_keys,
            feature_names=FEATURE_NAMES,
        )
        return bundle

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_features(self, psm) -> Optional[np.ndarray]:
        """Extract a fixed-length feature vector from PerSwingMetrics."""
        FALLBACK = {
            "right_elbow_at_contact":    140.0,
            "left_elbow_at_contact":     90.0,
            "right_shoulder_at_contact": 85.0,
            "right_knee_at_contact":     140.0,
            "left_knee_at_contact":      140.0,
            "torso_rotation_at_contact": 30.0,
            "torso_rotation_delta":      30.0,
            "stance_width":              1.4,
            "com_x_range":               0.1,
        }

        def _get(attr: str) -> float:
            val = getattr(psm, attr, None)
            if val is None:
                val = getattr(psm, attr.replace("_at_contact", ""), None)
            return float(val) if val is not None else FALLBACK.get(attr, 0.0)

        values = [_get(name) for name in FEATURE_NAMES]

        # Require at least elbow and knee data to be non-default
        re = getattr(psm, "right_elbow_at_contact", None)
        rk = getattr(psm, "right_knee_at_contact", None)
        if re is None and rk is None:
            return None

        return np.array(values, dtype=np.float32).reshape(1, -1)

    def _ml_predict(self, features: np.ndarray, feat_dict: dict, shot_type: str) -> dict:
        """Run sklearn models and return prediction dict."""
        bundle = self._bundle
        try:
            quality_score = float(bundle.quality_model.predict(features)[0])
            quality_score = max(0.0, min(100.0, quality_score))

            error_flags = bundle.error_model.predict(features)[0]
            # Also get confidence from the quality regressor if possible
            errors = [
                ERROR_LABELS.get(bundle.error_keys[i], bundle.error_keys[i])
                for i, flag in enumerate(error_flags)
                if flag == 1
            ]

            return {
                "quality_score": round(quality_score),
                "errors": errors,
                "confidence": 0.85,
                "source": "ml",
            }
        except Exception as exc:
            logger.warning("ML predict failed, falling back to rules: %s", exc)
            return _rule_based_predict(feat_dict, shot_type)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_model_instance: Optional[TechniqueModel] = None


def get_model(model_path: str = DEFAULT_MODEL_PATH) -> TechniqueModel:
    """
    Return the singleton TechniqueModel, loading it from disk on first call.
    Thread-safe for reads; loading is done once at startup.
    """
    global _model_instance
    if _model_instance is None:
        _model_instance = TechniqueModel(model_path=model_path)
        _model_instance.load()
    return _model_instance
