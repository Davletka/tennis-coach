"""
Unit tests for pipeline/metrics.py — aggregation logic.

LandmarkResult is a plain dataclass; it can be instantiated without
loading the MediaPipe model (that only happens inside PoseDetector).
"""
import pytest

from pipeline.metrics import (
    AggregatedMetrics,
    AngleStat,
    FrameMetrics,
    aggregate_metrics,
)
from pipeline.pose_detector import LandmarkResult


# ── Helpers ──────────────────────────────────────────────────────────────────

def _landmark(x: float, y: float, visibility: float = 1.0):
    """Return a single landmark tuple (x, y, z=0, visibility)."""
    return (x, y, 0.0, visibility)


def _full_result(frame_index: int = 0) -> LandmarkResult:
    """
    Build a LandmarkResult where every landmark sits on a simple 2-D grid
    so that joint angles and distances are deterministic.

    The layout (normalized coords):
      - shoulders at y=0.3, elbows at y=0.5, wrists at y=0.7
      - hips at y=0.6, knees at y=0.75, ankles at y=0.9
      - left side at x=0.35, right side at x=0.65
    """
    # 33 landmarks initialised to a safe default (low visibility → ignored)
    lm = [(0.5, 0.5, 0.0, 0.0)] * 33

    def set_lm(idx, x, y):
        lm[idx] = (x, y, 0.0, 1.0)   # fully visible

    # Shoulders (11=left, 12=right)
    set_lm(11, 0.35, 0.30)
    set_lm(12, 0.65, 0.30)
    # Elbows (13=left, 14=right)
    set_lm(13, 0.35, 0.50)
    set_lm(14, 0.65, 0.50)
    # Wrists (15=left, 16=right)
    set_lm(15, 0.35, 0.70)
    set_lm(16, 0.65, 0.70)
    # Hips (23=left, 24=right)
    set_lm(23, 0.40, 0.60)
    set_lm(24, 0.60, 0.60)
    # Knees (25=left, 26=right)
    set_lm(25, 0.40, 0.75)
    set_lm(26, 0.60, 0.75)
    # Ankles (27=left, 28=right)
    set_lm(27, 0.40, 0.90)
    set_lm(28, 0.60, 0.90)

    return LandmarkResult(landmarks=lm, frame_index=frame_index)


# ── AngleStat.to_dict ────────────────────────────────────────────────────────

class TestAngleStatToDict:
    def test_all_none(self):
        stat = AngleStat()
        d = stat.to_dict()
        assert d == {"mean": None, "min": None, "max": None, "std": None}

    def test_rounds_to_one_decimal(self):
        stat = AngleStat(mean=120.456, min=80.123, max=160.789, std=15.321)
        d = stat.to_dict()
        assert d["mean"] == 120.5
        assert d["min"] == 80.1
        assert d["max"] == 160.8
        assert d["std"] == 15.3


# ── AggregatedMetrics.detection_rate ─────────────────────────────────────────

class TestDetectionRate:
    def test_zero_frames(self):
        agg = AggregatedMetrics()
        assert agg.detection_rate == 0.0

    def test_full_detection(self):
        agg = AggregatedMetrics(frames_analyzed=10, pose_detected_frames=10)
        assert agg.detection_rate == 1.0

    def test_partial_detection(self):
        agg = AggregatedMetrics(frames_analyzed=10, pose_detected_frames=7)
        assert abs(agg.detection_rate - 0.7) < 1e-10


# ── aggregate_metrics ────────────────────────────────────────────────────────

class TestAggregateMetrics:
    def test_empty_inputs(self):
        agg = aggregate_metrics([], [])
        assert agg.frames_analyzed == 0
        assert agg.pose_detected_frames == 0
        assert agg.swing_count == 0
        assert agg.right_elbow.mean is None

    def test_counts_pose_detected_frames(self):
        r = _full_result(0)
        fms = [FrameMetrics(frame_index=0)]
        agg = aggregate_metrics(fms, [r, None])
        assert agg.pose_detected_frames == 1

    def test_single_frame_with_full_result(self):
        """With a fully-visible pose, joint angles should be non-None."""
        r = _full_result(0)
        W, H = 1280, 720
        from pipeline.metrics import compute_frame_metrics
        fm = compute_frame_metrics(r, None, W, H)

        fms = [fm]
        agg = aggregate_metrics(fms, [r])

        assert agg.frames_analyzed == 1
        # Joint angles must be populated
        assert agg.right_elbow.mean is not None
        assert agg.left_elbow.mean is not None
        assert agg.right_shoulder.mean is not None
        assert agg.left_shoulder.mean is not None
        assert agg.right_knee.mean is not None
        assert agg.left_knee.mean is not None
        # Torso & stance
        assert agg.torso_rotation_mean is not None
        assert agg.stance_width_mean is not None

    def test_elbow_angle_is_180_for_straight_arm(self):
        """
        When shoulder/elbow/wrist are collinear (straight arm), elbow angle ≈ 180°.
        """
        from pipeline.metrics import compute_frame_metrics

        lm = [(0.5, 0.5, 0.0, 0.0)] * 33

        def set_lm(idx, x, y):
            lm[idx] = (x, y, 0.0, 1.0)

        # Right arm: straight vertical line → angle at elbow = 180°
        set_lm(12, 0.5, 0.2)   # right shoulder
        set_lm(14, 0.5, 0.5)   # right elbow
        set_lm(16, 0.5, 0.8)   # right wrist
        # Minimal hips so CoM can be computed
        set_lm(23, 0.4, 0.6)
        set_lm(24, 0.6, 0.6)

        r = LandmarkResult(landmarks=lm, frame_index=0)
        fm = compute_frame_metrics(r, None, 640, 480)
        assert fm.right_elbow_angle is not None
        assert abs(fm.right_elbow_angle - 180.0) < 1.0

    def test_swing_detection_with_fast_wrist(self):
        """A wrist speed spike should be detected as a swing event."""
        from pipeline.metrics import compute_frame_metrics

        W, H = 640, 480

        # Frame 0: build a reference result
        r0 = _full_result(0)
        fm0 = compute_frame_metrics(r0, None, W, H)

        # Frame 1: move wrist dramatically to simulate fast swing
        lm1 = list(r0.landmarks)
        lm1[16] = (0.95, 0.70, 0.0, 1.0)   # right wrist jumps far right
        r1 = LandmarkResult(landmarks=lm1, frame_index=1)
        fm1 = compute_frame_metrics(r1, r0, W, H)

        # Frame 2: back to original
        r2 = _full_result(2)
        fm2 = compute_frame_metrics(r2, r1, W, H)

        agg = aggregate_metrics([fm0, fm1, fm2], [r0, r1, r2])
        # The large wrist movement at frame 1 should register as a swing
        assert agg.swing_count >= 1

    def test_com_range_computed(self):
        """com_x_range should be positive when CoM shifts across frames."""
        from pipeline.metrics import compute_frame_metrics

        W, H = 640, 480
        fms = []
        results = []

        for i, hip_x_offset in enumerate([-0.1, 0.0, 0.1]):
            lm = list(_full_result(i).landmarks)
            lm[23] = (0.40 + hip_x_offset, 0.60, 0.0, 1.0)
            lm[24] = (0.60 + hip_x_offset, 0.60, 0.0, 1.0)
            r = LandmarkResult(landmarks=lm, frame_index=i)
            fm = compute_frame_metrics(r, None, W, H)
            fms.append(fm)
            results.append(r)

        agg = aggregate_metrics(fms, results)
        assert agg.com_x_range is not None
        assert agg.com_x_range > 0.0

    def test_none_results_counted_correctly(self):
        """Frames where pose was not detected should count but not affect stats."""
        from pipeline.metrics import compute_frame_metrics

        r0 = _full_result(0)
        fm0 = compute_frame_metrics(r0, None, 640, 480)
        fm_no_pose = FrameMetrics(frame_index=1)   # all angles None

        agg = aggregate_metrics([fm0, fm_no_pose], [r0, None])
        assert agg.frames_analyzed == 2
        assert agg.pose_detected_frames == 1
        # Stats should still be computable from the one detected frame
        assert agg.right_elbow.mean is not None
