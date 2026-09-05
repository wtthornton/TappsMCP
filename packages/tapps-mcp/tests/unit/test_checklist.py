"""Tests for tools.checklist — session call tracking and epic validation."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from tapps_mcp.tools.checklist import (
    TASK_TOOL_MAP,
    TASK_TOOL_MAP_HIGH,
    TASK_TOOL_MAP_LOW,
    CallTracker,
    ChecklistResult,
    ToolCallRecord,
)


class TestToolCallRecord:
    def test_creation(self):
        r = ToolCallRecord(tool_name="tapps_score_file")
        assert r.tool_name == "tapps_score_file"
        assert r.timestamp > 0


class TestTaskToolMap:
    def test_feature_task(self):
        m = TASK_TOOL_MAP["feature"]
        assert "tapps_score_file" in m["required"]
        assert "tapps_quality_gate" in m["required"]

    def test_bugfix_task(self):
        m = TASK_TOOL_MAP["bugfix"]
        assert "tapps_score_file" in m["required"]

    def test_refactor_task(self):
        m = TASK_TOOL_MAP["refactor"]
        assert "tapps_score_file" in m["required"]
        assert "tapps_quality_gate" in m["required"]
        assert "tapps_call_graph" in m["recommended"]
        assert "tapps_diff_impact" in m["recommended"]

    def test_security_task(self):
        m = TASK_TOOL_MAP["security"]
        assert "tapps_security_scan" in m["required"]
        assert "tapps_quality_gate" in m["required"]

    def test_review_task(self):
        m = TASK_TOOL_MAP["review"]
        assert "tapps_score_file" in m["required"]
        assert "tapps_security_scan" in m["required"]
        assert "tapps_quality_gate" in m["required"]

    def test_all_task_types_present(self):
        expected = {
            "feature",
            "bugfix",
            "refactor",
            "security",
            "review",
            "epic",
            "release",
            "document",
            # ADR-0025 task types (qa / documentation / frontend).
            "documentation",
            "qa",
            "frontend",
        }
        assert set(TASK_TOOL_MAP.keys()) == expected

    def test_retired_tapps_memory_not_in_any_bucket(self) -> None:
        """TAP-1994: tapps_memory MCP removed — checklist must not recommend it."""
        for level_name, level_map in (
            ("medium", TASK_TOOL_MAP),
            ("high", TASK_TOOL_MAP_HIGH),
            ("low", TASK_TOOL_MAP_LOW),
        ):
            for task_type, spec in level_map.items():
                for bucket in ("required", "recommended", "optional"):
                    tools = spec.get(bucket, [])
                    assert "tapps_memory" not in tools, (
                        f"tapps_memory still in {level_name}/{task_type}/{bucket}"
                    )

    def test_document_task(self):
        m = TASK_TOOL_MAP["document"]
        assert "tapps_validate_changed" in m["required"]
        assert "tapps_validate_config" in m["recommended"]

    def test_document_task_type_resolves_without_fallback(self):
        from tapps_mcp.tools.checklist import TASK_TYPE_REASONS, CallTracker

        CallTracker.reset()
        result = CallTracker.evaluate("document", engagement_level="medium")
        assert result.resolved_policy_task_type == "document"
        assert result.policy_fallback is False
        assert result.task_type_hint == TASK_TYPE_REASONS["document"]

    def test_epic_task(self):
        m = TASK_TOOL_MAP["epic"]
        assert "tapps_checklist" in m["required"]


class TestCallTracker:
    # Tests in this class assert against the medium TASK_TOOL_MAP. They were
    # written before the high/low maps existed and historically read engagement
    # from `load_settings().llm_engagement_level`. That coupling is order-
    # dependent on CI — sibling tests that monkeypatch TAPPS_MCP_LLM_ENGAGEMENT_LEVEL
    # or call tapps_set_engagement_level() can leak HIGH/LOW into the cached
    # settings. Pass engagement_level="medium" explicitly via the helper below
    # so these assertions are independent of global state.

    @staticmethod
    def _evaluate(task_type, **kwargs):
        return CallTracker.evaluate(task_type, engagement_level="medium", **kwargs)

    def setup_method(self):
        CallTracker.reset()

    def test_record_and_get(self):
        CallTracker.record("tapps_score_file")
        assert "tapps_score_file" in CallTracker.get_called_tools()

    def test_total_calls(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        assert CallTracker.total_calls() == 3

    def test_unique_tools(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_score_file")
        called = CallTracker.get_called_tools()
        assert called == {"tapps_score_file"}

    def test_reset(self):
        CallTracker.record("tapps_score_file")
        CallTracker.reset()
        assert CallTracker.get_called_tools() == set()
        assert CallTracker.total_calls() == 0

    def test_evaluate_complete(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        result = self._evaluate("feature")
        assert result.complete is True
        assert result.missing_required == []
        assert result.task_type == "feature"

    def test_evaluate_incomplete(self):
        result = self._evaluate("feature")
        assert result.complete is False
        assert "tapps_score_file" in result.missing_required
        assert "tapps_quality_gate" in result.missing_required

    def test_evaluate_partial(self):
        CallTracker.record("tapps_score_file")
        result = self._evaluate("feature")
        assert result.complete is False
        assert "tapps_quality_gate" in result.missing_required
        assert "tapps_score_file" not in result.missing_required

    def test_evaluate_unknown_task_defaults_to_review(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_security_scan")
        CallTracker.record("tapps_quality_gate")
        result = self._evaluate("unknown_task")
        assert result.task_type == "unknown_task"
        assert result.complete is True
        assert result.policy_fallback is True
        assert result.resolved_policy_task_type == "review"

    def test_evaluate_unknown_task_strict_raises(self):
        with pytest.raises(ValueError, match="Unknown task_type"):
            self._evaluate(
                "not_a_real_task",
                strict_unknown_task_type=True,
            )

    def test_begin_session_adopts_pre_session_calls(self):
        """Calls recorded before begin_session (empty session_id) are kept.

        Agents sometimes invoke tools before ``tapps_session_start``; dropping
        those records caused checklist false negatives.
        """
        CallTracker.record("tapps_score_file")
        CallTracker.begin_session()
        CallTracker.record("tapps_quality_gate")
        r = self._evaluate("feature")
        assert "tapps_score_file" in r.called
        assert "tapps_quality_gate" in r.called

    def test_begin_session_isolates_prior_session_calls(self):
        """Calls from a previous checklist session stay filtered out."""
        CallTracker.begin_session("sess-a")
        CallTracker.record("tapps_score_file")
        CallTracker.begin_session("sess-b")
        CallTracker.record("tapps_quality_gate")
        r = self._evaluate("feature")
        assert "tapps_score_file" not in r.called
        assert "tapps_quality_gate" in r.called

    def test_evaluate_includes_recommended(self):
        result = self._evaluate("feature")
        assert "tapps_security_scan" in result.missing_recommended

    def test_evaluate_includes_optional(self):
        result = self._evaluate("feature")
        assert "tapps_checklist" in result.missing_optional

    def test_evaluate_total_calls(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        result = self._evaluate("feature")
        assert result.total_calls == 2

    def test_evaluate_called_sorted(self):
        CallTracker.record("tapps_quality_gate")
        CallTracker.record("tapps_score_file")
        result = self._evaluate("feature")
        assert result.called == ["tapps_quality_gate", "tapps_score_file"]

    def test_evaluate_engagement_high_feature_requires_more(self):
        """High engagement: feature requires score, gate, security_scan."""
        result = CallTracker.evaluate("feature", engagement_level="high")
        assert "tapps_security_scan" in result.missing_required
        assert "tapps_score_file" in result.missing_required
        assert "tapps_quality_gate" in result.missing_required

    def test_evaluate_engagement_high_feature_complete_with_all(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        CallTracker.record("tapps_security_scan")
        result = CallTracker.evaluate("feature", engagement_level="high")
        assert result.complete is True
        assert result.missing_required == []

    def test_evaluate_engagement_low_feature_requires_less(self):
        """Low engagement: feature only requires quality_gate."""
        result = CallTracker.evaluate("feature", engagement_level="low")
        assert "tapps_quality_gate" in result.missing_required
        assert "tapps_score_file" in result.missing_recommended

    def test_evaluate_engagement_low_feature_complete_with_gate_only(self):
        CallTracker.record("tapps_quality_gate")
        result = CallTracker.evaluate("feature", engagement_level="low")
        assert result.complete is True

    def test_engagement_maps_exist(self):
        assert set(TASK_TOOL_MAP_HIGH.keys()) == set(TASK_TOOL_MAP.keys())
        assert set(TASK_TOOL_MAP_LOW.keys()) == set(TASK_TOOL_MAP.keys())
        assert "tapps_security_scan" in TASK_TOOL_MAP_HIGH["feature"]["required"]
        assert "tapps_security_scan" not in TASK_TOOL_MAP_LOW["feature"]["required"]


class TestCrossProcessChecklistCredit:
    """TAP-6738: a sibling MCP process (nlt-release-ship, nlt-linear-issues,
    ...) that binds the shared ledger before any session marker exists must
    not be stranded forever once a session starts elsewhere.

    ``CallTracker`` is a process-wide singleton (all state lives on the
    class), so two real bindings sharing one ledger file are simulated the
    same way the TAP-6586 regression suite does it: clear the class state
    and re-``set_persist_path`` onto the same on-disk ledger, standing in for
    a fresh OS process picking up where the files left off.
    """

    @pytest.fixture(autouse=True)
    def _ledger(self, tmp_path: Path) -> Iterator[Path]:
        CallTracker.reset()
        path = tmp_path / "state" / "checklist_calls.jsonl"
        CallTracker.set_persist_path(path)
        yield path
        CallTracker.reset()
        CallTracker._persist_path = None
        CallTracker._calls.clear()

    @staticmethod
    def _rebind(path: Path) -> None:
        """Simulate a fresh process binding the same project ledger."""
        CallTracker._calls.clear()
        CallTracker._window_id = None
        CallTracker._active_session_id = None
        CallTracker._adopted_window_ids = frozenset()
        CallTracker.set_persist_path(path)

    def test_sibling_process_window_is_adopted_once_a_session_starts(
        self, _ledger: Path
    ) -> None:
        """Second binding records under no marker; first binding's later
        begin_session must retroactively adopt that orphan window so its
        row is credited.
        """
        self._rebind(_ledger)
        CallTracker.record("tapps_lookup_docs")
        sibling_window = CallTracker._window_id
        assert sibling_window is not None

        self._rebind(_ledger)
        CallTracker.begin_session("sess-a")

        assert sibling_window in CallTracker._adopted_window_ids
        result = CallTracker.evaluate("feature", engagement_level="medium")
        assert "tapps_lookup_docs" in result.called

    def test_prior_unrelated_session_still_does_not_leak(self, _ledger: Path) -> None:
        """A genuinely different, already-claimed session must not be picked
        up by the orphan scan (TAP-6586 stays fixed).
        """
        self._rebind(_ledger)
        CallTracker.begin_session("sess-old")
        CallTracker.record("tapps_score_file")

        self._rebind(_ledger)
        CallTracker.begin_session("sess-new")

        result = CallTracker.evaluate("feature", engagement_level="medium")
        assert result.total_calls == 0
        assert "tapps_score_file" not in result.called

    def test_migration_ledger_with_no_registry_adopts_nothing(self, _ledger: Path) -> None:
        """TAP-6738 round 2 (verifier refutation): the claimed-ids registry is
        introduced BY this feature, so it is absent on every existing install.
        A ledger already holding rows from many old, real session ids (written
        by a version of the server that predates the registry) must not have
        every one of those ids look "unclaimed" and get swept in wholesale by
        the very first ``begin_session`` after upgrading — that is the exact
        TAP-6586 false-green class, reopened via a migration path the
        existing sibling-window tests never exercise (they always begin a
        session under the new code first, which populates the registry).
        """
        old_timestamp = time.time() - (2 * CallTracker._ORPHAN_ADOPTION_WINDOW_SECONDS)
        _ledger.parent.mkdir(parents=True, exist_ok=True)
        with _ledger.open("w", encoding="utf-8") as fh:
            for sid in ("hist-a", "hist-b", "hist-c"):
                record = ToolCallRecord(
                    tool_name="tapps_score_file", timestamp=old_timestamp, session_id=sid
                )
                fh.write(
                    json.dumps(
                        {
                            "tool_name": record.tool_name,
                            "timestamp": record.timestamp,
                            "session_id": record.session_id,
                            "success": record.success,
                        }
                    )
                    + "\n"
                )

        assert not (_ledger.parent / "checklist_claimed_ids").exists()

        self._rebind(_ledger)
        CallTracker.begin_session("new-after-upgrade")

        assert CallTracker._adopted_window_ids == frozenset()
        result = CallTracker.evaluate("feature", engagement_level="medium")
        assert result.total_calls == 0
        assert result.called == []
        assert result.missing_required != []

    def test_seed_claimed_ids_at_first_creation(self, _ledger: Path) -> None:
        """TAP-6814: the round-2 recency window alone still adopted a
        pre-existing id if its newest row happened to be RECENT — e.g. two
        sibling sessions (sessA, sessB) both wrote within the adoption window
        just before the very first begin_session() ran on an existing
        install. Live probe: with no claimed_ids file and sessA/sessB in the
        adoption window, first begin_session() adopted both. The registry
        must instead be seeded with every distinct id already in the ledger
        at first creation, so the first begin_session() adopts nothing.
        """
        recent_timestamp = time.time() - 30.0
        _ledger.parent.mkdir(parents=True, exist_ok=True)
        with _ledger.open("w", encoding="utf-8") as fh:
            for sid in ("sessA", "sessB"):
                record = ToolCallRecord(
                    tool_name="tapps_score_file", timestamp=recent_timestamp, session_id=sid
                )
                fh.write(
                    json.dumps(
                        {
                            "tool_name": record.tool_name,
                            "timestamp": record.timestamp,
                            "session_id": record.session_id,
                            "success": record.success,
                        }
                    )
                    + "\n"
                )

        registry_path = _ledger.parent / "checklist_claimed_ids"
        assert not registry_path.exists()

        self._rebind(_ledger)
        CallTracker.begin_session("new-session")

        assert CallTracker._adopted_window_ids == frozenset()
        result = CallTracker.evaluate("feature", engagement_level="medium")
        assert result.total_calls == 0
        assert result.complete is False

        # The registry now exists and was seeded with the pre-existing ids
        # (plus the new session id), so a later begin_session on the same
        # ledger would still adopt nothing from this history.
        assert registry_path.exists()
        seeded = frozenset(
            ln.strip() for ln in registry_path.read_text(encoding="utf-8").splitlines() if ln.strip()
        )
        assert {"sessA", "sessB"} <= seeded

    def test_sibling_adoption_still_works_once_registry_exists(self, _ledger: Path) -> None:
        """Negative control / regression guard: seeding must only fire on
        first creation. Once the registry already exists (pre-created here,
        so this run's begin_session sees ``registry_is_new is False``), a
        genuine cross-process sibling window must still be adopted (TAP-6738)
        exactly as before this fix."""
        registry_path = _ledger.parent / "checklist_claimed_ids"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text("", encoding="utf-8")

        self._rebind(_ledger)
        CallTracker.record("tapps_lookup_docs")
        sibling_window = CallTracker._window_id
        assert sibling_window is not None

        self._rebind(_ledger)
        CallTracker.begin_session("sess-1")

        assert sibling_window in CallTracker._adopted_window_ids
        result = CallTracker.evaluate("feature", engagement_level="medium")
        assert "tapps_lookup_docs" in result.called

    def test_marker_named_prior_session_is_not_adopted_as_orphan(self, _ledger: Path) -> None:
        """TAP-6738 round 3 (verifier refutation): on an upgrade boundary the
        PRIOR session's rows are typically minutes old, well inside
        ``_ORPHAN_ADOPTION_WINDOW_SECONDS`` -- the round-2 recency bound alone
        does not exclude them. The marker's line-1 id is always a real prior
        session, never a sibling window id, so it must never be swept up by
        the orphan scan even though it is absent from the (not-yet-existing)
        claimed-ids registry.
        """
        recent_timestamp = time.time() - 60.0
        _ledger.parent.mkdir(parents=True, exist_ok=True)
        with _ledger.open("w", encoding="utf-8") as fh:
            for _ in range(3):
                record = ToolCallRecord(
                    tool_name="tapps_score_file",
                    timestamp=recent_timestamp,
                    session_id="prior-sess",
                )
                fh.write(
                    json.dumps(
                        {
                            "tool_name": record.tool_name,
                            "timestamp": record.timestamp,
                            "session_id": record.session_id,
                            "success": record.success,
                        }
                    )
                    + "\n"
                )
        (_ledger.parent / "checklist_active_session").write_text(
            "prior-sess\n", encoding="utf-8"
        )

        assert not (_ledger.parent / "checklist_claimed_ids").exists()

        self._rebind(_ledger)
        assert CallTracker._active_session_id == "prior-sess"
        CallTracker.begin_session("new-after-prior")

        assert "prior-sess" not in CallTracker._adopted_window_ids
        result = CallTracker.evaluate("feature", engagement_level="medium")
        assert result.total_calls == 0
        assert result.complete is False


class TestChecklistResult:
    def test_creation(self):
        r = ChecklistResult(task_type="feature", complete=True, total_calls=5)
        assert r.task_type == "feature"
        assert r.complete is True
        assert r.total_calls == 5
        assert r.called == []
        assert r.missing_required == []
