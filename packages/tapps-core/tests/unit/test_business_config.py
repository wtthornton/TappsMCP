"""Tests for tapps_core.experts.business_config — YAML schema and loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_core.experts.business_config import (
    BusinessExpertEntry,
    BusinessExpertsConfig,
    _MAX_BUSINESS_EXPERTS,
    load_business_experts,
)


def _write_yaml(tmp_path: Path, content: str) -> Path:
    """Write experts.yaml into .tapps-mcp/ under tmp_path."""
    config_dir = tmp_path / ".tapps-mcp"
    config_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = config_dir / "experts.yaml"
    yaml_path.write_text(content, encoding="utf-8")
    return yaml_path


# --- Happy path tests ---


class TestLoadBusinessExperts:
    """Tests for load_business_experts()."""

    def test_valid_yaml_single_expert(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path,
            """\
experts:
  - expert_id: "expert-billing"
    expert_name: "Billing Expert"
    primary_domain: "billing"
""",
        )
        result = load_business_experts(tmp_path)
        assert len(result) == 1
        assert result[0].expert_id == "expert-billing"
        assert result[0].expert_name == "Billing Expert"
        assert result[0].primary_domain == "billing"

    def test_valid_yaml_three_experts(self, tmp_path: Path) -> None:
        experts_yaml = "experts:\n"
        for i in range(3):
            experts_yaml += f"""\
  - expert_id: "expert-biz-{i}"
    expert_name: "Biz Expert {i}"
    primary_domain: "domain-{i}"
"""
        _write_yaml(tmp_path, experts_yaml)
        result = load_business_experts(tmp_path)
        assert len(result) == 3

    def test_valid_yaml_at_cap(self, tmp_path: Path) -> None:
        experts_yaml = "experts:\n"
        for i in range(_MAX_BUSINESS_EXPERTS):
            experts_yaml += f"""\
  - expert_id: "expert-cap-{i}"
    expert_name: "Cap Expert {i}"
    primary_domain: "domain-{i}"
"""
        _write_yaml(tmp_path, experts_yaml)
        result = load_business_experts(tmp_path)
        assert len(result) == _MAX_BUSINESS_EXPERTS

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = load_business_experts(tmp_path)
        assert result == []

    def test_empty_experts_list(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "experts: []\n")
        result = load_business_experts(tmp_path)
        assert result == []

    def test_keywords_valid(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path,
            """\
experts:
  - expert_id: "expert-kw"
    expert_name: "KW Expert"
    primary_domain: "kw-domain"
    keywords: ["billing", "invoice", "payment"]
""",
        )
        result = load_business_experts(tmp_path)
        assert result[0].keywords == ["billing", "invoice", "payment"]

    def test_knowledge_dir_override(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path,
            """\
experts:
  - expert_id: "expert-custom"
    expert_name: "Custom Expert"
    primary_domain: "custom"
    knowledge_dir: "my-knowledge"
""",
        )
        result = load_business_experts(tmp_path)
        assert result[0].knowledge_dir == "my-knowledge"

    def test_is_builtin_always_false(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path,
            """\
experts:
  - expert_id: "expert-notbuiltin"
    expert_name: "Not Builtin"
    primary_domain: "external"
""",
        )
        result = load_business_experts(tmp_path)
        assert result[0].is_builtin is False

    def test_description_defaults_empty(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path,
            """\
experts:
  - expert_id: "expert-nodesc"
    expert_name: "No Desc"
    primary_domain: "nodesc"
""",
        )
        result = load_business_experts(tmp_path)
        assert result[0].description == ""

    def test_rag_enabled_defaults_true(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path,
            """\
experts:
  - expert_id: "expert-rag"
    expert_name: "RAG Expert"
    primary_domain: "rag-domain"
""",
        )
        result = load_business_experts(tmp_path)
        assert result[0].rag_enabled is True

    def test_rag_enabled_false(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path,
            """\
experts:
  - expert_id: "expert-norag"
    expert_name: "No RAG"
    primary_domain: "norag"
    rag_enabled: false
""",
        )
        result = load_business_experts(tmp_path)
        assert result[0].rag_enabled is False


# --- Error path tests ---


class TestLoadBusinessExpertsErrors:
    """Tests for validation and error handling."""

    def test_invalid_yaml_not_a_dict(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "- item1\n- item2\n")
        with pytest.raises(ValueError, match="Expected a mapping"):
            load_business_experts(tmp_path)

    def test_malformed_yaml_syntax(self, tmp_path: Path) -> None:
        _write_yaml(tmp_path, "experts:\n  - expert_id: [\n")
        with pytest.raises(ValueError, match="Malformed YAML"):
            load_business_experts(tmp_path)

    def test_expert_id_without_prefix(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path,
            """\
experts:
  - expert_id: "billing"
    expert_name: "Billing"
    primary_domain: "billing"
""",
        )
        with pytest.raises(ValueError, match="expert_id must start with 'expert-'"):
            load_business_experts(tmp_path)

    def test_duplicate_expert_ids(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path,
            """\
experts:
  - expert_id: "expert-dup"
    expert_name: "Dup 1"
    primary_domain: "d1"
  - expert_id: "expert-dup"
    expert_name: "Dup 2"
    primary_domain: "d2"
""",
        )
        with pytest.raises(ValueError, match="Duplicate expert_ids"):
            load_business_experts(tmp_path)

    def test_exceeding_max_experts(self, tmp_path: Path) -> None:
        experts_yaml = "experts:\n"
        for i in range(_MAX_BUSINESS_EXPERTS + 1):
            experts_yaml += f"""\
  - expert_id: "expert-over-{i}"
    expert_name: "Over Expert {i}"
    primary_domain: "domain-{i}"
"""
        _write_yaml(tmp_path, experts_yaml)
        with pytest.raises(ValueError, match="Too many business experts"):
            load_business_experts(tmp_path)

    def test_extra_fields_rejected(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path,
            """\
experts:
  - expert_id: "expert-extra"
    expert_name: "Extra"
    primary_domain: "extra"
    unknown_field: "boom"
""",
        )
        with pytest.raises(ValueError):
            load_business_experts(tmp_path)

    def test_missing_expert_name(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path,
            """\
experts:
  - expert_id: "expert-noname"
    primary_domain: "noname"
""",
        )
        with pytest.raises(ValueError):
            load_business_experts(tmp_path)

    def test_missing_primary_domain(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path,
            """\
experts:
  - expert_id: "expert-nodomain"
    expert_name: "No Domain"
""",
        )
        with pytest.raises(ValueError):
            load_business_experts(tmp_path)


# --- Pydantic model unit tests ---


class TestBusinessExpertEntry:
    """Direct model validation tests."""

    def test_valid_entry(self) -> None:
        entry = BusinessExpertEntry(
            expert_id="expert-test",
            expert_name="Test",
            primary_domain="test-domain",
        )
        assert entry.expert_id == "expert-test"

    def test_keywords_too_many(self) -> None:
        with pytest.raises(ValueError, match="Too many keywords"):
            BusinessExpertEntry(
                expert_id="expert-kw",
                expert_name="KW",
                primary_domain="kw",
                keywords=["kw"] * 51,
            )


class TestBusinessExpertsConfig:
    """Root config model tests."""

    def test_empty_config(self) -> None:
        config = BusinessExpertsConfig()
        assert config.experts == []
