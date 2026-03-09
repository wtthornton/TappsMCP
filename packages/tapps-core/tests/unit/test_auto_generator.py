"""Tests for tapps_core.experts.auto_generator — auto-expert generation from codebase analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tapps_core.experts.auto_generator import (
    AutoGenerateResult,
    ExpertSuggestion,
    _BUILTIN_DOMAIN,
    _DOMAIN_METADATA,
    _FRAMEWORK_DOMAIN_MAP,
    _merge_into_experts_yaml,
    analyze_expert_gaps,
    auto_generate_experts,
    generate_expert_configs,
    scaffold_expert_with_knowledge,
)
from tapps_core.experts.business_config import (
    BusinessExpertEntry,
    BusinessExpertsConfig,
)
from tapps_core.experts.registry import ExpertRegistry


@pytest.fixture(autouse=True)
def _clear_business_experts() -> None:
    """Clear business experts before each test for isolation."""
    ExpertRegistry.clear_business_experts()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _write_experts_yaml(tmp_path: Path, data: dict[str, Any]) -> Path:
    """Write experts.yaml into .tapps-mcp/ under tmp_path."""
    config_dir = tmp_path / ".tapps-mcp"
    config_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = config_dir / "experts.yaml"
    yaml_path.write_text(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return yaml_path


# ===========================================================================
# analyze_expert_gaps
# ===========================================================================


class TestAnalyzeExpertGaps:
    """Tests for analyze_expert_gaps()."""

    def test_empty_inputs_produce_no_suggestions(self) -> None:
        result = analyze_expert_gaps(libraries=[], frameworks=[], domains=[])
        assert result == []

    def test_builtin_covered_domains_are_skipped(self) -> None:
        result = analyze_expert_gaps(
            libraries=["fastapi", "django", "pytest"],
            frameworks=[],
            domains=[],
        )
        assert result == []

    def test_all_builtin_libraries_skipped(self) -> None:
        builtin_libs = [
            lib for lib, domain in _FRAMEWORK_DOMAIN_MAP.items()
            if domain == _BUILTIN_DOMAIN
        ]
        result = analyze_expert_gaps(
            libraries=builtin_libs, frameworks=[], domains=[],
        )
        assert result == []

    def test_uncovered_domain_produces_suggestion(self) -> None:
        result = analyze_expert_gaps(
            libraries=["celery"], frameworks=[], domains=[],
        )
        assert len(result) == 1
        assert result[0].domain == "task-queue"
        assert result[0].expert_name == "Task Queue Expert"
        assert "celery" in result[0].detected_libraries

    def test_already_registered_business_domain_skipped(self) -> None:
        # Register a business expert for task-queue
        from tapps_core.experts.models import ExpertConfig

        ExpertRegistry.register_business_experts([
            ExpertConfig(
                expert_id="expert-tq",
                expert_name="TQ",
                primary_domain="task-queue",
                description="",
                keywords=[],
                rag_enabled=False,
                knowledge_dir=None,
                is_builtin=False,
            ),
        ])
        result = analyze_expert_gaps(
            libraries=["celery"], frameworks=[], domains=[],
        )
        assert result == []

    def test_multiple_libraries_same_domain(self) -> None:
        result = analyze_expert_gaps(
            libraries=["celery", "dramatiq", "huey"],
            frameworks=[],
            domains=[],
        )
        assert len(result) == 1
        assert result[0].domain == "task-queue"
        assert set(result[0].detected_libraries) == {"celery", "dramatiq", "huey"}

    def test_confidence_increases_with_more_libraries(self) -> None:
        single = analyze_expert_gaps(
            libraries=["celery"], frameworks=[], domains=[],
        )
        multiple = analyze_expert_gaps(
            libraries=["celery", "dramatiq", "huey"],
            frameworks=[],
            domains=[],
        )
        assert multiple[0].confidence > single[0].confidence

    def test_confidence_formula_one_lib(self) -> None:
        result = analyze_expert_gaps(
            libraries=["stripe"], frameworks=[], domains=[],
        )
        # confidence = min(1.0, 1 * 0.3 + 0.2) = 0.5
        assert result[0].confidence == pytest.approx(0.5)

    def test_confidence_formula_two_libs(self) -> None:
        result = analyze_expert_gaps(
            libraries=["stripe", "paypal"], frameworks=[], domains=[],
        )
        # confidence = min(1.0, 2 * 0.3 + 0.2) = 0.8
        assert result[0].confidence == pytest.approx(0.8)

    def test_confidence_capped_at_one(self) -> None:
        result = analyze_expert_gaps(
            libraries=["stripe", "paypal", "braintree", "square"],
            frameworks=[],
            domains=[],
        )
        # confidence = min(1.0, 4 * 0.3 + 0.2) = min(1.0, 1.4) = 1.0
        assert result[0].confidence == pytest.approx(1.0)

    def test_multiple_domains_detected(self) -> None:
        result = analyze_expert_gaps(
            libraries=["celery", "stripe", "redis"],
            frameworks=[],
            domains=[],
        )
        domains = {s.domain for s in result}
        assert "task-queue" in domains
        assert "payments" in domains
        assert "caching" in domains

    def test_suggestions_sorted_by_confidence_descending(self) -> None:
        result = analyze_expert_gaps(
            libraries=["celery", "stripe", "paypal"],
            frameworks=[],
            domains=[],
        )
        # payments: 2 libs (0.8), task-queue: 1 lib (0.5)
        assert result[0].domain == "payments"
        assert result[1].domain == "task-queue"

    def test_frameworks_input_also_matched(self) -> None:
        result = analyze_expert_gaps(
            libraries=[], frameworks=["celery"], domains=[],
        )
        assert len(result) == 1
        assert result[0].domain == "task-queue"

    def test_library_name_normalization(self) -> None:
        # Underscore -> hyphen normalization
        result = analyze_expert_gaps(
            libraries=["confluent_kafka"], frameworks=[], domains=[],
        )
        assert len(result) == 1
        assert result[0].domain == "message-broker"

    def test_keywords_include_detected_library_and_domain_words(self) -> None:
        result = analyze_expert_gaps(
            libraries=["stripe"], frameworks=[], domains=[],
        )
        assert "stripe" in result[0].keywords
        assert "payments" in result[0].keywords

    def test_structural_pattern_detection_model_files(self, tmp_path: Path) -> None:
        # Create a .pt model file
        (tmp_path / "model.pt").write_text("", encoding="utf-8")
        result = analyze_expert_gaps(
            libraries=[], frameworks=[], domains=[], project_root=tmp_path,
        )
        assert len(result) == 1
        assert result[0].domain == "ml-ops"

    def test_structural_pattern_detection_model_dir(self, tmp_path: Path) -> None:
        (tmp_path / "models").mkdir()
        result = analyze_expert_gaps(
            libraries=[], frameworks=[], domains=[], project_root=tmp_path,
        )
        assert len(result) == 1
        assert result[0].domain == "ml-ops"

    def test_structural_pattern_no_match(self, tmp_path: Path) -> None:
        result = analyze_expert_gaps(
            libraries=[], frameworks=[], domains=[], project_root=tmp_path,
        )
        assert result == []

    def test_unknown_library_ignored(self) -> None:
        result = analyze_expert_gaps(
            libraries=["some_unknown_lib"], frameworks=[], domains=[],
        )
        assert result == []

    def test_rationale_includes_library_names(self) -> None:
        result = analyze_expert_gaps(
            libraries=["celery"], frameworks=[], domains=[],
        )
        assert "celery" in result[0].rationale


# ===========================================================================
# generate_expert_configs
# ===========================================================================


class TestGenerateExpertConfigs:
    """Tests for generate_expert_configs()."""

    def test_generates_valid_business_expert_entries(self) -> None:
        suggestions = [
            ExpertSuggestion(
                domain="task-queue",
                expert_name="Task Queue Expert",
                description="Background jobs.",
                keywords=["celery", "task", "queue"],
                confidence=0.5,
            ),
        ]
        configs = generate_expert_configs(suggestions)
        assert len(configs) == 1
        assert isinstance(configs[0], BusinessExpertEntry)
        assert configs[0].expert_id == "expert-task-queue"
        assert configs[0].expert_name == "Task Queue Expert"

    def test_max_experts_limit_respected(self) -> None:
        suggestions = [
            ExpertSuggestion(
                domain=f"domain-{i}",
                expert_name=f"Expert {i}",
                description=f"Desc {i}",
            )
            for i in range(10)
        ]
        configs = generate_expert_configs(suggestions, max_experts=3)
        assert len(configs) == 3

    def test_global_20_expert_limit_respected(self) -> None:
        from tapps_core.experts.models import ExpertConfig

        # Register 18 business experts
        ExpertRegistry.register_business_experts([
            ExpertConfig(
                expert_id=f"expert-existing-{i}",
                expert_name=f"Existing {i}",
                primary_domain=f"existing-{i}",
                description="",
                keywords=[],
                rag_enabled=False,
                knowledge_dir=None,
                is_builtin=False,
            )
            for i in range(18)
        ])
        suggestions = [
            ExpertSuggestion(
                domain=f"new-domain-{i}",
                expert_name=f"New Expert {i}",
                description=f"Desc {i}",
            )
            for i in range(5)
        ]
        configs = generate_expert_configs(suggestions, max_experts=5)
        # 20 - 18 = 2 available slots
        assert len(configs) == 2

    def test_at_20_limit_returns_empty(self) -> None:
        from tapps_core.experts.models import ExpertConfig

        ExpertRegistry.register_business_experts([
            ExpertConfig(
                expert_id=f"expert-full-{i}",
                expert_name=f"Full {i}",
                primary_domain=f"full-{i}",
                description="",
                keywords=[],
                rag_enabled=False,
                knowledge_dir=None,
                is_builtin=False,
            )
            for i in range(BusinessExpertsConfig._MAX_EXPERTS)
        ])
        suggestions = [
            ExpertSuggestion(domain="extra", expert_name="Extra", description=""),
        ]
        configs = generate_expert_configs(suggestions)
        assert configs == []

    def test_keywords_include_detected_libraries(self) -> None:
        suggestions = [
            ExpertSuggestion(
                domain="payments",
                expert_name="Payments Expert",
                description="Payments.",
                keywords=["stripe", "paypal", "payments"],
            ),
        ]
        configs = generate_expert_configs(suggestions)
        assert "stripe" in configs[0].keywords
        assert "paypal" in configs[0].keywords

    def test_empty_suggestions_returns_empty(self) -> None:
        configs = generate_expert_configs([])
        assert configs == []

    def test_rag_enabled_by_default(self) -> None:
        suggestions = [
            ExpertSuggestion(
                domain="caching",
                expert_name="Caching Expert",
                description="Cache.",
            ),
        ]
        configs = generate_expert_configs(suggestions)
        assert configs[0].rag_enabled is True


# ===========================================================================
# scaffold_expert_with_knowledge
# ===========================================================================


class TestScaffoldExpertWithKnowledge:
    """Tests for scaffold_expert_with_knowledge()."""

    def _make_entry(self, domain: str = "task-queue") -> BusinessExpertEntry:
        return BusinessExpertEntry(
            expert_id=f"expert-{domain}",
            expert_name=f"{domain.replace('-', ' ').title()} Expert",
            primary_domain=domain,
            description=f"Expert for {domain}.",
        )

    def test_creates_overview_and_best_practices(self, tmp_path: Path) -> None:
        entry = self._make_entry("task-queue")
        knowledge_path = scaffold_expert_with_knowledge(tmp_path, entry)
        assert (knowledge_path / "README.md").exists()
        assert (knowledge_path / "best-practices.md").exists()

    def test_idempotency_does_not_overwrite(self, tmp_path: Path) -> None:
        entry = self._make_entry("payments")
        # First run
        knowledge_path = scaffold_expert_with_knowledge(tmp_path, entry)
        bp_path = knowledge_path / "best-practices.md"
        original_content = bp_path.read_text(encoding="utf-8")
        # Modify the file
        bp_path.write_text("custom content", encoding="utf-8")
        # Second run should not overwrite
        scaffold_expert_with_knowledge(tmp_path, entry)
        assert bp_path.read_text(encoding="utf-8") == "custom content"

    def test_best_practices_includes_detected_libraries(self, tmp_path: Path) -> None:
        entry = self._make_entry("payments")
        scaffold_expert_with_knowledge(
            tmp_path, entry, detected_libraries=["stripe", "paypal"],
        )
        knowledge_path = tmp_path / ".tapps-mcp" / "knowledge" / "payments"
        bp_content = (knowledge_path / "best-practices.md").read_text(encoding="utf-8")
        assert "stripe" in bp_content
        assert "paypal" in bp_content

    def test_best_practices_has_domain_key_concepts(self, tmp_path: Path) -> None:
        entry = self._make_entry("caching")
        knowledge_path = scaffold_expert_with_knowledge(tmp_path, entry)
        bp_content = (knowledge_path / "best-practices.md").read_text(encoding="utf-8")
        assert "Cache-aside" in bp_content or "cache" in bp_content.lower()

    def test_best_practices_excludes_structural_pattern_from_libs(
        self, tmp_path: Path,
    ) -> None:
        entry = self._make_entry("ml-ops")
        knowledge_path = scaffold_expert_with_knowledge(
            tmp_path, entry, detected_libraries=["structural-pattern"],
        )
        bp_content = (knowledge_path / "best-practices.md").read_text(encoding="utf-8")
        assert "structural-pattern" not in bp_content

    def test_returns_knowledge_path(self, tmp_path: Path) -> None:
        entry = self._make_entry("graphql-api")
        knowledge_path = scaffold_expert_with_knowledge(tmp_path, entry)
        assert knowledge_path.is_dir()
        assert "graphql-api" in str(knowledge_path)


# ===========================================================================
# auto_generate_experts (full orchestration)
# ===========================================================================


class TestAutoGenerateExperts:
    """Tests for auto_generate_experts() orchestrator."""

    def test_dry_run_returns_suggestions_without_writing(self, tmp_path: Path) -> None:
        result = auto_generate_experts(
            project_root=tmp_path,
            libraries=["celery", "stripe"],
            frameworks=[],
            domains=[],
            dry_run=True,
        )
        assert len(result.suggestions) >= 2
        assert result.generated == []
        assert result.scaffolded == []
        # No files written
        assert not (tmp_path / ".tapps-mcp" / "experts.yaml").exists()

    def test_live_mode_writes_experts_yaml(self, tmp_path: Path) -> None:
        result = auto_generate_experts(
            project_root=tmp_path,
            libraries=["celery"],
            frameworks=[],
            domains=[],
            dry_run=False,
        )
        assert len(result.generated) == 1
        yaml_path = tmp_path / ".tapps-mcp" / "experts.yaml"
        assert yaml_path.exists()
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert len(data["experts"]) == 1
        assert data["experts"][0]["expert_id"] == "expert-task-queue"

    def test_live_mode_scaffolds_knowledge(self, tmp_path: Path) -> None:
        result = auto_generate_experts(
            project_root=tmp_path,
            libraries=["celery"],
            frameworks=[],
            domains=[],
            dry_run=False,
            include_knowledge=True,
        )
        assert len(result.scaffolded) == 1
        knowledge_path = Path(result.scaffolded[0])
        assert knowledge_path.is_dir()
        assert (knowledge_path / "best-practices.md").exists()

    def test_live_mode_no_knowledge_scaffolding(self, tmp_path: Path) -> None:
        result = auto_generate_experts(
            project_root=tmp_path,
            libraries=["celery"],
            frameworks=[],
            domains=[],
            dry_run=False,
            include_knowledge=False,
        )
        assert result.scaffolded == []
        assert len(result.generated) == 1

    def test_no_suggestions_produces_empty_result(self, tmp_path: Path) -> None:
        result = auto_generate_experts(
            project_root=tmp_path,
            libraries=[],
            frameworks=[],
            domains=[],
            dry_run=False,
        )
        assert result.suggestions == []
        assert result.generated == []

    def test_max_experts_limits_generation(self, tmp_path: Path) -> None:
        result = auto_generate_experts(
            project_root=tmp_path,
            libraries=["celery", "stripe", "redis", "elasticsearch", "grpcio"],
            frameworks=[],
            domains=[],
            max_experts=2,
            dry_run=False,
        )
        assert len(result.generated) == 2

    def test_skipped_builtin_populated(self, tmp_path: Path) -> None:
        result = auto_generate_experts(
            project_root=tmp_path,
            libraries=["fastapi"],
            frameworks=[],
            domains=[],
            dry_run=True,
        )
        assert len(result.skipped_builtin) > 0

    def test_result_dataclass_defaults(self) -> None:
        r = AutoGenerateResult()
        assert r.suggestions == []
        assert r.generated == []
        assert r.scaffolded == []
        assert r.skipped_builtin == []
        assert r.skipped_existing == []


# ===========================================================================
# _merge_into_experts_yaml
# ===========================================================================


class TestMergeIntoExpertsYaml:
    """Tests for _merge_into_experts_yaml()."""

    def test_creates_new_file(self, tmp_path: Path) -> None:
        entry = BusinessExpertEntry(
            expert_id="expert-new",
            expert_name="New Expert",
            primary_domain="new-domain",
        )
        _merge_into_experts_yaml(tmp_path, [entry])
        yaml_path = tmp_path / ".tapps-mcp" / "experts.yaml"
        assert yaml_path.exists()
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert len(data["experts"]) == 1

    def test_preserves_existing_entries(self, tmp_path: Path) -> None:
        _write_experts_yaml(tmp_path, {
            "experts": [
                {
                    "expert_id": "expert-existing",
                    "expert_name": "Existing",
                    "primary_domain": "existing-domain",
                },
            ],
        })
        new_entry = BusinessExpertEntry(
            expert_id="expert-added",
            expert_name="Added Expert",
            primary_domain="added-domain",
        )
        _merge_into_experts_yaml(tmp_path, [new_entry])
        yaml_path = tmp_path / ".tapps-mcp" / "experts.yaml"
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert len(data["experts"]) == 2
        ids = {e["expert_id"] for e in data["experts"]}
        assert "expert-existing" in ids
        assert "expert-added" in ids

    def test_skips_duplicate_expert_ids(self, tmp_path: Path) -> None:
        _write_experts_yaml(tmp_path, {
            "experts": [
                {
                    "expert_id": "expert-dup",
                    "expert_name": "Original",
                    "primary_domain": "dup-domain",
                },
            ],
        })
        dup_entry = BusinessExpertEntry(
            expert_id="expert-dup",
            expert_name="Duplicate",
            primary_domain="dup-domain",
        )
        _merge_into_experts_yaml(tmp_path, [dup_entry])
        yaml_path = tmp_path / ".tapps-mcp" / "experts.yaml"
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert len(data["experts"]) == 1
        assert data["experts"][0]["expert_name"] == "Original"


# ===========================================================================
# ExpertSuggestion dataclass
# ===========================================================================


class TestExpertSuggestion:
    """Tests for the ExpertSuggestion dataclass."""

    def test_defaults(self) -> None:
        s = ExpertSuggestion(
            domain="test",
            expert_name="Test Expert",
            description="Test.",
        )
        assert s.keywords == []
        assert s.confidence == 0.5
        assert s.rationale == ""
        assert s.detected_libraries == []

    def test_full_construction(self) -> None:
        s = ExpertSuggestion(
            domain="payments",
            expert_name="Payments Expert",
            description="Payments processing.",
            keywords=["stripe", "payments"],
            confidence=0.8,
            rationale="Detected stripe",
            detected_libraries=["stripe"],
        )
        assert s.domain == "payments"
        assert s.confidence == 0.8


# ===========================================================================
# Domain metadata coverage
# ===========================================================================


class TestDomainMetadata:
    """Verify all mappable domains have metadata."""

    def test_all_non_builtin_domains_have_metadata(self) -> None:
        non_builtin_domains = {
            domain for domain in _FRAMEWORK_DOMAIN_MAP.values()
            if domain != _BUILTIN_DOMAIN
        }
        for domain in non_builtin_domains:
            assert domain in _DOMAIN_METADATA, f"Missing metadata for domain: {domain}"
