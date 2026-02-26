"""
Unit tests for api/models.py — Pydantic model validation.
"""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from api.models import (
    AnalyzeResponse,
    AngleStatResult,
    CoachingReportResult,
    CompareRequest,
    CompareResponse,
    DeltaCoachingReport,
    JobResultResponse,
    JobStatusResponse,
    MetricDelta,
    MetricsResult,
    ProgressDataPoint,
    SessionListResponse,
    SessionSummary,
    SwingEventResult,
)


NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# ── AnalyzeResponse ──────────────────────────────────────────────────────────

class TestAnalyzeResponse:
    def test_defaults(self):
        r = AnalyzeResponse(job_id="abc123")
        assert r.job_id == "abc123"
        assert r.status == "pending"

    def test_explicit_status(self):
        r = AnalyzeResponse(job_id="x", status="running")
        assert r.status == "running"

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            AnalyzeResponse(job_id="x", status="unknown")


# ── JobStatusResponse ────────────────────────────────────────────────────────

class TestJobStatusResponse:
    def test_valid(self):
        r = JobStatusResponse(
            job_id="j1",
            status="completed",
            progress=100,
            message="Done",
            created_at=NOW,
            updated_at=NOW,
        )
        assert r.progress == 100
        assert r.status == "completed"

    def test_progress_defaults_to_zero(self):
        r = JobStatusResponse(
            job_id="j1", status="pending", created_at=NOW, updated_at=NOW
        )
        assert r.progress == 0
        assert r.message == ""


# ── AngleStatResult ──────────────────────────────────────────────────────────

class TestAngleStatResult:
    def test_all_none(self):
        stat = AngleStatResult()
        assert stat.mean is None
        assert stat.min is None
        assert stat.max is None
        assert stat.std is None

    def test_with_values(self):
        stat = AngleStatResult(mean=120.5, min=80.0, max=160.0, std=15.3)
        assert stat.mean == 120.5

    def test_partial_values(self):
        stat = AngleStatResult(mean=90.0)
        assert stat.mean == 90.0
        assert stat.std is None


# ── SwingEventResult ──────────────────────────────────────────────────────────

class TestSwingEventResult:
    def test_required_fields(self):
        e = SwingEventResult(frame_index=42, wrist_speed=0.05)
        assert e.frame_index == 42
        assert e.com_x is None

    def test_with_com(self):
        e = SwingEventResult(frame_index=10, wrist_speed=0.08, com_x=0.52)
        assert e.com_x == 0.52


# ── MetricsResult ─────────────────────────────────────────────────────────────

def _make_metrics(**kwargs):
    defaults = dict(
        right_elbow=AngleStatResult(),
        left_elbow=AngleStatResult(),
        right_shoulder=AngleStatResult(),
        left_shoulder=AngleStatResult(),
        right_knee=AngleStatResult(),
        left_knee=AngleStatResult(),
        frames_analyzed=100,
        pose_detected_frames=80,
        detection_rate=0.8,
    )
    defaults.update(kwargs)
    return MetricsResult(**defaults)


class TestMetricsResult:
    def test_defaults(self):
        m = _make_metrics()
        assert m.swing_count == 0
        assert m.swing_events == []
        assert m.torso_rotation_mean is None

    def test_swing_events(self):
        events = [SwingEventResult(frame_index=5, wrist_speed=0.04)]
        m = _make_metrics(swing_count=1, swing_events=events)
        assert len(m.swing_events) == 1


# ── CoachingReportResult ──────────────────────────────────────────────────────

class TestCoachingReportResult:
    def test_defaults_empty_strings(self):
        r = CoachingReportResult()
        assert r.swing_mechanics == ""
        assert r.top_3_priorities == []

    def test_with_content(self):
        r = CoachingReportResult(
            swing_mechanics="Good follow-through",
            top_3_priorities=["Fix grip", "Bend knees", "Watch ball"],
        )
        assert len(r.top_3_priorities) == 3


# ── JobResultResponse ─────────────────────────────────────────────────────────

class TestJobResultResponse:
    def test_valid(self):
        r = JobResultResponse(
            job_id="j1",
            status="completed",
            coaching_report=CoachingReportResult(),
            metrics=_make_metrics(),
            annotated_video_url="https://s3.example.com/out.mp4",
            input_video_url="https://s3.example.com/in.mp4",
            fps=30.0,
            total_source_frames=300,
        )
        assert r.fps == 30.0
        assert r.total_source_frames == 300


# ── CompareRequest / CompareResponse ─────────────────────────────────────────

class TestCompareRequest:
    def test_valid(self):
        r = CompareRequest(session_a_id="s1", session_b_id="s2")
        assert r.session_a_id == "s1"

    def test_missing_field(self):
        with pytest.raises(ValidationError):
            CompareRequest(session_a_id="s1")


class TestMetricDelta:
    def test_improved(self):
        d = MetricDelta(
            metric_name="right_elbow_mean",
            session_a_value=90.0,
            session_b_value=120.0,
            delta=30.0,
            direction="improved",
        )
        assert d.direction == "improved"

    def test_none_values(self):
        d = MetricDelta(
            metric_name="torso_rotation_mean",
            session_a_value=None,
            session_b_value=None,
            delta=None,
            direction="unchanged",
        )
        assert d.delta is None


class TestDeltaCoachingReport:
    def test_defaults(self):
        r = DeltaCoachingReport()
        assert r.improvements == []
        assert r.regressions == []
        assert r.overall_progress_summary == ""

    def test_with_data(self):
        r = DeltaCoachingReport(
            overall_progress_summary="Good progress",
            improvements=["Better footwork"],
            top_3_priorities=["Fix backhand"],
        )
        assert len(r.improvements) == 1


class TestCompareResponse:
    def test_valid(self):
        r = CompareResponse(
            session_a_id="s1",
            session_b_id="s2",
            metric_deltas=[],
            delta_coaching=DeltaCoachingReport(),
        )
        assert r.session_a_id == "s1"
        assert r.metric_deltas == []


# ── ProgressDataPoint ─────────────────────────────────────────────────────────

class TestProgressDataPoint:
    def test_required_fields(self):
        p = ProgressDataPoint(
            session_id="s1",
            recorded_at=NOW,
            detection_rate=0.85,
        )
        assert p.right_elbow_mean is None
        assert p.detection_rate == 0.85

    def test_with_metrics(self):
        p = ProgressDataPoint(
            session_id="s1",
            recorded_at=NOW,
            detection_rate=0.9,
            right_elbow_mean=120.0,
            swing_count=5,
        )
        assert p.right_elbow_mean == 120.0
        assert p.swing_count == 5
