"""Tests for outcome tracker."""

import pytest

from tapps_mcp.metrics.outcome_tracker import CodeOutcome, OutcomeTracker


@pytest.fixture
def metrics_dir(tmp_path):
    d = tmp_path / "metrics"
    d.mkdir()
    return d


@pytest.fixture
def tracker(metrics_dir):
    return OutcomeTracker(metrics_dir)


class TestCodeOutcome:
    def test_roundtrip(self):
        outcome = CodeOutcome(
            session_id="s1",
            file_path="/tmp/test.py",
            initial_scores={"overall": 65.0},
            final_scores={"overall": 85.0},
            iterations=3,
        )
        d = outcome.to_dict()
        restored = CodeOutcome.from_dict(d)
        assert restored.session_id == "s1"
        assert restored.initial_scores == {"overall": 65.0}


class TestOutcomeTracker:
    def test_track_initial_scores(self, tracker):
        outcome = tracker.track_initial_scores(
            session_id="s1",
            file_path="/tmp/test.py",
            scores={"overall": 75.0, "security": 80.0},
        )
        assert outcome.session_id == "s1"
        assert outcome.iterations == 1
        assert outcome.first_pass_success is True  # 75 >= 70 (standard)

    def test_first_pass_failure(self, tracker):
        outcome = tracker.track_initial_scores(
            session_id="s1",
            file_path="/tmp/test.py",
            scores={"overall": 60.0},
        )
        assert outcome.first_pass_success is False

    def test_track_iteration(self, tracker):
        tracker.track_initial_scores("s1", "/tmp/test.py", {"overall": 60.0})
        updated = tracker.track_iteration("s1", "/tmp/test.py", {"overall": 75.0}, "security")
        assert updated is not None
        assert updated.iterations == 2
        assert updated.final_scores == {"overall": 75.0}
        assert "security" in updated.expert_consultations

    def test_track_iteration_unknown_file(self, tracker):
        result = tracker.track_iteration("s1", "/nonexistent.py", {})
        assert result is None

    def test_finalize_outcome(self, tracker):
        tracker.track_initial_scores("s1", "/tmp/test.py", {"overall": 60.0})
        tracker.track_iteration("s1", "/tmp/test.py", {"overall": 85.0})
        finalized = tracker.finalize_outcome("s1", "/tmp/test.py", gate_passed=True)
        assert finalized is not None
        assert finalized.finalized is True
        assert finalized.time_to_quality >= 0

    def test_finalize_persists_to_disk(self, tracker, metrics_dir):
        tracker.track_initial_scores("s1", "/tmp/test.py", {"overall": 60.0})
        tracker.finalize_outcome("s1", "/tmp/test.py", gate_passed=True)

        outcomes_file = metrics_dir / "outcomes.jsonl"
        assert outcomes_file.exists()

    def test_load_outcomes(self, tracker):
        tracker.track_initial_scores("s1", "/tmp/a.py", {"overall": 60.0})
        tracker.finalize_outcome("s1", "/tmp/a.py")
        tracker.track_initial_scores("s1", "/tmp/b.py", {"overall": 70.0})
        tracker.finalize_outcome("s1", "/tmp/b.py")

        outcomes = tracker.load_outcomes()
        assert len(outcomes) == 2

    def test_load_outcomes_with_limit(self, tracker):
        for i in range(5):
            tracker.track_initial_scores("s1", f"/tmp/{i}.py", {"overall": 60.0 + i})
            tracker.finalize_outcome("s1", f"/tmp/{i}.py")

        outcomes = tracker.load_outcomes(limit=2)
        assert len(outcomes) == 2

    def test_get_active_outcomes(self, tracker):
        tracker.track_initial_scores("s1", "/tmp/a.py", {"overall": 60.0})
        tracker.track_initial_scores("s1", "/tmp/b.py", {"overall": 70.0})

        active = tracker.get_active_outcomes()
        assert len(active) == 2

    def test_get_learning_data_insufficient(self, tracker):
        for i in range(5):
            tracker.track_initial_scores("s1", f"/tmp/{i}.py", {"overall": 60.0})
            tracker.finalize_outcome("s1", f"/tmp/{i}.py")

        data = tracker.get_learning_data(min_outcomes=10)
        assert len(data) == 0

    def test_get_statistics(self, tracker):
        tracker.track_initial_scores("s1", "/tmp/a.py", {"overall": 80.0})
        tracker.finalize_outcome("s1", "/tmp/a.py")
        tracker.track_initial_scores("s1", "/tmp/b.py", {"overall": 50.0})
        tracker.track_iteration("s1", "/tmp/b.py", {"overall": 75.0}, "testing")
        tracker.finalize_outcome("s1", "/tmp/b.py")

        stats = tracker.get_statistics()
        assert stats["total_outcomes"] == 2
        assert stats["first_pass_success_rate"] == 0.5
        assert "testing" in stats["expert_usage"]

    def test_empty_statistics(self, tracker):
        stats = tracker.get_statistics()
        assert stats["total_outcomes"] == 0
