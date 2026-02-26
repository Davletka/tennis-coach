"""
Pure math utilities — no project-level imports.
"""
from __future__ import annotations

import numpy as np
from typing import Optional, List, Tuple


def angle_between_three_points(
    a: Tuple[float, float],
    b: Tuple[float, float],
    c: Tuple[float, float],
) -> float:
    """
    Return the angle at vertex *b* formed by rays b→a and b→c, in degrees.
    Returns 0.0 if any vector has zero length.
    """
    a = np.array(a, dtype=float)
    b = np.array(b, dtype=float)
    c = np.array(c, dtype=float)

    ba = a - b
    bc = c - b

    norm_ba = np.linalg.norm(ba)
    norm_bc = np.linalg.norm(bc)
    if norm_ba == 0 or norm_bc == 0:
        return 0.0

    cos_angle = np.dot(ba, bc) / (norm_ba * norm_bc)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


def find_peaks(
    values: List[Optional[float]],
    threshold: float,
    min_distance: int = 10,
) -> List[int]:
    """
    Return indices of local maxima above *threshold* with at least
    *min_distance* frames between consecutive peaks.

    None values are skipped (treated as 0 for peak detection).
    """
    filled = np.array([v if v is not None else 0.0 for v in values], dtype=float)

    peaks: List[int] = []
    last_peak = -min_distance - 1

    for i in range(1, len(filled) - 1):
        if (
            filled[i] > threshold
            and filled[i] >= filled[i - 1]
            and filled[i] >= filled[i + 1]
            and (i - last_peak) >= min_distance
        ):
            peaks.append(i)
            last_peak = i

    return peaks


def safe_mean(values: List[Optional[float]]) -> Optional[float]:
    """Mean of non-None values; None if list is empty or all None."""
    valid = [v for v in values if v is not None]
    return float(np.mean(valid)) if valid else None


def safe_min(values: List[Optional[float]]) -> Optional[float]:
    valid = [v for v in values if v is not None]
    return float(np.min(valid)) if valid else None


def safe_max(values: List[Optional[float]]) -> Optional[float]:
    valid = [v for v in values if v is not None]
    return float(np.max(valid)) if valid else None


def safe_std(values: List[Optional[float]]) -> Optional[float]:
    valid = [v for v in values if v is not None]
    return float(np.std(valid)) if len(valid) > 1 else None


def euclidean_distance(
    p1: Tuple[float, float], p2: Tuple[float, float]
) -> float:
    return float(np.linalg.norm(np.array(p1) - np.array(p2)))
