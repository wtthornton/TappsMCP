"""Comprehensive tests for Epic 31 - Template Self-Optimization Loop.

Covers all 7 stories: template versions, redundancy analysis, ablation,
engagement calibration, failure analysis, promotion gate, and CLI commands.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from tapps_mcp.benchmark.mock_evaluator import MockEvaluator, make_test_result
from tapps_mcp.benchmark.models import (
    BenchmarkConfig,
    BenchmarkInstance,
    BenchmarkSummary,
    ContextMode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_INSTANCE_FIELDS: dict[str, Any] = {
    "instance_id": "test-001",
    "repo": "owner/repo",
    "problem_description": "Fix the bug.",
    "clean_pr_patch": "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new\n",
    "test_commands": ["pytest tests/"],
    "test_file_names": ["tests/test_foo.py"],
    "test_file_contents": {"tests/test_foo.py": "def test(): pass"},
    "docker_image": "",
}


def _make_instance(**overrides: Any) -> BenchmarkInstance:
    """Build a BenchmarkInstance with sensible defaults."""
    fields: dict[str, Any] = {**_REQUIRED_INSTANCE_FIELDS, **overrides}
    return BenchmarkInstance(**fields)


def _make_summary(
    total: int = 20,
    resolved: int = 10,
    context_mode: ContextMode = ContextMode.TAPPS,
    engagement_level: str = "medium",
) -> BenchmarkSummary:
    """Build a BenchmarkSummary with sensible defaults."""
    return BenchmarkSummary(
        total_instances=total,
        resolved_count=resolved,
        avg_tokens=1500.0,
        avg_cost=0.015,
        avg_steps=5.0,
        context_mode=context_mode,
        engagement_level=engagement_level,
    )


_SAMPLE_TEMPLATE = """\
# Template Title

Some preamble content here.

## Getting Started

This section covers setup instructions for the project.
Install dependencies and configure your environment.

## Code Quality

Run linting and formatting checks before committing.
Use ruff for linting and black for formatting.

## Testing Strategy

Write unit tests for all public functions.
Use pytest as the test framework.

## Deployment

Deploy using Docker containers on Kubernetes.
Monitor with Prometheus and Grafana.
"""


# ===========================================================================
# Story 31.1: TestTemplateVersionStore
# ===========================================================================


class TestTemplateVersionStoreRecord:
    """Test recording new template versions."""

    def test_record_creates_version(self, tmp_path: Path) -> None:
        """Recording a version creates a new entry with auto-increment."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            version = store.record_version("template content", "medium")

            assert version.version == 1
            assert version.engagement_level == "medium"
            assert version.content_hash != ""
            assert version.promoted is False
        finally:
            store.close()

    def test_record_auto_increments(self, tmp_path: Path) -> None:
        """Each recording gets a new auto-incremented version number."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            v1 = store.record_version("content 1", "medium")
            v2 = store.record_version("content 2", "medium")
            v3 = store.record_version("content 3", "high")

            assert v1.version == 1
            assert v2.version == 2
            assert v3.version == 3
        finally:
            store.close()

    def test_record_computes_sha256(self, tmp_path: Path) -> None:
        """Content hash is a valid SHA-256 hex digest."""
        import hashlib

        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            content = "test content for hashing"
            version = store.record_version(content, "low")

            expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
            assert version.content_hash == expected
        finally:
            store.close()

    def test_record_with_metadata(self, tmp_path: Path) -> None:
        """Metadata is stored and retrievable."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            version = store.record_version(
                "content", "medium", metadata={"source": "test", "author": "ci"}
            )

            assert version.metadata == {"source": "test", "author": "ci"}
        finally:
            store.close()


class TestTemplateVersionStoreHistory:
    """Test version history retrieval."""

    def test_get_latest_returns_newest(self, tmp_path: Path) -> None:
        """get_latest returns the most recently recorded version."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            store.record_version("v1", "medium")
            store.record_version("v2", "medium")
            v3 = store.record_version("v3", "medium")

            latest = store.get_latest("medium")
            assert latest is not None
            assert latest.version == v3.version
        finally:
            store.close()

    def test_get_latest_filters_by_level(self, tmp_path: Path) -> None:
        """get_latest respects engagement_level filter."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            store.record_version("high-content", "high")
            store.record_version("med-content", "medium")

            latest_high = store.get_latest("high")
            assert latest_high is not None
            assert latest_high.engagement_level == "high"
        finally:
            store.close()

    def test_get_latest_returns_none_when_empty(self, tmp_path: Path) -> None:
        """get_latest returns None when no versions exist."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            assert store.get_latest("medium") is None
        finally:
            store.close()

    def test_get_history_respects_limit(self, tmp_path: Path) -> None:
        """get_history returns at most 'limit' entries."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            for i in range(5):
                store.record_version(f"content-{i}", "medium")

            history = store.get_history("medium", limit=3)
            assert len(history) == 3
            # Should be newest first
            assert history[0].version > history[1].version
        finally:
            store.close()


class TestTemplateVersionStoreBestAndPromote:
    """Test best version selection and promotion."""

    def test_get_best_returns_highest_resolution(self, tmp_path: Path) -> None:
        """get_best returns the version with highest resolution rate."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            v1 = store.record_version("low-score", "medium")
            v2 = store.record_version("high-score", "medium")

            store.record_scores(
                v1.version,
                benchmark_scores=_make_summary(total=20, resolved=8),
            )
            store.record_scores(
                v2.version,
                benchmark_scores=_make_summary(total=20, resolved=15),
            )

            best = store.get_best("medium")
            assert best is not None
            assert best.version == v2.version
        finally:
            store.close()

    def test_get_best_returns_none_without_scores(self, tmp_path: Path) -> None:
        """get_best returns None when no versions have benchmark scores."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            store.record_version("no-scores", "medium")
            assert store.get_best("medium") is None
        finally:
            store.close()

    def test_promote_marks_version(self, tmp_path: Path) -> None:
        """promote sets promoted flag and reason."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            v = store.record_version("content", "medium")
            result = store.promote(v.version, "Best resolution rate")

            assert result is True

            latest = store.get_latest("medium")
            assert latest is not None
            assert latest.promoted is True
            assert latest.promotion_reason == "Best resolution rate"
        finally:
            store.close()

    def test_promote_returns_false_for_missing(self, tmp_path: Path) -> None:
        """promote returns False when version doesn't exist."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            assert store.promote(999, "reason") is False
        finally:
            store.close()


class TestTemplateVersionStoreCompare:
    """Test version comparison."""

    def test_compare_two_versions(self, tmp_path: Path) -> None:
        """compare returns diff metrics for two versions."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            v1 = store.record_version("content-a", "medium")
            v2 = store.record_version("content-b", "medium")

            store.record_scores(
                v1.version,
                benchmark_scores=_make_summary(total=20, resolved=8),
                redundancy_score=0.3,
            )
            store.record_scores(
                v2.version,
                benchmark_scores=_make_summary(total=20, resolved=12),
                redundancy_score=0.2,
            )

            result = store.compare(v1.version, v2.version)

            assert result["same_content"] is False
            assert result["resolution_rate_a"] is not None
            assert result["resolution_rate_b"] is not None
            assert "resolution_delta" in result
            assert result["resolution_delta"] == pytest.approx(0.2, abs=0.01)
        finally:
            store.close()

    def test_compare_missing_version(self, tmp_path: Path) -> None:
        """compare returns error when a version doesn't exist."""
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            v1 = store.record_version("content", "medium")
            result = store.compare(v1.version, 999)

            assert "error" in result
        finally:
            store.close()


# ===========================================================================
# Story 31.2: TestRedundancyAnalyzerV2
# ===========================================================================


class TestRedundancyAnalyzerV2Sections:
    """Test section-level redundancy analysis."""

    def test_analyze_with_no_repo_docs(self, tmp_path: Path) -> None:
        """Analysis with no repo docs results in low redundancy."""
        from tapps_mcp.benchmark.redundancy import RedundancyAnalyzerV2

        analyzer = RedundancyAnalyzerV2()
        report = analyzer.analyze_template_redundancy(_SAMPLE_TEMPLATE, tmp_path)

        assert report.total_sections > 0
        # With no repo docs, redundancy should be very low
        assert report.overall_score == pytest.approx(0.0, abs=0.01)

    def test_analyze_finds_sections(self, tmp_path: Path) -> None:
        """Analyzer correctly identifies template sections."""
        from tapps_mcp.benchmark.redundancy import RedundancyAnalyzerV2

        analyzer = RedundancyAnalyzerV2()
        report = analyzer.analyze_template_redundancy(_SAMPLE_TEMPLATE, tmp_path)

        section_names = [s.section_name for s in report.sections]
        assert "Getting Started" in section_names
        assert "Code Quality" in section_names
        assert "Testing Strategy" in section_names

    def test_analyze_with_overlapping_docs(self, tmp_path: Path) -> None:
        """Analysis detects overlap with existing repo docs."""
        from tapps_mcp.benchmark.redundancy import RedundancyAnalyzerV2

        # Create a README with overlapping content
        readme = tmp_path / "README.md"
        readme.write_text(
            "# Project\n\n"
            "Install dependencies and configure your environment.\n"
            "Run linting and formatting checks before committing.\n"
            "Use ruff for linting and black for formatting.\n"
            "Write unit tests for all public functions.\n"
            "Use pytest as the test framework.\n"
            "Deploy using Docker containers on Kubernetes.\n"
            "Monitor with Prometheus and Grafana.\n",
            encoding="utf-8",
        )

        analyzer = RedundancyAnalyzerV2()
        report = analyzer.analyze_template_redundancy(_SAMPLE_TEMPLATE, tmp_path)

        # Should detect significant redundancy
        assert report.overall_score > 0.05

    def test_section_recommendations(self, tmp_path: Path) -> None:
        """Sections are classified as keep/reduce/remove correctly."""
        from tapps_mcp.benchmark.redundancy import RedundancyAnalyzerV2

        analyzer = RedundancyAnalyzerV2()
        report = analyzer.analyze_template_redundancy(_SAMPLE_TEMPLATE, tmp_path)

        for section in report.sections:
            assert section.recommendation in ("keep", "reduce", "remove")

    def test_counts_match_sections(self, tmp_path: Path) -> None:
        """sections_to_remove + sections_to_reduce are consistent."""
        from tapps_mcp.benchmark.redundancy import RedundancyAnalyzerV2

        analyzer = RedundancyAnalyzerV2()
        report = analyzer.analyze_template_redundancy(_SAMPLE_TEMPLATE, tmp_path)

        remove_count = sum(
            1 for s in report.sections if s.recommendation == "remove"
        )
        reduce_count = sum(
            1 for s in report.sections if s.recommendation == "reduce"
        )
        assert report.sections_to_remove == remove_count
        assert report.sections_to_reduce == reduce_count


class TestRedundancyAnalyzerV2TFIDF:
    """Test TF-IDF implementation details."""

    def test_tfidf_cosine_identical_docs(self) -> None:
        """Identical documents should have cosine similarity near 1.0."""
        from tapps_mcp.benchmark.redundancy import (
            _build_idf,
            _build_tf,
            _cosine_similarity,
            _tfidf_vector,
            _tokenize,
        )

        text = "python testing framework pytest unit integration"
        tokens = _tokenize(text)
        # Include a different document so IDF is non-zero for some terms
        other_tokens = _tokenize("deploy kubernetes docker containers")

        collection = [tokens, tokens, other_tokens]
        idf = _build_idf(collection)
        tf = _build_tf(tokens)
        vec = _tfidf_vector(tf, idf)

        sim = _cosine_similarity(vec, vec)
        assert sim == pytest.approx(1.0, abs=0.001)

    def test_tfidf_cosine_different_docs(self) -> None:
        """Completely different documents should have low similarity."""
        from tapps_mcp.benchmark.redundancy import (
            _build_idf,
            _build_tf,
            _cosine_similarity,
            _tfidf_vector,
            _tokenize,
        )

        tokens_a = _tokenize("python testing framework pytest")
        tokens_b = _tokenize("deploy kubernetes docker containers")

        collection = [tokens_a, tokens_b]
        idf = _build_idf(collection)

        vec_a = _tfidf_vector(_build_tf(tokens_a), idf)
        vec_b = _tfidf_vector(_build_tf(tokens_b), idf)

        sim = _cosine_similarity(vec_a, vec_b)
        assert sim < 0.3

    def test_jaccard_empty_sets(self) -> None:
        """Jaccard similarity of empty sets is 1.0 (identical documents)."""
        from tapps_mcp.benchmark.redundancy import _jaccard_similarity

        assert _jaccard_similarity(set(), set()) == 1.0


class TestRedundancyTemplateReduction:
    """Test template reduction from redundancy reports."""

    def test_generate_reduced_removes_sections(self, tmp_path: Path) -> None:
        """generate_reduced_template removes 'remove' sections."""
        from tapps_mcp.benchmark.redundancy import (
            RedundancyAnalyzerV2,
            SectionRedundancyReport,
            TemplateRedundancyReport,
        )

        report = TemplateRedundancyReport(
            overall_score=0.5,
            sections=[
                SectionRedundancyReport(
                    section_name="Keep This",
                    section_content="Important content.",
                    redundancy_score=0.1,
                    recommendation="keep",
                    unique_content="Important content.",
                ),
                SectionRedundancyReport(
                    section_name="Remove This",
                    section_content="Redundant stuff.",
                    redundancy_score=0.8,
                    recommendation="remove",
                    unique_content="",
                ),
                SectionRedundancyReport(
                    section_name="Reduce This",
                    section_content="Mixed content here.",
                    redundancy_score=0.4,
                    recommendation="reduce",
                    unique_content="unique part only",
                ),
            ],
            total_sections=3,
            sections_to_remove=1,
            sections_to_reduce=1,
        )

        analyzer = RedundancyAnalyzerV2()
        reduced = analyzer.generate_reduced_template(report)

        assert "Keep This" in reduced
        assert "Remove This" not in reduced
        assert "Reduce This" in reduced
        assert "unique part only" in reduced


# ===========================================================================
# Story 31.3: TestAblationRunner
# ===========================================================================


class TestAblationRunner:
    """Test section ablation testing."""

    @pytest.mark.asyncio()
    async def test_ablation_returns_results_per_section(
        self, tmp_path: Path
    ) -> None:
        """Ablation returns one result per section."""
        from tapps_mcp.benchmark.ablation import AblationConfig, AblationRunner

        # Create a minimal dataset file
        dataset_file = tmp_path / "test.json"
        instances = [
            {
                **_REQUIRED_INSTANCE_FIELDS,
                "instance_id": f"abl-{i}",
            }
            for i in range(5)
        ]
        dataset_file.write_text(json.dumps(instances), encoding="utf-8")

        config = AblationConfig(
            base_template=_SAMPLE_TEMPLATE,
            sections=["Getting Started", "Code Quality"],
            benchmark_config=BenchmarkConfig(
                dataset_name=str(dataset_file),
                context_mode=ContextMode.TAPPS,
                subset_size=0,
            ),
        )

        runner = AblationRunner()
        evaluator = MockEvaluator(seed=42)
        results = await runner.run_ablation(config, evaluator)

        assert len(results) == 2
        assert results[0].removed_section == "Getting Started"
        assert results[1].removed_section == "Code Quality"

    @pytest.mark.asyncio()
    async def test_ablation_classification(self, tmp_path: Path) -> None:
        """Ablation results have valid classification."""
        from tapps_mcp.benchmark.ablation import AblationConfig, AblationRunner

        dataset_file = tmp_path / "test.json"
        instances = [
            {**_REQUIRED_INSTANCE_FIELDS, "instance_id": f"cls-{i}"}
            for i in range(5)
        ]
        dataset_file.write_text(json.dumps(instances), encoding="utf-8")

        config = AblationConfig(
            base_template=_SAMPLE_TEMPLATE,
            sections=["Testing Strategy"],
            benchmark_config=BenchmarkConfig(
                dataset_name=str(dataset_file),
                context_mode=ContextMode.TAPPS,
                subset_size=0,
            ),
        )

        runner = AblationRunner()
        evaluator = MockEvaluator(seed=42)
        results = await runner.run_ablation(config, evaluator)

        assert len(results) == 1
        assert results[0].recommendation in ("essential", "neutral", "harmful")

    @pytest.mark.asyncio()
    async def test_ablation_with_baseline_results(self, tmp_path: Path) -> None:
        """Ablation uses provided baseline results."""
        from tapps_mcp.benchmark.ablation import AblationConfig, AblationRunner

        dataset_file = tmp_path / "test.json"
        instances = [
            {**_REQUIRED_INSTANCE_FIELDS, "instance_id": f"base-{i}"}
            for i in range(5)
        ]
        dataset_file.write_text(json.dumps(instances), encoding="utf-8")

        # Pre-computed baseline
        baseline = [
            make_test_result(
                instance_id=f"base-{i}",
                context_mode=ContextMode.TAPPS,
                resolved=i < 3,
            )
            for i in range(5)
        ]

        config = AblationConfig(
            base_template=_SAMPLE_TEMPLATE,
            sections=["Deployment"],
            benchmark_config=BenchmarkConfig(
                dataset_name=str(dataset_file),
                context_mode=ContextMode.TAPPS,
                subset_size=0,
            ),
            baseline_results=baseline,
        )

        runner = AblationRunner()
        evaluator = MockEvaluator(seed=42)
        results = await runner.run_ablation(config, evaluator)

        assert len(results) == 1
        # delta_vs_full should be relative to our baseline (60% = 3/5)
        assert isinstance(results[0].delta_vs_full, float)

    def test_generate_optimal_template(self) -> None:
        """generate_optimal_template removes harmful sections."""
        from tapps_mcp.benchmark.ablation import AblationResult, AblationRunner

        results = [
            AblationResult(
                removed_section="Getting Started",
                resolution_rate=0.5,
                delta_vs_full=-0.05,
                delta_vs_none=0.1,
                recommendation="essential",
            ),
            AblationResult(
                removed_section="Deployment",
                resolution_rate=0.6,
                delta_vs_full=0.05,
                delta_vs_none=0.2,
                recommendation="harmful",
            ),
            AblationResult(
                removed_section="Code Quality",
                resolution_rate=0.55,
                delta_vs_full=0.0,
                delta_vs_none=0.15,
                recommendation="neutral",
            ),
        ]

        runner = AblationRunner()
        optimized = runner.generate_optimal_template(results, _SAMPLE_TEMPLATE)

        assert "Getting Started" in optimized
        assert "Code Quality" in optimized
        # Deployment should be removed (harmful)
        assert "## Deployment" not in optimized

    def test_generate_optimal_no_harmful(self) -> None:
        """When no sections are harmful, template is unchanged."""
        from tapps_mcp.benchmark.ablation import AblationResult, AblationRunner

        results = [
            AblationResult(
                removed_section="Getting Started",
                resolution_rate=0.5,
                delta_vs_full=-0.05,
                delta_vs_none=0.1,
                recommendation="essential",
            ),
        ]

        runner = AblationRunner()
        optimized = runner.generate_optimal_template(results, _SAMPLE_TEMPLATE)

        assert "Getting Started" in optimized
        assert "Code Quality" in optimized
        assert "Deployment" in optimized


# ===========================================================================
# Story 31.4: TestEngagementCalibrator
# ===========================================================================


class TestEngagementCalibrator:
    """Test engagement level calibration."""

    @pytest.mark.asyncio()
    async def test_calibrate_returns_all_levels(self, tmp_path: Path) -> None:
        """Calibration produces results for all three engagement levels."""
        from tapps_mcp.benchmark.engagement_calibrator import EngagementCalibrator

        dataset_file = tmp_path / "test.json"
        instances = [
            {**_REQUIRED_INSTANCE_FIELDS, "instance_id": f"cal-{i}"}
            for i in range(5)
        ]
        dataset_file.write_text(json.dumps(instances), encoding="utf-8")

        config = BenchmarkConfig(
            dataset_name=str(dataset_file),
            context_mode=ContextMode.TAPPS,
            subset_size=0,
        )

        calibrator = EngagementCalibrator()
        evaluator = MockEvaluator(seed=42)
        report = await calibrator.calibrate(config, evaluator)

        assert len(report.calibrations) == 3
        levels = {c.level for c in report.calibrations}
        assert levels == {"high", "medium", "low"}

    @pytest.mark.asyncio()
    async def test_calibrate_recommends_a_level(self, tmp_path: Path) -> None:
        """Calibration produces a valid recommendation."""
        from tapps_mcp.benchmark.engagement_calibrator import EngagementCalibrator

        dataset_file = tmp_path / "test.json"
        instances = [
            {**_REQUIRED_INSTANCE_FIELDS, "instance_id": f"rec-{i}"}
            for i in range(5)
        ]
        dataset_file.write_text(json.dumps(instances), encoding="utf-8")

        config = BenchmarkConfig(
            dataset_name=str(dataset_file),
            context_mode=ContextMode.TAPPS,
            subset_size=0,
        )

        calibrator = EngagementCalibrator()
        evaluator = MockEvaluator(seed=42)
        report = await calibrator.calibrate(config, evaluator)

        assert report.recommended_level in ("high", "medium", "low")
        assert len(report.recommendation_reason) > 0

    @pytest.mark.asyncio()
    async def test_calibrate_warns_worse_than_none(
        self, tmp_path: Path
    ) -> None:
        """Calibration warns when a level performs worse than no-context."""
        from tapps_mcp.benchmark.engagement_calibrator import EngagementCalibrator

        dataset_file = tmp_path / "test.json"
        instances = [
            {**_REQUIRED_INSTANCE_FIELDS, "instance_id": f"warn-{i}"}
            for i in range(10)
        ]
        dataset_file.write_text(json.dumps(instances), encoding="utf-8")

        # Use rates where NONE beats everything
        rates = {
            ContextMode.NONE: 0.9,
            ContextMode.TAPPS: 0.1,
        }
        evaluator = MockEvaluator(default_resolution_rates=rates, seed=42)

        config = BenchmarkConfig(
            dataset_name=str(dataset_file),
            context_mode=ContextMode.TAPPS,
            subset_size=0,
        )

        calibrator = EngagementCalibrator()
        report = await calibrator.calibrate(config, evaluator)

        # With TAPPS at 10% and NONE at 90%, should warn
        # Note: MockEvaluator uses the same rates for all engagement levels
        # so all three levels get the TAPPS rate.
        assert report.warning is not None or any(
            c.delta_vs_none < 0 for c in report.calibrations
        )

    @pytest.mark.asyncio()
    async def test_calibrate_efficiency_metrics(self, tmp_path: Path) -> None:
        """Calibration computes resolution_per_token for each level."""
        from tapps_mcp.benchmark.engagement_calibrator import EngagementCalibrator

        dataset_file = tmp_path / "test.json"
        instances = [
            {**_REQUIRED_INSTANCE_FIELDS, "instance_id": f"eff-{i}"}
            for i in range(5)
        ]
        dataset_file.write_text(json.dumps(instances), encoding="utf-8")

        config = BenchmarkConfig(
            dataset_name=str(dataset_file),
            context_mode=ContextMode.TAPPS,
            subset_size=0,
        )

        calibrator = EngagementCalibrator()
        evaluator = MockEvaluator(seed=42)
        report = await calibrator.calibrate(config, evaluator)

        for cal in report.calibrations:
            assert cal.resolution_per_token >= 0.0
            assert cal.avg_token_cost >= 0.0

    @pytest.mark.asyncio()
    async def test_calibrate_delta_vs_medium(self, tmp_path: Path) -> None:
        """Each calibration includes delta_vs_medium."""
        from tapps_mcp.benchmark.engagement_calibrator import EngagementCalibrator

        dataset_file = tmp_path / "test.json"
        instances = [
            {**_REQUIRED_INSTANCE_FIELDS, "instance_id": f"dvm-{i}"}
            for i in range(5)
        ]
        dataset_file.write_text(json.dumps(instances), encoding="utf-8")

        config = BenchmarkConfig(
            dataset_name=str(dataset_file),
            context_mode=ContextMode.TAPPS,
            subset_size=0,
        )

        calibrator = EngagementCalibrator()
        evaluator = MockEvaluator(seed=42)
        report = await calibrator.calibrate(config, evaluator)

        medium_cal = next(
            (c for c in report.calibrations if c.level == "medium"), None
        )
        assert medium_cal is not None
        # Medium's delta_vs_medium should be 0
        assert medium_cal.delta_vs_medium == pytest.approx(0.0, abs=0.0001)


# ===========================================================================
# Story 31.5: TestFailureAnalyzer
# ===========================================================================


class TestFailureAnalyzerPatterns:
    """Test failure pattern identification."""

    def test_no_failures_returns_empty(self) -> None:
        """No failures produces an empty pattern list."""
        from tapps_mcp.benchmark.failure_analyzer import FailureAnalyzer

        results = [make_test_result(resolved=True) for _ in range(5)]
        instances = [_make_instance(instance_id=f"pass-{i}") for i in range(5)]

        analyzer = FailureAnalyzer()
        patterns = analyzer.analyze_failures(results, instances)

        assert patterns == []

    def test_failures_clustered_by_error(self) -> None:
        """Failures with similar errors are clustered together."""
        from tapps_mcp.benchmark.failure_analyzer import FailureAnalyzer

        results = [
            make_test_result(
                instance_id=f"fail-{i}",
                resolved=False,
                error="ImportError: no module named foo",
            )
            for i in range(3)
        ]
        results.append(
            make_test_result(
                instance_id="fail-timeout",
                resolved=False,
                error="timeout exceeded after 300s",
            )
        )

        instances = [_make_instance(instance_id=f"fail-{i}") for i in range(3)]
        instances.append(_make_instance(instance_id="fail-timeout"))

        analyzer = FailureAnalyzer()
        patterns = analyzer.analyze_failures(results, instances)

        assert len(patterns) >= 2
        pattern_types = {p.pattern_type for p in patterns}
        assert "import" in pattern_types
        assert "timeout" in pattern_types

    def test_patterns_sorted_by_frequency(self) -> None:
        """Patterns are sorted by frequency (most common first)."""
        from tapps_mcp.benchmark.failure_analyzer import FailureAnalyzer

        results = [
            make_test_result(
                instance_id=f"imp-{i}",
                resolved=False,
                error="import error",
            )
            for i in range(5)
        ]
        results.append(
            make_test_result(
                instance_id="timeout-1",
                resolved=False,
                error="timeout",
            )
        )

        instances = [_make_instance(instance_id=r.instance_id) for r in results]

        analyzer = FailureAnalyzer()
        patterns = analyzer.analyze_failures(results, instances)

        assert patterns[0].frequency >= patterns[-1].frequency

    def test_patterns_capped_at_max(self) -> None:
        """At most 5 patterns are returned."""
        from tapps_mcp.benchmark.failure_analyzer import FailureAnalyzer

        results = []
        for i, keyword in enumerate(
            ["timeout", "import", "syntax", "assertion", "type", "memory", "path"]
        ):
            results.append(
                make_test_result(
                    instance_id=f"err-{i}",
                    resolved=False,
                    error=f"{keyword} error occurred",
                )
            )

        instances = [_make_instance(instance_id=r.instance_id) for r in results]

        analyzer = FailureAnalyzer()
        patterns = analyzer.analyze_failures(results, instances)

        assert len(patterns) <= 5

    def test_suggested_fix_not_empty(self) -> None:
        """Each pattern has a non-empty suggested fix."""
        from tapps_mcp.benchmark.failure_analyzer import FailureAnalyzer

        results = [
            make_test_result(
                instance_id="err-1", resolved=False, error="import error"
            )
        ]
        instances = [_make_instance(instance_id="err-1")]

        analyzer = FailureAnalyzer()
        patterns = analyzer.analyze_failures(results, instances)

        for pattern in patterns:
            assert len(pattern.suggested_fix) > 0


class TestFailureAnalyzerSuggestions:
    """Test template suggestion generation."""

    def test_generates_suggestions_from_patterns(self) -> None:
        """Suggestions are generated for each failure pattern."""
        from tapps_mcp.benchmark.failure_analyzer import (
            FailureAnalyzer,
            FailurePattern,
        )

        patterns = [
            FailurePattern(
                pattern_type="import",
                frequency=5,
                affected_repos=["owner/repo"],
                example_instance_ids=["fail-1"],
                suggested_fix="Add import guidance.",
            ),
        ]

        analyzer = FailureAnalyzer()
        suggestions = analyzer.generate_suggestions(patterns, _SAMPLE_TEMPLATE)

        assert len(suggestions) == 1
        assert suggestions[0].action in ("add", "modify")
        assert len(suggestions[0].content) > 0

    def test_suggestions_detect_existing_sections(self) -> None:
        """Suggestions use 'modify' for sections that already exist."""
        from tapps_mcp.benchmark.failure_analyzer import (
            FailureAnalyzer,
            FailurePattern,
        )

        # "Testing Strategy" exists in _SAMPLE_TEMPLATE
        patterns = [
            FailurePattern(
                pattern_type="assertion",
                frequency=3,
                affected_repos=["owner/repo"],
                example_instance_ids=["fail-1"],
                suggested_fix="Improve test guidance.",
            ),
        ]

        analyzer = FailureAnalyzer()
        suggestions = analyzer.generate_suggestions(patterns, _SAMPLE_TEMPLATE)

        assert len(suggestions) == 1
        assert suggestions[0].section == "Testing Strategy"
        assert suggestions[0].action == "modify"


# ===========================================================================
# Story 31.6: TestPromotionGate
# ===========================================================================


class TestPromotionGateApproval:
    """Test promotion gate approval logic."""

    def test_approve_first_version(self) -> None:
        """First version with good scores is approved."""
        from tapps_mcp.benchmark.promotion import (
            PromotionCriteria,
            evaluate_promotion,
        )
        from tapps_mcp.benchmark.template_versions import TemplateVersion

        candidate = TemplateVersion(
            version=1,
            content_hash="abc123",
            engagement_level="medium",
            benchmark_scores=_make_summary(total=25, resolved=15),
            redundancy_score=0.3,
            created_at="2026-01-01T00:00:00",
        )

        decision = evaluate_promotion(candidate, None, PromotionCriteria())

        assert decision.approved is True
        assert "first promotion" in decision.reason.lower() or "approved" in decision.reason.lower()

    def test_reject_without_scores(self) -> None:
        """Candidate without benchmark scores is rejected."""
        from tapps_mcp.benchmark.promotion import (
            PromotionCriteria,
            evaluate_promotion,
        )
        from tapps_mcp.benchmark.template_versions import TemplateVersion

        candidate = TemplateVersion(
            version=1,
            content_hash="abc123",
            engagement_level="medium",
            benchmark_scores=None,
            created_at="2026-01-01T00:00:00",
        )

        decision = evaluate_promotion(candidate, None, PromotionCriteria())

        assert decision.approved is False
        assert "no benchmark scores" in decision.reason.lower()

    def test_reject_insufficient_instances(self) -> None:
        """Candidate with too few evaluated instances is rejected."""
        from tapps_mcp.benchmark.promotion import (
            PromotionCriteria,
            evaluate_promotion,
        )
        from tapps_mcp.benchmark.template_versions import TemplateVersion

        candidate = TemplateVersion(
            version=1,
            content_hash="abc123",
            engagement_level="medium",
            benchmark_scores=_make_summary(total=5, resolved=3),
            redundancy_score=0.2,
            created_at="2026-01-01T00:00:00",
        )

        criteria = PromotionCriteria(min_instances_evaluated=20)
        decision = evaluate_promotion(candidate, None, criteria)

        assert decision.approved is False
        assert "insufficient" in decision.reason.lower()

    def test_reject_high_redundancy(self) -> None:
        """Candidate with redundancy above threshold is rejected."""
        from tapps_mcp.benchmark.promotion import (
            PromotionCriteria,
            evaluate_promotion,
        )
        from tapps_mcp.benchmark.template_versions import TemplateVersion

        candidate = TemplateVersion(
            version=1,
            content_hash="abc123",
            engagement_level="medium",
            benchmark_scores=_make_summary(total=25, resolved=15),
            redundancy_score=0.8,
            created_at="2026-01-01T00:00:00",
        )

        criteria = PromotionCriteria(max_redundancy=0.5)
        decision = evaluate_promotion(candidate, None, criteria)

        assert decision.approved is False
        assert "redundancy" in decision.reason.lower()

    def test_reject_no_improvement(self) -> None:
        """Candidate worse than current is rejected."""
        from tapps_mcp.benchmark.promotion import (
            PromotionCriteria,
            evaluate_promotion,
        )
        from tapps_mcp.benchmark.template_versions import TemplateVersion

        current = TemplateVersion(
            version=1,
            content_hash="current",
            engagement_level="medium",
            benchmark_scores=_make_summary(total=25, resolved=20),
            redundancy_score=0.2,
            created_at="2026-01-01T00:00:00",
        )

        candidate = TemplateVersion(
            version=2,
            content_hash="candidate",
            engagement_level="medium",
            benchmark_scores=_make_summary(total=25, resolved=10),
            redundancy_score=0.2,
            created_at="2026-01-02T00:00:00",
        )

        criteria = PromotionCriteria(min_resolution_delta=0.0)
        decision = evaluate_promotion(candidate, current, criteria)

        assert decision.approved is False


class TestAutoPromote:
    """Test auto_promote function."""

    def test_auto_promote_success(self, tmp_path: Path) -> None:
        """auto_promote promotes a valid candidate."""
        from tapps_mcp.benchmark.promotion import auto_promote
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            v = store.record_version("content", "medium")
            store.record_scores(
                v.version,
                benchmark_scores=_make_summary(total=25, resolved=15),
                redundancy_score=0.2,
            )

            result = auto_promote(v.version, store)
            assert result is True

            # Verify promoted
            latest = store.get_latest("medium")
            assert latest is not None
            assert latest.promoted is True
        finally:
            store.close()

    def test_auto_promote_missing_version(self, tmp_path: Path) -> None:
        """auto_promote returns False for a non-existent version."""
        from tapps_mcp.benchmark.promotion import auto_promote
        from tapps_mcp.benchmark.template_versions import TemplateVersionStore

        store = TemplateVersionStore(db_path=tmp_path / "versions.db")
        try:
            result = auto_promote(999, store)
            assert result is False
        finally:
            store.close()


# ===========================================================================
# Story 31.7: TestTemplateCLI
# ===========================================================================


class TestTemplateCLIHelp:
    """Test CLI command help text."""

    def test_template_group_help(self) -> None:
        """Template group shows help text."""
        from tapps_mcp.benchmark.cli_commands import template_group

        runner = CliRunner()
        result = runner.invoke(template_group, ["--help"])

        assert result.exit_code == 0
        assert "template" in result.output.lower() or "optimization" in result.output.lower()

    def test_optimize_help(self) -> None:
        """optimize command shows help text."""
        from tapps_mcp.benchmark.cli_commands import template_group

        runner = CliRunner()
        result = runner.invoke(template_group, ["optimize", "--help"])

        assert result.exit_code == 0
        assert "engagement-level" in result.output.lower()

    def test_ablate_help(self) -> None:
        """ablate command shows help text."""
        from tapps_mcp.benchmark.cli_commands import template_group

        runner = CliRunner()
        result = runner.invoke(template_group, ["ablate", "--help"])

        assert result.exit_code == 0
        assert "ablation" in result.output.lower() or "section" in result.output.lower()

    def test_compare_help(self) -> None:
        """compare command shows help text."""
        from tapps_mcp.benchmark.cli_commands import template_group

        runner = CliRunner()
        result = runner.invoke(template_group, ["compare", "--help"])

        assert result.exit_code == 0

    def test_history_help(self) -> None:
        """history command shows help text."""
        from tapps_mcp.benchmark.cli_commands import template_group

        runner = CliRunner()
        result = runner.invoke(template_group, ["history", "--help"])

        assert result.exit_code == 0
        assert "history" in result.output.lower()

    def test_history_no_db(self, tmp_path: Path) -> None:
        """history command handles missing database gracefully."""
        from tapps_mcp.benchmark.cli_commands import template_group

        runner = CliRunner()
        result = runner.invoke(
            template_group,
            ["history", "--db-path", str(tmp_path / "nonexistent.db")],
        )

        assert result.exit_code != 0 or "not found" in result.output.lower()

    def test_compare_no_db(self, tmp_path: Path) -> None:
        """compare command handles missing database gracefully."""
        from tapps_mcp.benchmark.cli_commands import template_group

        runner = CliRunner()
        result = runner.invoke(
            template_group,
            ["compare", "1", "2", "--db-path", str(tmp_path / "nonexistent.db")],
        )

        assert result.exit_code != 0 or "not found" in result.output.lower()
