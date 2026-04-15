"""Tests for tapps_core.insights.models — InsightEntry schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tapps_core.insights.models import (
    INSIGHT_SCHEMA_VERSION,
    InsightEntry,
    InsightOrigin,
    InsightType,
    SubjectKind,
)


class TestInsightSchemaSentinel:
    def test_schema_version_is_int(self):
        assert isinstance(INSIGHT_SCHEMA_VERSION, int)

    def test_schema_version_is_one(self):
        assert INSIGHT_SCHEMA_VERSION == 1


class TestInsightType:
    def test_all_values_are_strings(self):
        for member in InsightType:
            assert isinstance(member.value, str)

    def test_quality_member(self):
        assert InsightType.quality == "quality"

    def test_architecture_member(self):
        assert InsightType.architecture == "architecture"

    def test_security_member(self):
        assert InsightType.security == "security"

    def test_documentation_member(self):
        assert InsightType.documentation == "documentation"

    def test_pattern_member(self):
        assert InsightType.pattern == "pattern"

    def test_dependency_member(self):
        assert InsightType.dependency == "dependency"


class TestInsightOrigin:
    def test_tapps_mcp_value(self):
        assert InsightOrigin.tapps_mcp == "tapps-mcp"

    def test_docs_mcp_value(self):
        assert InsightOrigin.docs_mcp == "docs-mcp"

    def test_user_value(self):
        assert InsightOrigin.user == "user"

    def test_unknown_value(self):
        assert InsightOrigin.unknown == "unknown"


class TestSubjectKind:
    def test_all_members_present(self):
        members = {m.value for m in SubjectKind}
        assert {"file", "module", "class", "function", "system"} == members

    def test_klass_maps_to_class_string(self):
        assert SubjectKind.klass == "class"


class TestInsightEntryDefaults:
    def test_create_minimal(self):
        e = InsightEntry(key="test.insight.one", value="something meaningful")
        assert e.insight_type == InsightType.quality
        assert e.server_origin == InsightOrigin.unknown
        assert e.schema_version == 1
        assert e.subject_path == ""
        assert e.subject_kind == SubjectKind.system

    def test_schema_version_is_always_one(self):
        e = InsightEntry(key="test.v", value="val")
        assert e.schema_version == 1

    def test_inherits_memory_entry_key_validation(self):
        with pytest.raises(ValidationError):
            InsightEntry(key="UPPER_CASE", value="val")

    def test_inherits_memory_entry_value_validation(self):
        with pytest.raises(ValidationError):
            InsightEntry(key="test.empty", value="   ")


class TestInsightEntryCustomFields:
    def test_insight_type_architecture(self):
        e = InsightEntry(
            key="arch.fact.one",
            value="tapps-core is a shim over tapps-brain",
            insight_type=InsightType.architecture,
        )
        assert e.insight_type == InsightType.architecture

    def test_server_origin_docs_mcp(self):
        e = InsightEntry(
            key="docs.fact.one",
            value="README is comprehensive",
            server_origin=InsightOrigin.docs_mcp,
        )
        assert e.server_origin == InsightOrigin.docs_mcp

    def test_subject_path_stored(self):
        path = "packages/tapps-core/src/tapps_core/memory/__init__.py"
        e = InsightEntry(key="test.path", value="some insight", subject_path=path)
        assert e.subject_path == path

    def test_subject_kind_file(self):
        e = InsightEntry(key="test.file", value="val", subject_kind=SubjectKind.file)
        assert e.subject_kind == SubjectKind.file

    def test_full_construction(self):
        e = InsightEntry(
            key="security.scan.finding.001",
            value="Hardcoded API key detected in config.py",
            insight_type=InsightType.security,
            server_origin=InsightOrigin.tapps_mcp,
            subject_path="packages/tapps-mcp/src/tapps_mcp/config.py",
            subject_kind=SubjectKind.file,
            tags=["security", "api-key"],
        )
        assert e.insight_type == InsightType.security
        assert e.server_origin == InsightOrigin.tapps_mcp
        assert e.subject_kind == SubjectKind.file
        assert len(e.tags) == 2

    def test_is_subclass_of_memory_entry(self):
        from tapps_brain.models import MemoryEntry

        e = InsightEntry(key="test.sub", value="val")
        assert isinstance(e, MemoryEntry)

    def test_roundtrip_serialization(self):
        e = InsightEntry(
            key="test.roundtrip",
            value="roundtrip value",
            insight_type=InsightType.pattern,
            server_origin=InsightOrigin.docs_mcp,
            subject_path="src/main.py",
            subject_kind=SubjectKind.file,
        )
        dumped = e.model_dump()
        restored = InsightEntry.model_validate(dumped)
        assert restored.insight_type == InsightType.pattern
        assert restored.server_origin == InsightOrigin.docs_mcp
        assert restored.subject_path == "src/main.py"
        assert restored.subject_kind == SubjectKind.file
        assert restored.schema_version == 1
