"""
Train the tennis technique quality model from a labeled CSV dataset.

Usage:
    python scripts/train_model.py --dataset data/tennis_swings.csv
    python scripts/train_model.py --dataset data/tennis_swings.csv --output models/tennis_technique.pkl

Dataset CSV format (see data/tennis_swings_example.csv for a template):

Required columns:
    right_elbow_at_contact      — degrees (e.g. 145)
    left_elbow_at_contact       — degrees
    right_shoulder_at_contact   — degrees
    right_knee_at_contact       — degrees
    left_knee_at_contact        — degrees
    torso_rotation_at_contact   — degrees
    torso_rotation_delta        — degrees (total rotation during swing)
    stance_width                — ratio to hip width (e.g. 1.4)
    com_x_range                 — lateral movement 0-1 (e.g. 0.12)
    quality_score               — 0-100 (your subjective rating)
    shot_type                   — forehand / backhand / serve

Optional error flag columns (0 or 1):
    err_arm_too_straight
    err_arm_too_bent
    err_insufficient_rotation
    err_contact_too_low
    err_narrow_stance
    err_knees_not_bent
    err_wide_stance

If error columns are missing they are auto-generated from quality_score thresholds.
"""
from __future__ import annotations

import argparse
import sys
import os

# Make sure repo root is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np

from pipeline.technique_model import (
    FEATURE_NAMES,
    ModelBundle,
    TechniqueModel,
    DEFAULT_MODEL_PATH,
    ERROR_LABELS,
)


def load_dataset(path: str):
    """Load and validate the CSV dataset. Returns X, y_quality, y_errors, error_keys."""
    try:
        import pandas as pd
    except ImportError:
        print("ERROR: pandas is required for training. Run: pip install pandas scikit-learn")
        sys.exit(1)

    df = pd.read_csv(path)
    print(f"Loaded {len(df)} rows from {path}")

    # Check required columns
    missing = [col for col in FEATURE_NAMES if col not in df.columns]
    if missing:
        print(f"ERROR: Missing required columns: {missing}")
        print(f"Required: {FEATURE_NAMES}")
        sys.exit(1)

    if "quality_score" not in df.columns:
        print("ERROR: 'quality_score' column is required (0-100)")
        sys.exit(1)

    # Fill missing values with column medians
    for col in FEATURE_NAMES:
        if df[col].isnull().any():
            median = df[col].median()
            df[col] = df[col].fillna(median)
            print(f"  Filled {df[col].isnull().sum()} NaN values in '{col}' with median {median:.1f}")

    X = df[FEATURE_NAMES].values.astype(np.float32)
    y_quality = df["quality_score"].values.astype(np.float32)

    # Error columns — use existing or auto-generate from quality + rules
    error_keys = list(ERROR_LABELS.keys())
    err_cols = [f"err_{k}" for k in error_keys]
    available_err_cols = [c for c in err_cols if c in df.columns]

    if available_err_cols:
        print(f"Using {len(available_err_cols)} error columns from dataset")
        y_errors = np.zeros((len(df), len(error_keys)), dtype=np.int32)
        for i, key in enumerate(error_keys):
            col = f"err_{key}"
            if col in df.columns:
                y_errors[:, i] = df[col].fillna(0).astype(int).values
    else:
        print("No error columns found — auto-generating from rules")
        y_errors = _auto_generate_errors(df, error_keys)

    print(f"Features: {X.shape}, Quality targets: {y_quality.shape}, Error targets: {y_errors.shape}")
    return X, y_quality, y_errors, error_keys


def _auto_generate_errors(df, error_keys: list) -> np.ndarray:
    """Generate error flags from biomechanics rules when not provided in dataset."""
    n = len(df)
    y = np.zeros((n, len(error_keys)), dtype=np.int32)
    key_to_idx = {k: i for i, k in enumerate(error_keys)}

    def _set(key, mask):
        if key in key_to_idx:
            y[:, key_to_idx[key]] = mask.astype(int)

    _set("arm_too_straight",      df["right_elbow_at_contact"] > 165)
    _set("arm_too_bent",          df["right_elbow_at_contact"] < 90)
    _set("insufficient_rotation", df["torso_rotation_delta"] < 20)
    _set("narrow_stance",         df["stance_width"] < 1.0)
    _set("wide_stance",           df["stance_width"] > 2.2)
    _set("knees_not_bent",        df["right_knee_at_contact"] > 165)

    return y


def print_evaluation(model: TechniqueModel, X, y_quality, y_errors, error_keys):
    """Print quick evaluation metrics after training."""
    try:
        from sklearn.metrics import mean_absolute_error, accuracy_score
    except ImportError:
        return

    bundle = model._bundle
    if bundle is None:
        return

    q_pred = bundle.quality_model.predict(X)
    mae = mean_absolute_error(y_quality, q_pred)
    print(f"\nQuality model MAE: {mae:.1f} points (on training data)")

    e_pred = bundle.error_model.predict(X)
    for i, key in enumerate(error_keys):
        acc = accuracy_score(y_errors[:, i], e_pred[:, i])
        prevalence = y_errors[:, i].mean()
        if prevalence > 0:
            print(f"  Error '{key}': accuracy={acc:.0%}, prevalence={prevalence:.0%}")


def main():
    parser = argparse.ArgumentParser(description="Train tennis technique model")
    parser.add_argument("--dataset", required=True, help="Path to labeled CSV dataset")
    parser.add_argument("--output", default=DEFAULT_MODEL_PATH, help="Output .pkl path")
    args = parser.parse_args()

    X, y_quality, y_errors, error_keys = load_dataset(args.dataset)

    print("\nTraining model...")
    model = TechniqueModel(model_path=args.output)
    bundle = model.train(X, y_quality, y_errors, error_keys)
    model.save(bundle, args.output)

    print_evaluation(model, X, y_quality, y_errors, error_keys)

    print(f"\nModel saved to: {args.output}")
    print("Restart the Celery worker to load the new model.")


if __name__ == "__main__":
    main()
