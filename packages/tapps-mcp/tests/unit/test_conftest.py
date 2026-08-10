"""Tests for the shared test doubles defined in packages/tapps-mcp/tests/conftest.py.

``InMemoryPrivateBackend`` stands in for Postgres in ~6,700 unit tests (ADR-007),
so a defect in it makes the whole suite lie — a search that silently matches
nothing, or an audit filter that drops rows, reads as "the code under test is
broken". It had no direct coverage until TAP-5733.

conftest.py is loaded here by path rather than imported as a module: pytest owns
the real import, and ``--import-mode=importlib`` plus the three packages'
identically named ``tests`` trees (TAP-4575) make ``import conftest`` ambiguous.
Same loader pattern as test_tool_budget_lint.py.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from types import ModuleType

CONFTEST_PATH = Path(__file__).resolve().parents[1] / "conftest.py"


@pytest.fixture(scope="module")
def shared() -> ModuleType:
    """Load tests/conftest.py by path, without disturbing pytest's own copy."""
    spec = importlib.util.spec_from_file_location("tapps_mcp_tests_conftest", CONFTEST_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["tapps_mcp_tests_conftest"] = module
    spec.loader.exec_module(module)
    return module


class _Entry:
    """Minimal stand-in for a tapps-brain MemoryEntry."""

    def __init__(self, key: str, value: str, created_at: str = "2026-01-01T00:00:00+00:00") -> None:
        self.key = key
        self.value = value
        self.created_at = created_at


class TestSearchTokens:
    def test_lowercases_and_splits_on_punctuation(self, shared: ModuleType) -> None:
        assert shared._search_tokens("Latest MCP-Changes!") == {"latest", "mcp", "changes"}

    def test_empty_string_yields_no_tokens(self, shared: ModuleType) -> None:
        assert shared._search_tokens("") == set()

    def test_digits_are_tokens(self, shared: ModuleType) -> None:
        assert "5733" in shared._search_tokens("TAP-5733")


class TestEntryMatches:
    def test_matches_on_value(self, shared: ModuleType) -> None:
        entry = _Entry("unrelated-key", "the quick brown fox")
        assert shared._entry_matches(entry, {"brown"})

    def test_matches_on_key_with_dashes_split(self, shared: ModuleType) -> None:
        entry = _Entry("brain-bridge-health", "value")
        assert shared._entry_matches(entry, {"bridge"})

    def test_no_shared_token_does_not_match(self, shared: ModuleType) -> None:
        entry = _Entry("some-key", "some value")
        assert not shared._entry_matches(entry, {"absent"})


class TestFilterByCreatedAt:
    def test_since_is_inclusive(self, shared: ModuleType) -> None:
        entries = [_Entry("a", "v", "2026-01-02"), _Entry("b", "v", "2026-01-01")]
        kept = shared._filter_by_created_at(entries, since="2026-01-02", until=None)
        assert [e.key for e in kept] == ["a"]

    def test_until_is_inclusive(self, shared: ModuleType) -> None:
        entries = [_Entry("a", "v", "2026-01-02"), _Entry("b", "v", "2026-01-01")]
        kept = shared._filter_by_created_at(entries, since=None, until="2026-01-01")
        assert [e.key for e in kept] == ["b"]

    def test_no_bounds_returns_everything(self, shared: ModuleType) -> None:
        entries = [_Entry("a", "v"), _Entry("b", "v")]
        assert shared._filter_by_created_at(entries, since=None, until=None) == entries


class TestAuditRow:
    def test_event_type_falls_back_to_action(self, shared: ModuleType) -> None:
        row = shared._audit_row({"action": "save", "key": "k", "timestamp": "t"})
        assert row["event_type"] == "save"

    def test_explicit_event_type_wins_over_action(self, shared: ModuleType) -> None:
        row = shared._audit_row({"action": "save", "event_type": "gc", "key": "k"})
        assert row["event_type"] == "gc"

    def test_extra_keys_become_details(self, shared: ModuleType) -> None:
        row = shared._audit_row({"action": "save", "key": "k", "tier": "pattern"})
        assert row["details"] == {"tier": "pattern"}

    def test_missing_fields_default_to_empty_strings(self, shared: ModuleType) -> None:
        row = shared._audit_row({})
        assert row == {"timestamp": "", "event_type": "", "key": "", "details": {}}


class TestAuditRowMatches:
    @pytest.fixture
    def row(self, shared: ModuleType) -> dict[str, Any]:
        return shared._audit_row(
            {"action": "save", "key": "k1", "timestamp": "2026-01-02T00:00:00"}
        )

    def test_no_filters_matches(self, shared: ModuleType, row: dict[str, Any]) -> None:
        assert shared._audit_row_matches(row, key=None, event_type=None, since=None, until=None)

    def test_key_mismatch_rejects(self, shared: ModuleType, row: dict[str, Any]) -> None:
        assert not shared._audit_row_matches(
            row, key="other", event_type=None, since=None, until=None
        )

    def test_event_type_mismatch_rejects(self, shared: ModuleType, row: dict[str, Any]) -> None:
        assert not shared._audit_row_matches(row, key=None, event_type="gc", since=None, until=None)

    def test_since_after_timestamp_rejects(self, shared: ModuleType, row: dict[str, Any]) -> None:
        assert not shared._audit_row_matches(
            row, key=None, event_type=None, since="2026-02-01", until=None
        )

    def test_until_before_timestamp_rejects(self, shared: ModuleType, row: dict[str, Any]) -> None:
        assert not shared._audit_row_matches(
            row, key=None, event_type=None, since=None, until="2026-01-01"
        )

    def test_all_filters_satisfied_matches(self, shared: ModuleType, row: dict[str, Any]) -> None:
        assert shared._audit_row_matches(
            row, key="k1", event_type="save", since="2026-01-01", until="2026-01-03"
        )


class TestInMemoryPrivateBackend:
    @pytest.fixture
    def backend(self, shared: ModuleType) -> Any:
        instance = shared.InMemoryPrivateBackend()
        yield instance
        instance.close()

    def test_save_then_load_all(self, backend: Any) -> None:
        backend.save(_Entry("k1", "hello world"))
        assert [e.key for e in backend.load_all()] == ["k1"]

    def test_load_all_respects_limit(self, backend: Any) -> None:
        for i in range(5):
            backend.save(_Entry(f"k{i}", "v"))
        assert len(backend.load_all(limit=2)) == 2

    def test_delete_reports_whether_key_existed(self, backend: Any) -> None:
        backend.save(_Entry("k1", "v"))
        assert backend.delete("k1") is True
        assert backend.delete("k1") is False

    def test_search_finds_by_value_token(self, backend: Any) -> None:
        backend.save(_Entry("k1", "the quick brown fox"))
        assert [e.key for e in backend.search("brown")] == ["k1"]

    def test_search_blank_query_returns_nothing(self, backend: Any) -> None:
        backend.save(_Entry("k1", "anything"))
        assert backend.search("   ") == []

    def test_search_applies_since_filter(self, backend: Any) -> None:
        backend.save(_Entry("old", "shared token", "2026-01-01"))
        backend.save(_Entry("new", "shared token", "2026-06-01"))
        found = backend.search("shared", since="2026-03-01")
        assert [e.key for e in found] == ["new"]

    def test_audit_roundtrip_through_query(self, backend: Any) -> None:
        backend.append_audit("save", "k1", {"tier": "pattern"})
        rows = backend.query_audit()
        assert len(rows) == 1
        assert rows[0]["event_type"] == "save"
        assert rows[0]["details"]["tier"] == "pattern"

    def test_query_audit_filters_by_key(self, backend: Any) -> None:
        backend.append_audit("save", "k1")
        backend.append_audit("save", "k2")
        assert [r["key"] for r in backend.query_audit(key="k2")] == ["k2"]

    def test_query_audit_respects_limit(self, backend: Any) -> None:
        for i in range(5):
            backend.append_audit("save", f"k{i}")
        assert len(backend.query_audit(limit=2)) == 2

    def test_query_audit_skips_malformed_lines(self, backend: Any) -> None:
        backend.append_audit("save", "k1")
        with backend.audit_path.open("a", encoding="utf-8") as fh:
            fh.write("not json\n\n")
        assert [r["key"] for r in backend.query_audit()] == ["k1"]

    def test_query_audit_on_missing_file_returns_empty(self, backend: Any) -> None:
        backend.audit_path.unlink()
        assert backend.query_audit() == []

    def test_relations_save_load_and_delete(self, backend: Any) -> None:
        rel = type("R", (), {"subject": "a", "predicate": "uses", "object_entity": "b"})()
        assert backend.save_relations("k1", [rel]) == 1
        assert backend.count_relations() == 1
        assert len(backend.load_relations("k1")) == 1
        assert backend.delete_relations("k1") == 1
        assert backend.count_relations() == 0

    def test_archive_entry_tracks_byte_total(self, backend: Any) -> None:
        entry = type("E", (), {"key": "k1", "model_dump": lambda self: {"key": "k1"}})()
        written = backend.archive_entry(entry)
        assert written > 0
        assert backend.total_archive_bytes() == written
        assert [row["key"] for row in backend.list_archive()] == ["k1"]

    def test_flywheel_meta_roundtrip(self, backend: Any) -> None:
        assert backend.flywheel_meta_get("absent") is None
        backend.flywheel_meta_set("k", "v")
        assert backend.flywheel_meta_get("k") == "v"

    def test_close_is_idempotent(self, backend: Any) -> None:
        """The teardown fixture calls close() after the test; a double close must
        not raise, which is what let the bandit B110 wrapper be removed."""
        backend.close()
        backend.close()

    def test_audit_file_is_json_lines(self, backend: Any) -> None:
        backend.append_audit("save", "k1")
        line = backend.audit_path.read_text(encoding="utf-8").strip()
        assert json.loads(line)["key"] == "k1"
