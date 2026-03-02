"""Integration tests for the benchmark pipeline (Epic 30, Story 7).

Exercises the full pipeline: fixture loading, context injection/removal,
mock evaluation, and redundancy analysis using the synthetic fixture dataset.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tapps_mcp.benchmark.context_injector import (
    ContextInjector,
    RedundancyAnalyzer,
)
from tapps_mcp.benchmark.dataset import DatasetLoader
from tapps_mcp.benchmark.mock_evaluator import MockEvaluator
from tapps_mcp.benchmark.models import BenchmarkConfig, BenchmarkInstance, ContextMode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "benchmark"
_INSTANCES_JSON = _FIXTURES_DIR / "instances.json"


def _load_fixture_instances() -> list[BenchmarkInstance]:
    """Load benchmark instances from the fixture JSON file."""
    with _INSTANCES_JSON.open(encoding="utf-8") as f:
        raw = json.load(f)
    return [BenchmarkInstance(**row) for row in raw]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestLoadFixtureDataset:
    """Test loading the fixture dataset through the DatasetLoader."""

    async def test_load_fixture_dataset(self) -> None:
        """DatasetLoader can load the 5 synthetic fixture instances from JSON."""
        config = BenchmarkConfig(
            dataset_name=str(_INSTANCES_JSON),
            subset_size=0,
        )
        loader = DatasetLoader(config)
        instances = await loader.load()

        assert len(instances) == 5

        ids = [inst.instance_id for inst in instances]
        assert "fixture-001-lint-fix" in ids
        assert "fixture-002-type-error" in ids
        assert "fixture-003-security-fix" in ids
        assert "fixture-004-refactor" in ids
        assert "fixture-005-with-agents-md" in ids

        # Verify fields on the first instance
        first = next(i for i in instances if i.instance_id == "fixture-001-lint-fix")
        assert first.repo == "example/calculator"
        assert first.test_commands == ["python -m pytest tests/"]
        assert "test_calculator.py" in first.test_file_names[0]
        assert first.key_files == ["calculator.py"]
        assert first.risk_factors is None
        assert first.rationale is not None

    async def test_fixture_instances_are_valid_models(self) -> None:
        """Every fixture instance passes Pydantic validation."""
        config = BenchmarkConfig(
            dataset_name=str(_INSTANCES_JSON),
            subset_size=0,
        )
        loader = DatasetLoader(config)
        instances = await loader.load()

        for inst in instances:
            assert isinstance(inst, BenchmarkInstance)
            assert inst.instance_id
            assert inst.repo
            assert inst.clean_pr_patch

    async def test_security_fixture_has_risk_factors(self) -> None:
        """The security fixture (003) has sql-injection in risk_factors."""
        config = BenchmarkConfig(
            dataset_name=str(_INSTANCES_JSON),
            subset_size=0,
        )
        loader = DatasetLoader(config)
        instances = await loader.load()

        security = next(i for i in instances if i.instance_id == "fixture-003-security-fix")
        assert security.risk_factors is not None
        assert "sql-injection" in security.risk_factors


@pytest.mark.slow
class TestInjectAndRemoveContext:
    """Test context injection and removal with real file I/O."""

    def test_inject_and_remove_context(self, tmp_path: Path) -> None:
        """Inject AGENTS.md into a tmp repo, verify it exists, remove, verify gone."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        injector = ContextInjector(engagement_level="medium")

        # Generate and inject context
        content = injector.generate_tapps_context(repo_dir)
        assert len(content) > 0

        target = injector.inject_context(repo_dir, content)
        assert target.exists()
        assert target.read_text(encoding="utf-8") == content
        assert target.name == "AGENTS.md"

        # Remove context
        injector.remove_context(repo_dir)
        assert not (repo_dir / "AGENTS.md").exists()

    def test_inject_preserves_existing_backup(self, tmp_path: Path) -> None:
        """When AGENTS.md already exists, it is backed up and restored."""
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        original_content = "# Existing AGENTS.md\nProject-specific docs."
        (repo_dir / "AGENTS.md").write_text(original_content, encoding="utf-8")

        injector = ContextInjector(engagement_level="medium")
        injected_content = injector.generate_tapps_context(repo_dir)

        # Inject overwrites, creating backup
        injector.inject_context(repo_dir, injected_content)
        assert (repo_dir / "AGENTS.md").read_text(encoding="utf-8") == injected_content
        assert (repo_dir / "AGENTS.md.bak").exists()

        # Remove restores original
        injector.remove_context(repo_dir)
        assert (repo_dir / "AGENTS.md").exists()
        assert (repo_dir / "AGENTS.md").read_text(encoding="utf-8") == original_content
        assert not (repo_dir / "AGENTS.md.bak").exists()


@pytest.mark.slow
class TestMockEvaluateFixtureInstances:
    """Test MockEvaluator on the full fixture dataset."""

    async def test_mock_evaluate_all_fixtures(self) -> None:
        """MockEvaluator returns a result for every fixture instance."""
        instances = _load_fixture_instances()
        evaluator = MockEvaluator(seed=42)

        results = await evaluator.evaluate_batch(instances, ContextMode.TAPPS)

        assert len(results) == 5
        for result in results:
            assert result.context_mode is ContextMode.TAPPS
            assert result.engagement_level == "medium"
            assert result.token_usage > 0
            assert result.duration_ms > 0
            assert result.steps >= 3

        # Check that instance IDs match
        result_ids = {r.instance_id for r in results}
        instance_ids = {i.instance_id for i in instances}
        assert result_ids == instance_ids

    async def test_resolved_instances_have_nonzero_patch_size(self) -> None:
        """Resolved instances should have patch_size > 0."""
        instances = _load_fixture_instances()
        evaluator = MockEvaluator(seed=42)

        results = await evaluator.evaluate_batch(instances, ContextMode.TAPPS)

        for result in results:
            if result.resolved:
                assert result.patch_size > 0
            else:
                assert result.patch_size == 0


@pytest.mark.slow
class TestFullPipelineNoneVsTapps:
    """Test the full pipeline: load, evaluate NONE, evaluate TAPPS, compare."""

    async def test_full_pipeline_none_vs_tapps(self) -> None:
        """Load fixtures, evaluate with NONE and TAPPS, compare resolution counts."""
        # Load
        instances = _load_fixture_instances()
        assert len(instances) == 5

        # Evaluate with NONE context
        evaluator_none = MockEvaluator(seed=42)
        results_none = await evaluator_none.evaluate_batch(instances, ContextMode.NONE)

        # Evaluate with TAPPS context (fresh evaluator for consistent call_count)
        evaluator_tapps = MockEvaluator(seed=42)
        results_tapps = await evaluator_tapps.evaluate_batch(instances, ContextMode.TAPPS)

        # Both should have 5 results
        assert len(results_none) == 5
        assert len(results_tapps) == 5

        # All results should be valid
        for r in results_none:
            assert r.context_mode is ContextMode.NONE
            assert isinstance(r.resolved, bool)
        for r in results_tapps:
            assert r.context_mode is ContextMode.TAPPS
            assert isinstance(r.resolved, bool)

        # Compute resolution rates
        none_resolved = sum(1 for r in results_none if r.resolved)
        tapps_resolved = sum(1 for r in results_tapps if r.resolved)

        # Both should be non-negative and at most 5
        assert 0 <= none_resolved <= 5
        assert 0 <= tapps_resolved <= 5

        # TAPPS tokens should include context overhead (200 per instance)
        tapps_total_tokens = sum(r.token_usage for r in results_tapps)
        none_total_tokens = sum(r.token_usage for r in results_none)
        assert tapps_total_tokens > none_total_tokens

    async def test_deterministic_across_runs(self) -> None:
        """Two identical pipeline runs produce the same results."""
        instances = _load_fixture_instances()

        eval_a = MockEvaluator(seed=42)
        results_a = await eval_a.evaluate_batch(instances, ContextMode.TAPPS)

        eval_b = MockEvaluator(seed=42)
        results_b = await eval_b.evaluate_batch(instances, ContextMode.TAPPS)

        for ra, rb in zip(results_a, results_b, strict=True):
            assert ra.instance_id == rb.instance_id
            assert ra.resolved == rb.resolved
            assert ra.token_usage == rb.token_usage
            assert ra.steps == rb.steps


@pytest.mark.slow
class TestRedundancyOnFixtureWithAgentsMd:
    """Test redundancy analysis for fixture-005 which has AGENTS.md as a key file."""

    def test_redundancy_on_fixture_with_agents_md(self, tmp_path: Path) -> None:
        """fixture-005 includes AGENTS.md as a key file; check redundancy scoring."""
        instances = _load_fixture_instances()
        instance_005 = next(i for i in instances if i.instance_id == "fixture-005-with-agents-md")

        # Verify the fixture has AGENTS.md in key_files
        assert "AGENTS.md" in instance_005.key_files

        # Set up a mock repo with a README.md
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()

        readme_content = (
            "# Paginator\n\n"
            "A simple pagination library.\n\n"
            "## Usage\n\n"
            "```python\n"
            "from paginator import paginate\n"
            "items = list(range(100))\n"
            "page_1 = paginate(items, 1, 10)\n"
            "```\n"
        )
        (repo_dir / "README.md").write_text(readme_content, encoding="utf-8")

        # Inject context and measure redundancy
        injector = ContextInjector(engagement_level="medium")
        agents_content = injector.generate_tapps_context(repo_dir)
        injector.inject_context(repo_dir, agents_content)

        analyzer = RedundancyAnalyzer()
        repo_docs = analyzer.collect_repo_docs(repo_dir)

        # Should have at least README.md and AGENTS.md
        assert len(repo_docs) >= 2

        redundancy = analyzer.score_redundancy(agents_content, repo_docs)
        assert 0.0 <= redundancy <= 1.0

        # Section-level analysis
        sections = analyzer.analyze_sections(agents_content, repo_docs)
        assert len(sections) > 0
        for section in sections:
            assert section.redundancy_score >= 0.0
            assert section.redundancy_score <= 1.0
            assert section.recommendation in ("keep", "reduce", "remove")

    def test_no_redundancy_without_docs(self, tmp_path: Path) -> None:
        """A repo with no documentation files has zero redundancy."""
        repo_dir = tmp_path / "empty_repo"
        repo_dir.mkdir()

        injector = ContextInjector(engagement_level="medium")
        agents_content = injector.generate_tapps_context(repo_dir)

        analyzer = RedundancyAnalyzer()
        repo_docs = analyzer.collect_repo_docs(repo_dir)

        assert len(repo_docs) == 0
        redundancy = analyzer.score_redundancy(agents_content, repo_docs)
        assert redundancy == 0.0
