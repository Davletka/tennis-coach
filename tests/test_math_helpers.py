"""
Unit tests for utils/math_helpers.py — pure math, no external service deps.
"""
import math
import pytest
from utils.math_helpers import (
    angle_between_three_points,
    euclidean_distance,
    find_peaks,
    safe_max,
    safe_mean,
    safe_min,
    safe_std,
)


# ── angle_between_three_points ───────────────────────────────────────────────

class TestAngleBetweenThreePoints:
    def test_right_angle(self):
        # 90° at origin with perpendicular rays along axes
        angle = angle_between_three_points((1, 0), (0, 0), (0, 1))
        assert abs(angle - 90.0) < 1e-6

    def test_straight_line(self):
        # 180° — three collinear points
        angle = angle_between_three_points((0, 0), (1, 0), (2, 0))
        assert abs(angle - 180.0) < 1e-6

    def test_zero_angle(self):
        # Rays in the same direction → 0°
        angle = angle_between_three_points((2, 0), (0, 0), (1, 0))
        assert abs(angle - 0.0) < 1e-6

    def test_45_degree_angle(self):
        angle = angle_between_three_points((1, 0), (0, 0), (1, 1))
        assert abs(angle - 45.0) < 1e-5

    def test_zero_length_vector_returns_zero(self):
        # a == b → ba has zero length
        angle = angle_between_three_points((0, 0), (0, 0), (1, 1))
        assert angle == 0.0

    def test_float_inputs(self):
        angle = angle_between_three_points((0.5, 0.0), (0.0, 0.0), (0.0, 0.5))
        assert abs(angle - 90.0) < 1e-6

    def test_symmetric(self):
        # angle(a,b,c) == angle(c,b,a)
        a = angle_between_three_points((3, 4), (0, 0), (1, 2))
        b = angle_between_three_points((1, 2), (0, 0), (3, 4))
        assert abs(a - b) < 1e-10


# ── euclidean_distance ────────────────────────────────────────────────────────

class TestEuclideanDistance:
    def test_same_point(self):
        assert euclidean_distance((3, 4), (3, 4)) == 0.0

    def test_unit_axes(self):
        assert abs(euclidean_distance((0, 0), (1, 0)) - 1.0) < 1e-10
        assert abs(euclidean_distance((0, 0), (0, 1)) - 1.0) < 1e-10

    def test_pythagorean_triple(self):
        # 3-4-5 triangle
        assert abs(euclidean_distance((0, 0), (3, 4)) - 5.0) < 1e-10

    def test_float_coords(self):
        d = euclidean_distance((0.0, 0.0), (0.5, 0.5))
        assert abs(d - math.sqrt(0.5)) < 1e-10


# ── find_peaks ────────────────────────────────────────────────────────────────

class TestFindPeaks:
    def test_single_peak(self):
        values = [0.0, 0.01, 0.05, 0.01, 0.0]
        peaks = find_peaks(values, threshold=0.02, min_distance=1)
        assert peaks == [2]

    def test_no_peaks_below_threshold(self):
        values = [0.0, 0.01, 0.015, 0.01, 0.0]
        peaks = find_peaks(values, threshold=0.02, min_distance=1)
        assert peaks == []

    def test_two_peaks_with_min_distance(self):
        values = [0.0, 0.1, 0.0, 0.1, 0.0]
        peaks = find_peaks(values, threshold=0.05, min_distance=2)
        assert len(peaks) == 2
        assert 1 in peaks and 3 in peaks

    def test_min_distance_suppresses_close_peaks(self):
        # Two peaks only 2 frames apart; min_distance=5 should keep only first
        values = [0.0, 0.1, 0.0, 0.1, 0.0, 0.0, 0.0, 0.0]
        peaks = find_peaks(values, threshold=0.05, min_distance=5)
        assert len(peaks) == 1
        assert peaks[0] == 1

    def test_none_values_treated_as_zero(self):
        values = [None, 0.1, None, 0.05, None]
        peaks = find_peaks(values, threshold=0.05, min_distance=1)
        assert 1 in peaks

    def test_empty_list(self):
        assert find_peaks([], threshold=0.01) == []

    def test_first_and_last_not_peaks(self):
        # First and last indices can never be peaks (loop starts at 1, ends at len-2)
        values = [0.5, 0.0, 0.0]
        assert find_peaks(values, threshold=0.1, min_distance=1) == []


# ── safe_* statistics ─────────────────────────────────────────────────────────

class TestSafeStats:
    def test_safe_mean_normal(self):
        assert abs(safe_mean([1.0, 2.0, 3.0]) - 2.0) < 1e-10

    def test_safe_mean_with_none(self):
        assert abs(safe_mean([1.0, None, 3.0]) - 2.0) < 1e-10

    def test_safe_mean_all_none(self):
        assert safe_mean([None, None]) is None

    def test_safe_mean_empty(self):
        assert safe_mean([]) is None

    def test_safe_min(self):
        assert safe_min([3.0, 1.0, 2.0]) == 1.0

    def test_safe_min_with_none(self):
        assert safe_min([None, 5.0, 2.0]) == 2.0

    def test_safe_min_all_none(self):
        assert safe_min([None]) is None

    def test_safe_max(self):
        assert safe_max([3.0, 1.0, 2.0]) == 3.0

    def test_safe_max_with_none(self):
        assert safe_max([None, 5.0, 2.0]) == 5.0

    def test_safe_max_all_none(self):
        assert safe_max([None]) is None

    def test_safe_std_normal(self):
        result = safe_std([2.0, 4.0])
        assert result is not None
        assert abs(result - 1.0) < 1e-10

    def test_safe_std_single_value(self):
        # std of one value is undefined — return None
        assert safe_std([5.0]) is None

    def test_safe_std_with_none(self):
        # [1.0, None, 3.0] → valid = [1.0, 3.0], std = 1.0
        result = safe_std([1.0, None, 3.0])
        assert result is not None
        assert abs(result - 1.0) < 1e-10

    def test_safe_std_all_none(self):
        assert safe_std([None, None]) is None
