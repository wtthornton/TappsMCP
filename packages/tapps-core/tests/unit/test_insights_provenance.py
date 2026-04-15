"""Tests for tapps_core.insights.provenance (STORY-102.6)."""

from __future__ import annotations

from tapps_core.insights.models import InsightEntry, InsightOrigin, InsightType
from tapps_core.insights.provenance import (
    ProvenanceAnnotation,
    annotate_provenance,
    format_provenance_summary,
)


def _insight(**kwargs: object) -> InsightEntry:
    return InsightEntry(
        key=kwargs.pop("key", "test.insight.one"),  # type: ignore[arg-type]
        value=kwargs.pop("value", "Some insight value"),  # type: ignore[arg-type]
        insight_type=kwargs.pop("insight_type", InsightType.architecture),  # type: ignore[arg-type]
        server_origin=kwargs.pop("server_origin", InsightOrigin.docs_mcp),  # type: ignore[arg-type]
        **kwargs,
    )


class TestProvenanceAnnotation:
    def test_default_is_local(self):
        a = ProvenanceAnnotation(key="test.key")
        assert a.recalled_from == "local"
        assert a.is_federated is False

    def test_federated_flag(self):
        a = ProvenanceAnnotation(key="test.key", recalled_from="tapps-brain:other", is_federated=True)
        assert a.is_federated is True

    def test_summary_line_local(self):
        a = ProvenanceAnnotation(
            key="arch.proj.structure",
            origin_server=InsightOrigin.docs_mcp,
            recalled_from="local",
            is_federated=False,
        )
        line = a.summary_line()
        assert "arch.proj.structure" in line
        assert "this project" in line
        assert "docs-mcp" in line

    def test_summary_line_federated(self):
        a = ProvenanceAnnotation(
            key="arch.other.pkg",
            origin_server=InsightOrigin.tapps_mcp,
            recalled_from="tapps-brain:other-project",
            is_federated=True,
        )
        line = a.summary_line()
        assert "tapps-brain:other-project" in line


class TestAnnotateProvenance:
    def test_empty_list(self):
        assert annotate_provenance([]) == []

    def test_single_entry_local(self):
        entries = [_insight(key="test.single")]
        result = annotate_provenance(entries)
        assert len(result) == 1
        assert "_provenance" in result[0]

    def test_provenance_key_matches_entry_key(self):
        entries = [_insight(key="arch.myproject.structure")]
        result = annotate_provenance(entries)
        assert result[0]["_provenance"]["key"] == "arch.myproject.structure"

    def test_local_source_not_federated(self):
        entries = [_insight()]
        result = annotate_provenance(entries, federation_source="local")
        assert result[0]["_provenance"]["is_federated"] is False
        assert result[0]["_provenance"]["recalled_from"] == "local"

    def test_federation_source_marked(self):
        entries = [_insight()]
        result = annotate_provenance(entries, federation_source="tapps-brain:proj-b")
        prov = result[0]["_provenance"]
        assert prov["is_federated"] is True
        assert prov["recalled_from"] == "tapps-brain:proj-b"

    def test_origin_server_preserved(self):
        entries = [_insight(server_origin=InsightOrigin.tapps_mcp)]
        result = annotate_provenance(entries)
        assert result[0]["_provenance"]["origin_server"] == "tapps-mcp"

    def test_entry_data_preserved(self):
        entries = [_insight(key="test.data.preserved", value="check this value")]
        result = annotate_provenance(entries)
        assert result[0]["value"] == "check this value"
        assert result[0]["key"] == "test.data.preserved"

    def test_multiple_entries(self):
        entries = [_insight(key=f"test.multi.{i}") for i in range(3)]
        result = annotate_provenance(entries)
        assert len(result) == 3
        keys = [r["_provenance"]["key"] for r in result]
        assert "test.multi.0" in keys
        assert "test.multi.2" in keys

    def test_origin_project_set(self):
        entries = [_insight()]
        result = annotate_provenance(entries, origin_project="my-service")
        assert result[0]["_provenance"]["origin_project"] == "my-service"


class TestFormatProvenanceSummary:
    def test_empty_returns_empty_string(self):
        assert format_provenance_summary([]) == ""

    def test_contains_header(self):
        entries = [_insight(key="test.fmt")]
        annotated = annotate_provenance(entries)
        summary = format_provenance_summary(annotated)
        assert "Recalled insight provenance" in summary

    def test_contains_entry_key(self):
        entries = [_insight(key="arch.proj.structure")]
        annotated = annotate_provenance(entries)
        summary = format_provenance_summary(annotated)
        assert "arch.proj.structure" in summary

    def test_local_shows_this_project(self):
        entries = [_insight(key="test.local")]
        annotated = annotate_provenance(entries, federation_source="local")
        summary = format_provenance_summary(annotated)
        assert "this project" in summary

    def test_federated_shows_remote_source(self):
        entries = [_insight(key="test.fed")]
        annotated = annotate_provenance(entries, federation_source="tapps-brain:remote")
        summary = format_provenance_summary(annotated)
        assert "tapps-brain:remote" in summary

    def test_multiple_entries_in_summary(self):
        entries = [_insight(key=f"test.summary.{i}") for i in range(3)]
        annotated = annotate_provenance(entries)
        summary = format_provenance_summary(annotated)
        assert summary.count("- [") == 3
