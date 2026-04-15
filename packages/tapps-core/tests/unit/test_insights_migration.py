"""Tests for tapps_core.insights.migration — migrate_memory_entry_to_insight, bulk_migrate."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from tapps_brain.models import MemoryEntry, MemoryScope, MemorySource, MemoryTier

from tapps_core.insights import (
    InsightMigrationResult,
    InsightOrigin,
    InsightType,
    SubjectKind,
    bulk_migrate,
    migrate_memory_entry_to_insight,
)
from tapps_core.insights.migration import _infer_insight_type, _infer_subject_kind
from tapps_core.insights.models import InsightEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(key: str = "test.entry", tags: list[str] | None = None) -> MemoryEntry:
    return MemoryEntry(
        key=key,
        value="A test memory entry value",
        tags=tags or [],
        tier=MemoryTier.pattern,
        source=MemorySource.agent,
        scope=MemoryScope.project,
    )


# ---------------------------------------------------------------------------
# _infer_insight_type
# ---------------------------------------------------------------------------

class TestInferInsightType:
    def test_architecture_tag(self):
        e = _make_entry(tags=["architecture"])
        assert _infer_insight_type(e) == InsightType.architecture

    def test_arch_shorthand_tag(self):
        e = _make_entry(tags=["arch"])
        assert _infer_insight_type(e) == InsightType.architecture

    def test_design_tag(self):
        e = _make_entry(tags=["design"])
        assert _infer_insight_type(e) == InsightType.architecture

    def test_docs_tag(self):
        e = _make_entry(tags=["docs"])
        assert _infer_insight_type(e) == InsightType.documentation

    def test_security_tag(self):
        e = _make_entry(tags=["security"])
        assert _infer_insight_type(e) == InsightType.security

    def test_cve_tag(self):
        e = _make_entry(tags=["cve"])
        assert _infer_insight_type(e) == InsightType.security

    def test_pattern_tag(self):
        e = _make_entry(tags=["pattern"])
        assert _infer_insight_type(e) == InsightType.pattern

    def test_dependency_tag(self):
        e = _make_entry(tags=["dependency"])
        assert _infer_insight_type(e) == InsightType.dependency

    def test_dep_shorthand_tag(self):
        e = _make_entry(tags=["dep"])
        assert _infer_insight_type(e) == InsightType.dependency

    def test_quality_tag(self):
        e = _make_entry(tags=["quality"])
        assert _infer_insight_type(e) == InsightType.quality

    def test_unknown_tag_falls_back_to_quality(self):
        e = _make_entry(tags=["unrecognized-tag"])
        assert _infer_insight_type(e) == InsightType.quality

    def test_no_tags_falls_back_to_quality(self):
        e = _make_entry(tags=[])
        assert _infer_insight_type(e) == InsightType.quality

    def test_first_matching_tag_wins(self):
        # "architecture" is first → architecture, not dependency
        e = _make_entry(tags=["architecture", "dependency"])
        assert _infer_insight_type(e) == InsightType.architecture


# ---------------------------------------------------------------------------
# _infer_subject_kind
# ---------------------------------------------------------------------------

class TestInferSubjectKind:
    def test_empty_path_is_system(self):
        assert _infer_subject_kind("") == SubjectKind.system

    def test_py_file_is_file(self):
        assert _infer_subject_kind("src/main.py") == SubjectKind.file

    def test_dotted_path_is_module(self):
        assert _infer_subject_kind("tapps_core.memory") == SubjectKind.module

    def test_slash_path_without_py_is_module(self):
        assert _infer_subject_kind("packages/tapps-core/src") == SubjectKind.module

    def test_bare_name_is_system(self):
        assert _infer_subject_kind("tapps") == SubjectKind.system


# ---------------------------------------------------------------------------
# migrate_memory_entry_to_insight
# ---------------------------------------------------------------------------

class TestMigrateMemoryEntryToInsight:
    def test_returns_insight_entry(self):
        entry = _make_entry()
        result = migrate_memory_entry_to_insight(entry)
        assert isinstance(result, InsightEntry)

    def test_preserves_key(self):
        entry = _make_entry("my.custom.key")
        result = migrate_memory_entry_to_insight(entry)
        assert result.key == "my.custom.key"

    def test_preserves_value(self):
        entry = _make_entry()
        result = migrate_memory_entry_to_insight(entry)
        assert result.value == entry.value

    def test_preserves_tier(self):
        entry = _make_entry()
        entry = entry.model_copy(update={"tier": MemoryTier.architectural})
        result = migrate_memory_entry_to_insight(entry)
        assert result.tier == MemoryTier.architectural

    def test_preserves_tags(self):
        entry = _make_entry(tags=["quality", "score"])
        result = migrate_memory_entry_to_insight(entry)
        assert result.tags == ["quality", "score"]

    def test_schema_version_is_one(self):
        result = migrate_memory_entry_to_insight(_make_entry())
        assert result.schema_version == 1

    def test_default_origin_is_unknown(self):
        result = migrate_memory_entry_to_insight(_make_entry())
        assert result.server_origin == InsightOrigin.unknown

    def test_explicit_origin_applied(self):
        result = migrate_memory_entry_to_insight(
            _make_entry(), server_origin=InsightOrigin.docs_mcp
        )
        assert result.server_origin == InsightOrigin.docs_mcp

    def test_explicit_insight_type_applied(self):
        result = migrate_memory_entry_to_insight(
            _make_entry(), insight_type=InsightType.architecture
        )
        assert result.insight_type == InsightType.architecture

    def test_inferred_type_from_tag(self):
        entry = _make_entry(tags=["security"])
        result = migrate_memory_entry_to_insight(entry)
        assert result.insight_type == InsightType.security

    def test_explicit_type_overrides_tag(self):
        entry = _make_entry(tags=["security"])
        result = migrate_memory_entry_to_insight(entry, insight_type=InsightType.pattern)
        assert result.insight_type == InsightType.pattern

    def test_subject_path_applied(self):
        result = migrate_memory_entry_to_insight(
            _make_entry(), subject_path="src/foo.py"
        )
        assert result.subject_path == "src/foo.py"

    def test_subject_kind_inferred_from_path(self):
        result = migrate_memory_entry_to_insight(
            _make_entry(), subject_path="src/foo.py"
        )
        assert result.subject_kind == SubjectKind.file

    def test_explicit_subject_kind_overrides_inference(self):
        result = migrate_memory_entry_to_insight(
            _make_entry(),
            subject_path="src/foo.py",
            subject_kind=SubjectKind.function,
        )
        assert result.subject_kind == SubjectKind.function

    def test_idempotent_on_insight_entry(self):
        """Migrating an InsightEntry returns equivalent InsightEntry."""
        original = InsightEntry(
            key="test.idempotent",
            value="idempotent test",
            insight_type=InsightType.architecture,
            server_origin=InsightOrigin.docs_mcp,
            subject_path="src/x.py",
            subject_kind=SubjectKind.file,
        )
        result = migrate_memory_entry_to_insight(original)
        assert result.insight_type == InsightType.architecture
        assert result.server_origin == InsightOrigin.docs_mcp
        assert result.subject_path == "src/x.py"
        assert result.subject_kind == SubjectKind.file

    def test_idempotent_preserves_origin_when_not_overridden(self):
        original = InsightEntry(
            key="test.orig-preserve",
            value="origin check",
            server_origin=InsightOrigin.tapps_mcp,
        )
        result = migrate_memory_entry_to_insight(original)
        assert result.server_origin == InsightOrigin.tapps_mcp

    def test_override_origin_on_existing_insight(self):
        original = InsightEntry(
            key="test.override-orig",
            value="override test",
            server_origin=InsightOrigin.tapps_mcp,
        )
        result = migrate_memory_entry_to_insight(original, server_origin=InsightOrigin.user)
        assert result.server_origin == InsightOrigin.user


# ---------------------------------------------------------------------------
# bulk_migrate
# ---------------------------------------------------------------------------

class TestBulkMigrate:
    def test_returns_insight_migration_result(self):
        result = bulk_migrate([])
        assert isinstance(result, InsightMigrationResult)

    def test_empty_list(self):
        result = bulk_migrate([])
        assert result.total == 0
        assert result.success_count == 0
        assert result.failure_count == 0
        assert result.succeeded == []
        assert result.failed_keys == []

    def test_single_entry(self):
        result = bulk_migrate([_make_entry("single.key")])
        assert result.total == 1
        assert result.success_count == 1
        assert result.failure_count == 0
        assert len(result.succeeded) == 1
        assert result.succeeded[0].key == "single.key"

    def test_multiple_entries(self):
        entries = [_make_entry(f"entry.key.{i}") for i in range(5)]
        result = bulk_migrate(entries)
        assert result.total == 5
        assert result.success_count == 5
        assert result.failure_count == 0

    def test_server_origin_applied_to_all(self):
        entries = [_make_entry(f"orig.key.{i}") for i in range(3)]
        result = bulk_migrate(entries, server_origin=InsightOrigin.tapps_mcp)
        for insight in result.succeeded:
            assert insight.server_origin == InsightOrigin.tapps_mcp

    def test_subject_path_applied_to_plain_entries(self):
        entries = [_make_entry("path.test")]
        result = bulk_migrate(entries, subject_path="src/core.py")
        assert result.succeeded[0].subject_path == "src/core.py"

    def test_counts_are_accurate(self):
        entries = [_make_entry(f"count.{i}") for i in range(4)]
        result = bulk_migrate(entries)
        assert result.success_count + result.failure_count == result.total

    def test_all_succeeded_are_insight_entries(self):
        entries = [_make_entry(f"type.check.{i}") for i in range(3)]
        result = bulk_migrate(entries)
        for e in result.succeeded:
            assert isinstance(e, InsightEntry)

    def test_mixed_memory_and_insight_entries(self):
        """bulk_migrate handles a mix of MemoryEntry and InsightEntry."""
        plain = _make_entry("plain.key")
        already_insight = InsightEntry(
            key="already.insight",
            value="already promoted",
            insight_type=InsightType.architecture,
        )
        result = bulk_migrate([plain, already_insight])
        assert result.total == 2
        assert result.success_count == 2
        keys = {e.key for e in result.succeeded}
        assert "plain.key" in keys
        assert "already.insight" in keys
