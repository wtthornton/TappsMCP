"""Unit tests for benchmark models and configuration (Epic 30, Story 1)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from tapps_mcp.benchmark.config import DEFAULT_CONFIG, load_benchmark_config
from tapps_mcp.benchmark.models import (
    BenchmarkConfig,
    BenchmarkInstance,
    BenchmarkResult,
    BenchmarkSummary,
    ComparisonReport,
    ContextMode,
    EngagementReport,
    RepoBreakdown,
    RunMetadata,
)

# ---------------------------------------------------------------------------
# ContextMode enum
# ---------------------------------------------------------------------------


class TestContextMode:
    """Tests for ContextMode enum."""

    def test_values(self) -> None:
        assert ContextMode.NONE == "none"
        assert ContextMode.TAPPS == "tapps"
        assert ContextMode.HUMAN == "human"
        assert ContextMode.ALL == "all"

    def test_member_count(self) -> None:
        assert len(ContextMode) == 4

    def test_from_string(self) -> None:
        assert ContextMode("none") is ContextMode.NONE
        assert ContextMode("tapps") is ContextMode.TAPPS


# ---------------------------------------------------------------------------
# BenchmarkInstance
# ---------------------------------------------------------------------------


class TestBenchmarkInstance:
    """Tests for BenchmarkInstance model."""

    def test_valid_creation(self) -> None:
        instance = BenchmarkInstance(
            instance_id="test-001",
            repo="owner/repo",
            problem_description="Fix the bug.",
            clean_pr_patch="--- a/file.py\n+++ b/file.py\n",
            test_commands=["pytest tests/"],
            test_file_names=["tests/test_foo.py"],
            test_file_contents={"tests/test_foo.py": "def test_foo(): pass"},
            docker_image="python:3.12",
        )
        assert instance.instance_id == "test-001"
        assert instance.repo == "owner/repo"
        assert instance.setup_commands == []
        assert instance.key_files == []
        assert instance.risk_factors is None
        assert instance.rationale is None

    def test_optional_fields(self) -> None:
        instance = BenchmarkInstance(
            instance_id="test-002",
            repo="owner/repo",
            problem_description="Fix it.",
            clean_pr_patch="diff",
            test_commands=["pytest"],
            test_file_names=["test.py"],
            test_file_contents={"test.py": "pass"},
            docker_image="python:3.12",
            risk_factors=["flaky tests"],
            rationale="Complex refactor needed.",
            setup_commands=["pip install -e ."],
            key_files=["src/main.py"],
        )
        assert instance.risk_factors == ["flaky tests"]
        assert instance.rationale == "Complex refactor needed."
        assert instance.setup_commands == ["pip install -e ."]
        assert instance.key_files == ["src/main.py"]

    def test_frozen(self) -> None:
        instance = BenchmarkInstance(
            instance_id="test-003",
            repo="owner/repo",
            problem_description="Bug.",
            clean_pr_patch="diff",
            test_commands=["pytest"],
            test_file_names=["test.py"],
            test_file_contents={"test.py": "pass"},
            docker_image="python:3.12",
        )
        with pytest.raises(ValidationError):
            instance.instance_id = "modified"  # type: ignore[misc]

    def test_serialization_roundtrip(self) -> None:
        instance = BenchmarkInstance(
            instance_id="rt-001",
            repo="owner/repo",
            problem_description="Roundtrip.",
            clean_pr_patch="diff",
            test_commands=["pytest"],
            test_file_names=["test.py"],
            test_file_contents={"test.py": "code"},
            docker_image="python:3.12",
            key_files=["main.py"],
        )
        data = instance.model_dump()
        restored = BenchmarkInstance.model_validate(data)
        assert restored == instance


# ---------------------------------------------------------------------------
# BenchmarkConfig
# ---------------------------------------------------------------------------


class TestBenchmarkConfig:
    """Tests for BenchmarkConfig model."""

    def test_defaults(self) -> None:
        config = BenchmarkConfig()
        assert config.dataset_name == "eth-sri/agentbench"
        assert config.context_mode is ContextMode.NONE
        assert config.engagement_level == "medium"
        assert config.subset_size == 20
        assert config.workers == 4
        assert config.output_dir == Path(".tapps-mcp/benchmark/")
        assert config.docker_timeout == 300
        assert config.random_seed == 42

    def test_invalid_subset_size(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            BenchmarkConfig(subset_size=-1)

    def test_invalid_workers(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            BenchmarkConfig(workers=0)

    def test_invalid_docker_timeout(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 30"):
            BenchmarkConfig(docker_timeout=10)

    def test_invalid_engagement_level(self) -> None:
        with pytest.raises(ValidationError, match="engagement_level"):
            BenchmarkConfig(engagement_level="ultra")

    def test_valid_engagement_levels(self) -> None:
        for level in ("high", "medium", "low"):
            config = BenchmarkConfig(engagement_level=level)
            assert config.engagement_level == level

    def test_serialization_roundtrip(self) -> None:
        config = BenchmarkConfig(
            context_mode=ContextMode.TAPPS,
            subset_size=50,
            workers=8,
        )
        data = config.model_dump()
        restored = BenchmarkConfig.model_validate(data)
        assert restored.context_mode is ContextMode.TAPPS
        assert restored.subset_size == 50
        assert restored.workers == 8

    def test_frozen(self) -> None:
        config = BenchmarkConfig()
        with pytest.raises(ValidationError):
            config.workers = 8  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BenchmarkResult
# ---------------------------------------------------------------------------


class TestBenchmarkResult:
    """Tests for BenchmarkResult model."""

    def test_minimal_creation(self) -> None:
        result = BenchmarkResult(
            instance_id="test-001",
            context_mode=ContextMode.NONE,
            engagement_level="medium",
            resolved=True,
        )
        assert result.resolved is True
        assert result.token_usage == 0
        assert result.inference_cost == 0.0
        assert result.steps == 0
        assert result.patch_size == 0
        assert result.error is None
        assert result.duration_ms == 0
        assert result.timestamp  # auto-generated

    def test_full_creation(self) -> None:
        result = BenchmarkResult(
            instance_id="test-002",
            context_mode=ContextMode.TAPPS,
            engagement_level="high",
            resolved=False,
            token_usage=15000,
            inference_cost=0.45,
            steps=12,
            patch_size=42,
            error="Docker timeout",
            duration_ms=300000,
        )
        assert result.token_usage == 15000
        assert result.error == "Docker timeout"

    def test_negative_token_usage_rejected(self) -> None:
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            BenchmarkResult(
                instance_id="bad",
                context_mode=ContextMode.NONE,
                engagement_level="medium",
                resolved=False,
                token_usage=-1,
            )

    def test_serialization_roundtrip(self) -> None:
        result = BenchmarkResult(
            instance_id="rt-001",
            context_mode=ContextMode.HUMAN,
            engagement_level="low",
            resolved=True,
            token_usage=5000,
        )
        data = result.model_dump()
        restored = BenchmarkResult.model_validate(data)
        assert restored.instance_id == result.instance_id
        assert restored.context_mode is ContextMode.HUMAN
        assert restored.token_usage == 5000


# ---------------------------------------------------------------------------
# RepoBreakdown
# ---------------------------------------------------------------------------


class TestRepoBreakdown:
    """Tests for RepoBreakdown model."""

    def test_resolution_rate(self) -> None:
        rb = RepoBreakdown(repo="owner/repo", total=10, resolved=7)
        assert rb.resolution_rate == pytest.approx(0.7)

    def test_resolution_rate_zero_total(self) -> None:
        rb = RepoBreakdown(repo="owner/repo", total=0, resolved=0)
        assert rb.resolution_rate == 0.0

    def test_resolution_rate_all_resolved(self) -> None:
        rb = RepoBreakdown(repo="owner/repo", total=5, resolved=5)
        assert rb.resolution_rate == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# BenchmarkSummary
# ---------------------------------------------------------------------------


class TestBenchmarkSummary:
    """Tests for BenchmarkSummary model."""

    def test_resolution_rate_computed(self) -> None:
        summary = BenchmarkSummary(
            total_instances=20,
            resolved_count=15,
            avg_tokens=10000.0,
            avg_cost=0.30,
            avg_steps=8.5,
            context_mode=ContextMode.TAPPS,
            engagement_level="medium",
        )
        assert summary.resolution_rate == pytest.approx(0.75)

    def test_resolution_rate_zero_instances(self) -> None:
        summary = BenchmarkSummary(
            total_instances=0,
            resolved_count=0,
            avg_tokens=0.0,
            avg_cost=0.0,
            avg_steps=0.0,
            context_mode=ContextMode.NONE,
            engagement_level="low",
        )
        assert summary.resolution_rate == 0.0

    def test_per_repo_breakdown(self) -> None:
        summary = BenchmarkSummary(
            total_instances=10,
            resolved_count=6,
            avg_tokens=8000.0,
            avg_cost=0.20,
            avg_steps=5.0,
            per_repo_breakdown={
                "org/a": RepoBreakdown(repo="org/a", total=5, resolved=3),
                "org/b": RepoBreakdown(repo="org/b", total=5, resolved=3),
            },
            context_mode=ContextMode.ALL,
            engagement_level="high",
        )
        assert len(summary.per_repo_breakdown) == 2
        assert summary.per_repo_breakdown["org/a"].resolution_rate == pytest.approx(0.6)

    def test_serialization_roundtrip(self) -> None:
        summary = BenchmarkSummary(
            total_instances=10,
            resolved_count=7,
            avg_tokens=5000.0,
            avg_cost=0.15,
            avg_steps=6.0,
            context_mode=ContextMode.TAPPS,
            engagement_level="medium",
        )
        data = summary.model_dump()
        restored = BenchmarkSummary.model_validate(data)
        assert restored.resolution_rate == pytest.approx(0.7)
        assert restored.context_mode is ContextMode.TAPPS


# ---------------------------------------------------------------------------
# ComparisonReport
# ---------------------------------------------------------------------------


class TestComparisonReport:
    """Tests for ComparisonReport model."""

    @pytest.fixture()
    def baseline_summary(self) -> BenchmarkSummary:
        return BenchmarkSummary(
            total_instances=20,
            resolved_count=10,
            avg_tokens=12000.0,
            avg_cost=0.36,
            avg_steps=10.0,
            context_mode=ContextMode.NONE,
            engagement_level="medium",
        )

    @pytest.fixture()
    def treatment_summary(self) -> BenchmarkSummary:
        return BenchmarkSummary(
            total_instances=20,
            resolved_count=14,
            avg_tokens=14000.0,
            avg_cost=0.42,
            avg_steps=8.0,
            context_mode=ContextMode.TAPPS,
            engagement_level="medium",
        )

    def test_delta_calculations(
        self,
        baseline_summary: BenchmarkSummary,
        treatment_summary: BenchmarkSummary,
    ) -> None:
        report = ComparisonReport(
            baseline=baseline_summary,
            treatment=treatment_summary,
            resolution_delta=0.2,
            token_delta=2000.0,
            cost_delta=0.06,
        )
        assert report.resolution_delta == pytest.approx(0.2)
        assert report.token_delta == pytest.approx(2000.0)
        assert report.cost_delta == pytest.approx(0.06)
        assert report.statistically_significant is None
        assert report.p_value is None

    def test_with_significance(
        self,
        baseline_summary: BenchmarkSummary,
        treatment_summary: BenchmarkSummary,
    ) -> None:
        report = ComparisonReport(
            baseline=baseline_summary,
            treatment=treatment_summary,
            resolution_delta=0.2,
            token_delta=2000.0,
            cost_delta=0.06,
            per_repo_deltas={"org/a": 0.15, "org/b": 0.25},
            statistically_significant=True,
            p_value=0.03,
        )
        assert report.statistically_significant is True
        assert report.p_value == pytest.approx(0.03)
        assert report.per_repo_deltas["org/a"] == pytest.approx(0.15)

    def test_serialization_roundtrip(
        self,
        baseline_summary: BenchmarkSummary,
        treatment_summary: BenchmarkSummary,
    ) -> None:
        report = ComparisonReport(
            baseline=baseline_summary,
            treatment=treatment_summary,
            resolution_delta=0.2,
            token_delta=2000.0,
            cost_delta=0.06,
        )
        data = report.model_dump()
        restored = ComparisonReport.model_validate(data)
        assert restored.resolution_delta == pytest.approx(0.2)
        assert restored.baseline.resolution_rate == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# RunMetadata
# ---------------------------------------------------------------------------


class TestRunMetadata:
    """Tests for RunMetadata model."""

    def test_creation(self) -> None:
        config = BenchmarkConfig(context_mode=ContextMode.TAPPS)
        meta = RunMetadata(
            run_id="run-001",
            config=config,
            instance_count=20,
            context_mode=ContextMode.TAPPS,
        )
        assert meta.run_id == "run-001"
        assert meta.instance_count == 20
        assert meta.context_mode is ContextMode.TAPPS
        assert meta.timestamp  # auto-generated

    def test_serialization_roundtrip(self) -> None:
        config = BenchmarkConfig()
        meta = RunMetadata(
            run_id="run-002",
            config=config,
            instance_count=10,
            context_mode=ContextMode.NONE,
        )
        data = meta.model_dump()
        restored = RunMetadata.model_validate(data)
        assert restored.run_id == "run-002"
        assert restored.config.dataset_name == "eth-sri/agentbench"


# ---------------------------------------------------------------------------
# EngagementReport
# ---------------------------------------------------------------------------


class TestEngagementReport:
    """Tests for EngagementReport model."""

    def _make_summary(
        self, level: str, mode: ContextMode, total: int, resolved: int
    ) -> BenchmarkSummary:
        return BenchmarkSummary(
            total_instances=total,
            resolved_count=resolved,
            avg_tokens=10000.0,
            avg_cost=0.30,
            avg_steps=8.0,
            context_mode=mode,
            engagement_level=level,
        )

    def test_creation(self) -> None:
        results = {
            "high": self._make_summary("high", ContextMode.TAPPS, 20, 16),
            "medium": self._make_summary("medium", ContextMode.TAPPS, 20, 14),
            "low": self._make_summary("low", ContextMode.TAPPS, 20, 12),
        }
        report = EngagementReport(
            results_by_level=results,
            recommended_level="high",
            recommendation_reason="Highest resolution rate.",
        )
        assert report.recommended_level == "high"
        assert report.recommendation_reason == "Highest resolution rate."
        assert len(report.results_by_level) == 3
        assert report.results_by_level["high"].resolution_rate == pytest.approx(0.8)

    def test_single_level(self) -> None:
        results = {
            "medium": self._make_summary("medium", ContextMode.NONE, 10, 5),
        }
        report = EngagementReport(
            results_by_level=results,
            recommended_level="medium",
            recommendation_reason="Only level tested.",
        )
        assert len(report.results_by_level) == 1

    def test_serialization_roundtrip(self) -> None:
        results = {
            "high": self._make_summary("high", ContextMode.ALL, 20, 18),
            "low": self._make_summary("low", ContextMode.ALL, 20, 10),
        }
        report = EngagementReport(
            results_by_level=results,
            recommended_level="high",
            recommendation_reason="Better resolution rate.",
        )
        data = report.model_dump()
        restored = EngagementReport.model_validate(data)
        assert restored.recommended_level == "high"
        assert restored.results_by_level["high"].resolution_rate == pytest.approx(0.9)
        assert restored.results_by_level["low"].resolution_rate == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


class TestLoadBenchmarkConfig:
    """Tests for load_benchmark_config."""

    def test_default_config_object(self) -> None:
        assert DEFAULT_CONFIG.dataset_name == "eth-sri/agentbench"
        assert DEFAULT_CONFIG.context_mode is ContextMode.NONE

    def test_loads_defaults_when_no_yaml(self, tmp_path: Path) -> None:
        config = load_benchmark_config(project_root=tmp_path)
        assert config.dataset_name == "eth-sri/agentbench"
        assert config.subset_size == 20

    def test_overrides_take_precedence(self, tmp_path: Path) -> None:
        config = load_benchmark_config(
            project_root=tmp_path,
            overrides={
                "subset_size": 50,
                "workers": 8,
                "context_mode": ContextMode.TAPPS,
            },
        )
        assert config.subset_size == 50
        assert config.workers == 8
        assert config.context_mode is ContextMode.TAPPS

    def test_loads_from_yaml(self, tmp_path: Path) -> None:
        yaml_content = """\
benchmark:
  dataset_name: local/dataset
  subset_size: 100
  context_mode: tapps
  workers: 2
"""
        (tmp_path / ".tapps-mcp.yaml").write_text(yaml_content, encoding="utf-8")
        config = load_benchmark_config(project_root=tmp_path)
        assert config.dataset_name == "local/dataset"
        assert config.subset_size == 100
        assert config.context_mode is ContextMode.TAPPS
        assert config.workers == 2

    def test_overrides_beat_yaml(self, tmp_path: Path) -> None:
        yaml_content = """\
benchmark:
  subset_size: 100
"""
        (tmp_path / ".tapps-mcp.yaml").write_text(yaml_content, encoding="utf-8")
        config = load_benchmark_config(project_root=tmp_path, overrides={"subset_size": 5})
        assert config.subset_size == 5

    def test_invalid_yaml_falls_back_to_defaults(self, tmp_path: Path) -> None:
        (tmp_path / ".tapps-mcp.yaml").write_text("not: valid: yaml: [", encoding="utf-8")
        config = load_benchmark_config(project_root=tmp_path)
        assert config.dataset_name == "eth-sri/agentbench"

    def test_invalid_values_fall_back_to_defaults(self, tmp_path: Path) -> None:
        yaml_content = """\
benchmark:
  workers: -5
"""
        (tmp_path / ".tapps-mcp.yaml").write_text(yaml_content, encoding="utf-8")
        config = load_benchmark_config(project_root=tmp_path)
        # Should fall back to defaults on validation error
        assert config.workers == 4

    def test_context_mode_string_coercion(self, tmp_path: Path) -> None:
        config = load_benchmark_config(
            project_root=tmp_path,
            overrides={"context_mode": "human"},
        )
        assert config.context_mode is ContextMode.HUMAN

    def test_uses_cwd_when_no_root(self) -> None:
        # When no project_root is given, load_benchmark_config falls back to CWD.
        # Just verify it returns a valid config without crashing.
        config = load_benchmark_config()
        assert isinstance(config, BenchmarkConfig)
