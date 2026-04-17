"""Tests for file-based adaptive persistence."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from tapps_core.adaptive.models import CodeOutcome, DomainWeightEntry, DomainWeightsSnapshot
from tapps_core.adaptive.persistence import (
    DomainWeightStore,
    FileOutcomeTracker,
    FilePerformanceTracker,
    save_json_atomic,
)


class TestFileOutcomeTracker:
    @pytest.fixture()
    def tracker(self, tmp_path: Path) -> FileOutcomeTracker:
        return FileOutcomeTracker(tmp_path)

    def test_save_and_load_roundtrip(self, tracker: FileOutcomeTracker):
        outcome = CodeOutcome(
            workflow_id="wf-1",
            file_path="main.py",
            initial_scores={"complexity": 7.0},
            first_pass_success=True,
        )
        tracker.save_outcome(outcome)
        loaded = tracker.load_outcomes()
        assert len(loaded) == 1
        assert loaded[0].workflow_id == "wf-1"
        assert loaded[0].first_pass_success is True

    def test_load_with_limit(self, tracker: FileOutcomeTracker):
        for i in range(5):
            tracker.save_outcome(CodeOutcome(workflow_id=f"wf-{i}", file_path="f.py"))
        loaded = tracker.load_outcomes(limit=2)
        assert len(loaded) == 2
        assert loaded[0].workflow_id == "wf-3"
        assert loaded[1].workflow_id == "wf-4"

    def test_load_with_workflow_id_filter(self, tracker: FileOutcomeTracker):
        tracker.save_outcome(CodeOutcome(workflow_id="wf-a", file_path="a.py"))
        tracker.save_outcome(CodeOutcome(workflow_id="wf-b", file_path="b.py"))
        loaded = tracker.load_outcomes(workflow_id="wf-a")
        assert len(loaded) == 1
        assert loaded[0].file_path == "a.py"

    def test_load_empty(self, tracker: FileOutcomeTracker):
        loaded = tracker.load_outcomes()
        assert loaded == []

    def test_get_statistics_empty(self, tracker: FileOutcomeTracker):
        stats = tracker.get_statistics()
        assert stats["total_outcomes"] == 0
        assert stats["first_pass_success_rate"] == 0.0

    def test_get_statistics_populated(self, tracker: FileOutcomeTracker):
        tracker.save_outcome(
            CodeOutcome(
                workflow_id="wf-1",
                file_path="a.py",
                first_pass_success=True,
                iterations=1,
                expert_consultations=["expert-security"],
            )
        )
        tracker.save_outcome(
            CodeOutcome(
                workflow_id="wf-2",
                file_path="b.py",
                first_pass_success=False,
                iterations=3,
                expert_consultations=["expert-security", "expert-testing"],
            )
        )
        stats = tracker.get_statistics()
        assert stats["total_outcomes"] == 2
        assert stats["first_pass_success_rate"] == 0.5
        assert stats["avg_iterations"] == 2.0
        assert stats["expert_usage"]["expert-security"] == 2

    def test_jsonl_format(self, tracker: FileOutcomeTracker):
        tracker.save_outcome(CodeOutcome(workflow_id="wf-1", file_path="a.py"))
        lines = tracker._file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["workflow_id"] == "wf-1"


class TestFilePerformanceTracker:
    @pytest.fixture()
    def tracker(self, tmp_path: Path) -> FilePerformanceTracker:
        return FilePerformanceTracker(tmp_path)

    def test_track_and_calculate(self, tracker: FilePerformanceTracker):
        tracker.track_consultation("expert-security", "security", 0.85, "How to hash?")
        tracker.track_consultation("expert-security", "security", 0.90, "Salt usage?")
        perf = tracker.calculate_performance("expert-security")
        assert perf is not None
        assert perf.consultations == 2
        assert 0.87 <= perf.avg_confidence <= 0.88
        assert "security" in perf.domain_coverage

    def test_calculate_empty(self, tracker: FilePerformanceTracker):
        perf = tracker.calculate_performance("nonexistent")
        assert perf is None

    def test_get_all_performance(self, tracker: FilePerformanceTracker):
        tracker.track_consultation("expert-a", "security", 0.8)
        tracker.track_consultation("expert-b", "testing", 0.7)
        all_perf = tracker.get_all_performance()
        assert "expert-a" in all_perf
        assert "expert-b" in all_perf

    def test_weakness_low_confidence(self, tracker: FilePerformanceTracker):
        # Track consultations with low confidence.
        for _ in range(3):
            tracker.track_consultation("expert-weak", "domain-x", 0.3)
        perf = tracker.calculate_performance("expert-weak")
        assert perf is not None
        assert "low_confidence" in perf.weaknesses

    def test_load_skips_malformed_lines(self, tracker: FilePerformanceTracker):
        """Malformed JSONL lines are skipped without failing."""
        tracker.track_consultation("expert-a", "sec", 0.8)
        perf_file = tracker._file
        # Append invalid line
        with perf_file.open("a", encoding="utf-8") as fh:
            fh.write("{ invalid json }\n")
        perf = tracker.calculate_performance("expert-a")
        assert perf is not None
        assert perf.consultations == 1

    def test_load_skips_non_dict_lines(self, tracker: FilePerformanceTracker):
        """Non-dict JSON lines are skipped."""
        perf_file = tracker._file
        perf_file.parent.mkdir(parents=True, exist_ok=True)
        with perf_file.open("w", encoding="utf-8") as fh:
            fh.write('["array", "not", "dict"]\n')
        perf = tracker.calculate_performance("any")
        assert perf is None


class TestSaveJsonAtomic:
    def test_writes_json(self, tmp_path: Path):
        target = tmp_path / "data.json"
        save_json_atomic({"key": "value"}, target)
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["key"] == "value"

    def test_overwrites_existing(self, tmp_path: Path):
        target = tmp_path / "data.json"
        save_json_atomic({"v": 1}, target)
        save_json_atomic({"v": 2}, target)
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["v"] == 2

    def test_creates_parent_directory(self, tmp_path: Path):
        target = tmp_path / "nested" / "dir" / "data.json"
        save_json_atomic({"created": True}, target)
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["created"] is True

    def test_writes_list(self, tmp_path: Path):
        target = tmp_path / "list.json"
        save_json_atomic([1, 2, 3], target)
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data == [1, 2, 3]


# ---------------------------------------------------------------------------
# DomainWeightStore tests (Epic 57, Story 57.1)
# ---------------------------------------------------------------------------


class TestDomainWeightStore:
    """Tests for DomainWeightStore business domain weight persistence."""

    @pytest.fixture()
    def store(self, tmp_path: Path) -> DomainWeightStore:
        return DomainWeightStore(tmp_path)

    # -- Basic save/load roundtrip ------------------------------------------

    def test_save_and_load_technical_weight(self, store: DomainWeightStore):
        store.save_weight("security", 1.2, samples=10, domain_type="technical")
        entry = store.get_weight("security", domain_type="technical")
        assert entry is not None
        assert entry.domain == "security"
        assert entry.weight == 1.2
        assert entry.samples == 10

    def test_save_and_load_business_weight(self, store: DomainWeightStore):
        store.save_weight("acme-billing", 1.5, samples=5, domain_type="business")
        entry = store.get_weight("acme-billing", domain_type="business")
        assert entry is not None
        assert entry.domain == "acme-billing"
        assert entry.weight == 1.5
        assert entry.samples == 5

    def test_business_weight_not_in_technical(self, store: DomainWeightStore):
        store.save_weight("acme-billing", 1.5, domain_type="business")
        # Should not appear in technical weights
        entry = store.get_weight("acme-billing", domain_type="technical")
        assert entry is None

    def test_technical_weight_not_in_business(self, store: DomainWeightStore):
        store.save_weight("security", 1.2, domain_type="technical")
        # Should not appear in business weights
        entry = store.get_weight("security", domain_type="business")
        assert entry is None

    # -- Load empty/missing file --------------------------------------------

    def test_load_empty(self, store: DomainWeightStore):
        snapshot = store.load_weights()
        assert isinstance(snapshot, DomainWeightsSnapshot)
        assert snapshot.technical == {}
        assert snapshot.business == {}

    def test_get_weight_missing_returns_none(self, store: DomainWeightStore):
        entry = store.get_weight("nonexistent", domain_type="technical")
        assert entry is None

    def test_get_weight_value_missing_returns_default(self, store: DomainWeightStore):
        value = store.get_weight_value("nonexistent", domain_type="technical")
        assert value == 1.0  # Default weight

    # -- Weight clamping ----------------------------------------------------

    def test_weight_clamps_to_min(self, store: DomainWeightStore):
        store.save_weight("test", 0.01, domain_type="technical")
        entry = store.get_weight("test", domain_type="technical")
        assert entry is not None
        assert entry.weight == 0.1  # Clamped to minimum

    def test_weight_clamps_to_max(self, store: DomainWeightStore):
        store.save_weight("test", 10.0, domain_type="technical")
        entry = store.get_weight("test", domain_type="technical")
        assert entry is not None
        assert entry.weight == 3.0  # Clamped to maximum

    # -- Feedback updates ---------------------------------------------------

    def test_update_from_positive_feedback(self, store: DomainWeightStore):
        store.save_weight("security", 1.0, domain_type="technical")
        entry = store.update_from_feedback(
            "security", helpful=True, domain_type="technical", learning_rate=0.1
        )
        assert entry.weight > 1.0
        assert entry.samples == 1
        assert entry.positive_count == 1
        assert entry.negative_count == 0

    def test_update_from_negative_feedback(self, store: DomainWeightStore):
        store.save_weight("security", 1.0, domain_type="technical")
        entry = store.update_from_feedback(
            "security", helpful=False, domain_type="technical", learning_rate=0.1
        )
        assert entry.weight < 1.0
        assert entry.samples == 1
        assert entry.positive_count == 0
        assert entry.negative_count == 1

    def test_update_creates_new_entry_if_missing(self, store: DomainWeightStore):
        entry = store.update_from_feedback("new-domain", helpful=True, domain_type="business")
        assert entry.domain == "new-domain"
        assert entry.weight > 1.0
        assert entry.samples == 1

    def test_multiple_feedback_accumulates(self, store: DomainWeightStore):
        store.save_weight("testing", 1.0, domain_type="technical")
        store.update_from_feedback("testing", helpful=True, domain_type="technical")
        store.update_from_feedback("testing", helpful=True, domain_type="technical")
        entry = store.update_from_feedback("testing", helpful=False, domain_type="technical")
        assert entry.samples == 3
        assert entry.positive_count == 2
        assert entry.negative_count == 1

    # -- Load separate sections ---------------------------------------------

    def test_load_technical_weights(self, store: DomainWeightStore):
        store.save_weight("security", 1.2, domain_type="technical")
        store.save_weight("testing", 0.9, domain_type="technical")
        store.save_weight("acme-billing", 1.5, domain_type="business")
        tech = store.load_technical_weights()
        assert "security" in tech
        assert "testing" in tech
        assert "acme-billing" not in tech
        assert len(tech) == 2

    def test_load_business_weights(self, store: DomainWeightStore):
        store.save_weight("security", 1.2, domain_type="technical")
        store.save_weight("acme-billing", 1.5, domain_type="business")
        store.save_weight("acme-compliance", 0.8, domain_type="business")
        biz = store.load_business_weights()
        assert "acme-billing" in biz
        assert "acme-compliance" in biz
        assert "security" not in biz
        assert len(biz) == 2

    # -- Delete weights -----------------------------------------------------

    def test_delete_existing_weight(self, store: DomainWeightStore):
        store.save_weight("security", 1.2, domain_type="technical")
        deleted = store.delete_weight("security", domain_type="technical")
        assert deleted is True
        assert store.get_weight("security", domain_type="technical") is None

    def test_delete_nonexistent_returns_false(self, store: DomainWeightStore):
        deleted = store.delete_weight("nonexistent", domain_type="technical")
        assert deleted is False

    # -- Clear weights ------------------------------------------------------

    def test_clear_technical_only(self, store: DomainWeightStore):
        store.save_weight("security", 1.2, domain_type="technical")
        store.save_weight("acme", 1.5, domain_type="business")
        store.clear_weights(domain_type="technical")
        snapshot = store.load_weights()
        assert snapshot.technical == {}
        assert len(snapshot.business) == 1

    def test_clear_business_only(self, store: DomainWeightStore):
        store.save_weight("security", 1.2, domain_type="technical")
        store.save_weight("acme", 1.5, domain_type="business")
        store.clear_weights(domain_type="business")
        snapshot = store.load_weights()
        assert len(snapshot.technical) == 1
        assert snapshot.business == {}

    def test_clear_all_weights(self, store: DomainWeightStore):
        store.save_weight("security", 1.2, domain_type="technical")
        store.save_weight("acme", 1.5, domain_type="business")
        store.clear_weights(domain_type=None)
        snapshot = store.load_weights()
        assert snapshot.technical == {}
        assert snapshot.business == {}

    # -- Statistics ---------------------------------------------------------

    def test_statistics_empty(self, store: DomainWeightStore):
        stats = store.get_statistics()
        assert stats["total_domains"] == 0
        assert stats["technical_count"] == 0
        assert stats["business_count"] == 0
        assert stats["total_samples"] == 0
        assert stats["avg_weight"] == 1.0  # Default

    def test_statistics_populated(self, store: DomainWeightStore):
        store.save_weight("security", 1.2, samples=10, domain_type="technical")
        store.save_weight("testing", 0.8, samples=5, domain_type="technical")
        store.save_weight("acme", 1.5, samples=3, domain_type="business")
        stats = store.get_statistics()
        assert stats["total_domains"] == 3
        assert stats["technical_count"] == 2
        assert stats["business_count"] == 1
        assert stats["total_samples"] == 18
        assert 1.1 <= stats["avg_weight"] <= 1.2

    def test_statistics_top_domains(self, store: DomainWeightStore):
        store.save_weight("low", 0.5, domain_type="technical")
        store.save_weight("high", 2.0, domain_type="technical")
        store.save_weight("med", 1.0, domain_type="technical")
        stats = store.get_statistics()
        top_tech = stats["top_technical"]
        assert len(top_tech) == 3
        assert top_tech[0]["domain"] == "high"
        assert top_tech[0]["weight"] == 2.0

    # -- Persistence file location ------------------------------------------

    def test_creates_directory_structure(self, tmp_path: Path):
        store = DomainWeightStore(tmp_path)
        store.save_weight("test", 1.0, domain_type="technical")
        expected_dir = tmp_path / ".tapps-mcp" / "adaptive"
        assert expected_dir.exists()

    def test_yaml_file_created(self, tmp_path: Path):
        store = DomainWeightStore(tmp_path)
        store.save_weight("test", 1.0, domain_type="technical")
        yaml_file = tmp_path / ".tapps-mcp" / "adaptive" / "domain_weights.yaml"
        # Either YAML or JSON fallback should exist
        json_file = tmp_path / ".tapps-mcp" / "adaptive" / "domain_weights.json"
        assert yaml_file.exists() or json_file.exists()

    # -- Backward compatibility / migration ---------------------------------

    def test_loads_legacy_json_fallback(self, tmp_path: Path):
        """Test backward compatibility with JSON format."""
        store_dir = tmp_path / ".tapps-mcp" / "adaptive"
        store_dir.mkdir(parents=True, exist_ok=True)
        json_file = store_dir / "domain_weights.json"
        json_file.write_text(
            json.dumps(
                {
                    "technical": {"security": {"weight": 1.3, "samples": 5}},
                    "business": {},
                    "version": 1,
                }
            )
        )
        store = DomainWeightStore(tmp_path)
        snapshot = store.load_weights()
        assert "security" in snapshot.technical
        assert snapshot.technical["security"].weight == 1.3

    def test_overwrites_on_update(self, store: DomainWeightStore):
        store.save_weight("security", 1.0, samples=5, domain_type="technical")
        store.save_weight("security", 1.5, samples=10, domain_type="technical")
        entry = store.get_weight("security", domain_type="technical")
        assert entry is not None
        assert entry.weight == 1.5
        assert entry.samples == 10


class TestDomainWeightEntry:
    """Tests for DomainWeightEntry model."""

    def test_default_values(self):
        entry = DomainWeightEntry(domain="test")
        assert entry.weight == 1.0
        assert entry.samples == 0
        assert entry.positive_count == 0
        assert entry.negative_count == 0
        assert entry.last_updated is not None

    def test_custom_values(self):
        entry = DomainWeightEntry(
            domain="security",
            weight=1.5,
            samples=10,
            positive_count=8,
            negative_count=2,
        )
        assert entry.domain == "security"
        assert entry.weight == 1.5
        assert entry.samples == 10
        assert entry.positive_count == 8
        assert entry.negative_count == 2

    def test_weight_validation(self):
        # Weight must be >= 0
        with pytest.raises(ValueError):
            DomainWeightEntry(domain="test", weight=-1.0)


class TestDomainWeightsSnapshot:
    """Tests for DomainWeightsSnapshot model."""

    def test_empty_snapshot(self):
        snapshot = DomainWeightsSnapshot()
        assert snapshot.technical == {}
        assert snapshot.business == {}
        assert snapshot.version == 1
        assert snapshot.timestamp is not None

    def test_populated_snapshot(self):
        tech_entry = DomainWeightEntry(domain="security", weight=1.2)
        biz_entry = DomainWeightEntry(domain="acme", weight=1.5)
        snapshot = DomainWeightsSnapshot(
            technical={"security": tech_entry},
            business={"acme": biz_entry},
        )
        assert len(snapshot.technical) == 1
        assert len(snapshot.business) == 1
        assert snapshot.technical["security"].weight == 1.2
        assert snapshot.business["acme"].weight == 1.5
