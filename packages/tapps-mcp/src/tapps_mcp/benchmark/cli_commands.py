"""CLI commands for the benchmark subsystem."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click
import structlog

logger = structlog.get_logger(__name__)

__all__ = ["benchmark_group", "template_group", "tools_group"]


@click.group("benchmark")
def benchmark_group() -> None:
    """Benchmark infrastructure for evaluating TappsMCP context files."""


@benchmark_group.command("run")
@click.option(
    "--dataset",
    default="eth-sri/agentbench",
    show_default=True,
    help="HuggingFace dataset name or local file path.",
)
@click.option(
    "--context-mode",
    type=click.Choice(["none", "tapps", "human", "all"]),
    default="all",
    show_default=True,
    help="Context injection mode.",
)
@click.option(
    "--engagement-level",
    type=click.Choice(["high", "medium", "low"]),
    default="medium",
    show_default=True,
    help="TappsMCP engagement level.",
)
@click.option(
    "--subset",
    default=20,
    type=int,
    show_default=True,
    help="Number of instances (0=all).",
)
@click.option(
    "--workers",
    default=4,
    type=int,
    show_default=True,
    help="Parallel worker count.",
)
@click.option(
    "--output-dir",
    default=".tapps-mcp/benchmark/",
    show_default=True,
    help="Results output directory.",
)
@click.option(
    "--run-id",
    default="",
    help="Run identifier (auto-generated if empty).",
)
@click.option(
    "--mock",
    is_flag=True,
    help="Use MockEvaluator instead of Docker.",
)
def run_benchmark(
    dataset: str,
    context_mode: str,
    engagement_level: str,
    subset: int,
    workers: int,
    output_dir: str,
    run_id: str,
    mock: bool,
) -> None:
    """Run benchmark evaluation on AGENTBench instances."""
    from datetime import UTC, datetime

    from tapps_mcp.benchmark.config import load_benchmark_config
    from tapps_mcp.benchmark.models import ContextMode

    config = load_benchmark_config(
        overrides={
            "dataset_name": dataset,
            "context_mode": ContextMode(context_mode),
            "engagement_level": engagement_level,
            "subset_size": subset,
            "workers": workers,
            "output_dir": Path(output_dir),
        },
    )

    effective_run_id = run_id or datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")

    click.echo(f"Benchmark run: {effective_run_id}")
    click.echo(f"  Dataset: {config.dataset_name}")
    click.echo(f"  Context mode: {config.context_mode.value}")
    click.echo(f"  Engagement: {config.engagement_level}")
    click.echo(f"  Subset: {config.subset_size}")
    click.echo(f"  Workers: {config.workers}")
    click.echo()

    asyncio.run(
        _run_benchmark_async(config, effective_run_id, mock),
    )


async def _run_benchmark_async(
    config: Any,  # noqa: ANN401
    run_id: str,
    use_mock: bool,
) -> None:
    """Execute the benchmark pipeline asynchronously.

    Loads the dataset, evaluates all conditions via the mock or
    real evaluator, persists results, and prints a summary.
    """
    from tapps_mcp.benchmark.analyzer import ResultsAnalyzer
    from tapps_mcp.benchmark.dataset import DatasetLoader
    from tapps_mcp.benchmark.mock_evaluator import MockEvaluator
    from tapps_mcp.benchmark.models import ContextMode
    from tapps_mcp.benchmark.reporter import ResultsPersistence

    # Load dataset
    click.echo("Loading dataset...")
    loader = DatasetLoader(config)
    try:
        instances = await loader.load()
    except Exception as exc:
        click.echo(f"Error loading dataset: {exc}", err=True)
        sys.exit(1)
    click.echo(f"  Loaded {len(instances)} instances")

    # Resolve context modes to evaluate
    if config.context_mode is ContextMode.ALL:
        modes = [ContextMode.NONE, ContextMode.TAPPS, ContextMode.HUMAN]
    else:
        modes = [config.context_mode]

    # Build evaluator backend
    evaluator = MockEvaluator(seed=config.random_seed)
    if use_mock:
        click.echo("  Using MockEvaluator")
    else:
        # When a real Evaluator is available, import and use it.
        # For now, fall back to MockEvaluator with a warning.
        try:
            from tapps_mcp.benchmark.evaluator import (  # type: ignore[import-not-found]
                Evaluator as _RealEvaluator,
            )

            evaluator = _RealEvaluator(  # type: ignore[assignment]
                config=config,
            )
        except ImportError:
            click.echo(
                "  Warning: Evaluator not available, falling back to MockEvaluator",
            )

    # Evaluate each context mode
    persistence = ResultsPersistence(output_dir=config.output_dir)
    analyzer = ResultsAnalyzer()

    for mode in modes:
        click.echo(f"  Evaluating mode: {mode.value}...")
        results = await evaluator.evaluate_batch(
            instances,
            mode,
            config.engagement_level,
        )
        mode_run_id = f"{run_id}-{mode.value}"
        persistence.save_results(results, mode_run_id, config)
        summary = analyzer.aggregate(results)
        click.echo(
            f"    {mode.value}: {summary.resolution_rate:.1%} "
            f"({summary.resolved_count}/{summary.total_instances})",
        )

    click.echo(f"\nResults saved to {config.output_dir}/")


@benchmark_group.command("analyze")
@click.option(
    "--run-id",
    default="",
    help="Run ID to analyze (default: latest).",
)
@click.option(
    "--compare",
    default="",
    help="Comma-separated run IDs to compare.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "csv", "json"]),
    default="markdown",
    help="Output format.",
)
@click.option(
    "--output-dir",
    default=".tapps-mcp/benchmark/",
    help="Results directory.",
)
def analyze_results(
    run_id: str,
    compare: str,
    output_format: str,
    output_dir: str,
) -> None:
    """Analyze benchmark results and generate reports."""
    from tapps_mcp.benchmark.analyzer import ResultsAnalyzer
    from tapps_mcp.benchmark.reporter import (
        ReportGenerator,
        ResultsPersistence,
    )

    persistence = ResultsPersistence(output_dir=Path(output_dir))
    analyzer = ResultsAnalyzer()
    reporter = ReportGenerator()

    if compare:
        _analyze_compare(
            compare,
            persistence,
            analyzer,
            reporter,
            output_format,
        )
    else:
        _analyze_single(run_id, persistence, analyzer)


def _analyze_compare(
    compare: str,
    persistence: Any,  # noqa: ANN401
    analyzer: Any,  # noqa: ANN401
    reporter: Any,  # noqa: ANN401
    output_format: str,
) -> None:
    """Compare two benchmark runs."""
    run_ids = [r.strip() for r in compare.split(",")]
    if len(run_ids) != 2:  # noqa: PLR2004
        click.echo(
            "Error: --compare requires exactly 2 comma-separated run IDs",
            err=True,
        )
        sys.exit(1)

    try:
        baseline_results = persistence.load_results(run_ids[0])
        treatment_results = persistence.load_results(run_ids[1])
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    comparison = analyzer.compare_conditions(
        baseline_results,
        treatment_results,
    )

    if output_format == "markdown":
        click.echo(reporter.generate_markdown(comparison))
    elif output_format == "csv":
        click.echo(
            reporter.generate_csv(
                baseline_results + treatment_results,
            ),
        )
    else:
        click.echo(
            json.dumps(
                comparison.model_dump(),
                indent=2,
                default=str,
            ),
        )


def _analyze_single(
    run_id: str,
    persistence: Any,  # noqa: ANN401
    analyzer: Any,  # noqa: ANN401
) -> None:
    """Analyze a single benchmark run."""
    target_run = run_id
    if not target_run:
        runs = persistence.list_runs()
        if not runs:
            click.echo("No benchmark runs found.", err=True)
            sys.exit(1)
        target_run = runs[0].run_id

    try:
        results = persistence.load_results(target_run)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    summary = analyzer.aggregate(results)
    click.echo(f"Run: {target_run}")
    click.echo(f"  Instances: {summary.total_instances}")
    click.echo(f"  Resolved: {summary.resolved_count}")
    click.echo(f"  Resolution rate: {summary.resolution_rate:.1%}")
    click.echo(f"  Avg tokens: {summary.avg_tokens:.0f}")
    click.echo(f"  Avg cost: ${summary.avg_cost:.4f}")


@benchmark_group.command("report")
@click.option(
    "--output",
    "output_file",
    default="",
    help="Output file path (default: stdout).",
)
@click.option(
    "--output-dir",
    default=".tapps-mcp/benchmark/",
    help="Results directory.",
)
@click.option(
    "--include-redundancy",
    is_flag=True,
    help="Include redundancy analysis in report.",
)
def generate_report(
    output_file: str,
    output_dir: str,
    include_redundancy: bool,
) -> None:
    """Generate a summary report of all benchmark runs."""
    from tapps_mcp.benchmark.reporter import ResultsPersistence

    persistence = ResultsPersistence(output_dir=Path(output_dir))
    runs = persistence.list_runs()

    if not runs:
        click.echo("No benchmark runs found.", err=True)
        sys.exit(1)

    lines: list[str] = ["# TappsMCP Benchmark Report", ""]
    lines.append(f"Total runs: {len(runs)}")
    lines.append("")
    lines.append("| Run ID | Timestamp | Instances | Mode |")
    lines.append("|--------|-----------|-----------|------|")
    for run in runs:
        lines.append(
            f"| {run.run_id} | {run.timestamp[:19]} "
            f"| {run.instance_count} "
            f"| {run.context_mode.value} |",
        )

    if include_redundancy:
        lines.append("")
        lines.append(
            "*(Redundancy analysis requires per-run context data.)*",
        )

    report = "\n".join(lines)
    if output_file:
        Path(output_file).write_text(report, encoding="utf-8")
        click.echo(f"Report written to {output_file}")
    else:
        click.echo(report)


# ---------------------------------------------------------------------------
# Tool effectiveness CLI group (Epic 32)
# ---------------------------------------------------------------------------


@benchmark_group.group("tools")
def tools_group() -> None:
    """Tool effectiveness benchmarking commands."""


@tools_group.command("report")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--tools",
    "tool_list",
    default="",
    help="Comma-separated tool names (default: all).",
)
def tools_report(output_format: str, tool_list: str) -> None:
    """Generate a full tool effectiveness report."""
    asyncio.run(_tools_report_async(output_format, tool_list))


async def _tools_report_async(output_format: str, tool_list: str) -> None:
    """Run tool effectiveness report asynchronously."""
    from tapps_mcp.benchmark.call_patterns import CallPatternAnalyzer
    from tapps_mcp.benchmark.tool_evaluator import (
        _ALL_TOOL_NAMES,
        MockToolEvaluator,
        ToolImpactEvaluator,
    )
    from tapps_mcp.benchmark.tool_report import generate_tool_effectiveness_report
    from tapps_mcp.benchmark.tool_task_models import BUILTIN_TASKS

    tools = [t.strip() for t in tool_list.split(",") if t.strip()] if tool_list else _ALL_TOOL_NAMES

    click.echo(f"Evaluating {len(tools)} tools across {len(BUILTIN_TASKS)} tasks...")

    evaluator = ToolImpactEvaluator()
    mock = MockToolEvaluator()
    tool_report = await evaluator.evaluate_all_tools(tools, mock)

    # Collect results for call pattern analysis
    all_results = []
    for tool in tools:
        results = await evaluator.evaluate_tool_impact(tool, MockToolEvaluator())
        all_results.extend(results)

    pattern_analyzer = CallPatternAnalyzer()
    call_report = pattern_analyzer.analyze(all_results, BUILTIN_TASKS)

    report = generate_tool_effectiveness_report(
        tool_report,
        call_report,
        output_format=output_format,
    )
    click.echo(report)


@tools_group.command("rank")
def tools_rank() -> None:
    """Show tool effectiveness ranking."""
    asyncio.run(_tools_rank_async())


async def _tools_rank_async() -> None:
    """Run tool ranking asynchronously."""
    from tapps_mcp.benchmark.tool_evaluator import (
        _ALL_TOOL_NAMES,
        MockToolEvaluator,
        ToolImpactEvaluator,
    )

    click.echo("Computing tool rankings...")
    evaluator = ToolImpactEvaluator()
    mock = MockToolEvaluator()
    report = await evaluator.evaluate_all_tools(_ALL_TOOL_NAMES, mock)

    click.echo(f"\n{'Rank':<5} {'Tool':<30} {'Impact':>8} {'Helped':>8} {'Hurt':>6}")
    click.echo("-" * 60)
    for i, r in enumerate(report.tool_rankings, 1):
        click.echo(
            f"{i:<5} {r.tool_name:<30} "
            f"{r.impact_score:>+7.1%} "
            f"{r.tasks_helped:>8} "
            f"{r.tasks_hurt:>6}"
        )


@tools_group.command("calibrate")
@click.option(
    "--engagement-level",
    type=click.Choice(["high", "medium", "low"]),
    default="medium",
    show_default=True,
    help="Engagement level for calibration thresholds.",
)
def tools_calibrate(engagement_level: str) -> None:
    """Generate data-driven checklist tier calibration."""
    asyncio.run(_tools_calibrate_async(engagement_level))


async def _tools_calibrate_async(engagement_level: str) -> None:
    """Run calibration asynchronously."""
    from tapps_mcp.benchmark.call_patterns import CallPatternAnalyzer
    from tapps_mcp.benchmark.checklist_calibrator import ChecklistCalibrator
    from tapps_mcp.benchmark.tool_evaluator import (
        _ALL_TOOL_NAMES,
        MockToolEvaluator,
        ToolImpactEvaluator,
    )
    from tapps_mcp.benchmark.tool_task_models import BUILTIN_TASKS

    click.echo(f"Calibrating checklist tiers (engagement: {engagement_level})...")

    evaluator = ToolImpactEvaluator()
    mock = MockToolEvaluator()
    tool_report = await evaluator.evaluate_all_tools(_ALL_TOOL_NAMES, mock)

    # Get call patterns
    all_results = []
    for tool in _ALL_TOOL_NAMES:
        results = await evaluator.evaluate_tool_impact(tool, MockToolEvaluator())
        all_results.extend(results)

    pattern_analyzer = CallPatternAnalyzer()
    call_report = pattern_analyzer.analyze(all_results, BUILTIN_TASKS)

    calibrator = ChecklistCalibrator()
    calibration = calibrator.calibrate_tiers(
        tool_report.tool_rankings,
        call_report,
        engagement_level,
    )

    click.echo(f"\n{'Tool':<30} {'Impact':>8} {'Freq':>6} {'Tier':>12} {'Change':>10}")
    click.echo("-" * 70)
    for c in calibration.classifications:
        click.echo(
            f"{c.tool_name:<30} "
            f"{c.measured_impact:>+7.1%} "
            f"{c.call_frequency:>5.0%} "
            f"{c.recommended_tier:>12} "
            f"{c.tier_change or '':>10}"
        )

    required = sum(1 for c in calibration.classifications if c.recommended_tier == "required")
    recommended = sum(1 for c in calibration.classifications if c.recommended_tier == "recommended")
    optional = sum(1 for c in calibration.classifications if c.recommended_tier == "optional")
    click.echo(f"\nSummary: {required} required, {recommended} recommended, {optional} optional")


# ---------------------------------------------------------------------------
# Template optimization CLI group (Epic 31)
# ---------------------------------------------------------------------------


@click.group("template")
def template_group() -> None:
    """Template optimization and version management commands."""


@template_group.command("optimize")
@click.option(
    "--engagement-level",
    type=click.Choice(["high", "medium", "low"]),
    default="medium",
    show_default=True,
    help="Engagement level to optimize.",
)
@click.option(
    "--repo-path",
    default=".",
    show_default=True,
    help="Repository path for redundancy analysis.",
)
@click.option(
    "--db-path",
    default=".tapps-mcp/benchmark/template_versions.db",
    show_default=True,
    help="Template versions database path.",
)
@click.option(
    "--mock",
    is_flag=True,
    help="Use MockEvaluator instead of Docker.",
)
def template_optimize(
    engagement_level: str,
    repo_path: str,
    db_path: str,
    mock: bool,
) -> None:
    """Run the template optimization pipeline.

    Analyzes the current template for redundancy, records a new version,
    evaluates via benchmarks, and recommends improvements.
    """
    from tapps_mcp.benchmark.redundancy import RedundancyAnalyzerV2
    from tapps_mcp.benchmark.template_versions import TemplateVersionStore
    from tapps_mcp.prompts.prompt_loader import load_agents_template

    template = load_agents_template(engagement_level)
    repo = Path(repo_path).resolve()
    store = TemplateVersionStore(db_path=Path(db_path))

    try:
        # Record version
        version = store.record_version(
            content=template,
            engagement_level=engagement_level,
            metadata={"source": "optimize-cli"},
        )
        click.echo(f"Recorded template version {version.version}")
        click.echo(f"  Hash: {version.content_hash[:12]}...")
        click.echo(f"  Level: {engagement_level}")

        # Redundancy analysis
        analyzer = RedundancyAnalyzerV2()
        report = analyzer.analyze_template_redundancy(template, repo)

        store.record_scores(
            version=version.version,
            redundancy_score=report.overall_score,
            section_scores={s.section_name: s.redundancy_score for s in report.sections},
        )

        click.echo("\nRedundancy analysis:")
        click.echo(f"  Overall score: {report.overall_score:.2%}")
        click.echo(f"  Sections: {report.total_sections}")
        click.echo(f"  To remove: {report.sections_to_remove}")
        click.echo(f"  To reduce: {report.sections_to_reduce}")

        for section in report.sections:
            marker = {"keep": " ", "reduce": "~", "remove": "x"}
            icon = marker.get(section.recommendation, "?")
            click.echo(
                f"  [{icon}] {section.section_name}: "
                f"{section.redundancy_score:.2%} "
                f"({section.recommendation})"
            )

        if mock:
            click.echo("\nBenchmark evaluation (mock)...")
            asyncio.run(_run_template_benchmark(version, store, engagement_level))
        else:
            click.echo("\nSkipping benchmark evaluation (use --mock for mock evaluation).")
    finally:
        store.close()


async def _run_template_benchmark(
    version: Any,  # noqa: ANN401
    store: Any,  # noqa: ANN401
    engagement_level: str,
) -> None:
    """Run mock benchmark evaluation for a template version."""
    from tapps_mcp.benchmark.analyzer import ResultsAnalyzer
    from tapps_mcp.benchmark.config import load_benchmark_config
    from tapps_mcp.benchmark.mock_evaluator import MockEvaluator
    from tapps_mcp.benchmark.models import ContextMode

    config = load_benchmark_config(
        overrides={
            "engagement_level": engagement_level,
            "context_mode": ContextMode.TAPPS,
            "subset_size": 20,
        },
    )

    from tapps_mcp.benchmark.dataset import DatasetLoader

    loader = DatasetLoader(config)
    try:
        instances = await loader.load()
    except Exception as exc:
        click.echo(f"  Error loading dataset: {exc}", err=True)
        return

    evaluator = MockEvaluator(seed=config.random_seed)
    results = await evaluator.evaluate_batch(
        instances,
        ContextMode.TAPPS,
        engagement_level,
    )

    analyzer = ResultsAnalyzer()
    summary = analyzer.aggregate(results)

    store.record_scores(
        version=version.version,
        benchmark_scores=summary,
    )

    click.echo(
        f"  Resolution: {summary.resolution_rate:.1%} "
        f"({summary.resolved_count}/{summary.total_instances})"
    )
    click.echo(f"  Avg tokens: {summary.avg_tokens:.0f}")
    click.echo(f"  Avg cost: ${summary.avg_cost:.4f}")


@template_group.command("ablate")
@click.option(
    "--engagement-level",
    type=click.Choice(["high", "medium", "low"]),
    default="medium",
    show_default=True,
    help="Engagement level of the template to ablate.",
)
@click.option(
    "--subset",
    default=20,
    type=int,
    show_default=True,
    help="Number of benchmark instances.",
)
def template_ablate(
    engagement_level: str,
    subset: int,
) -> None:
    """Run section ablation analysis on a template.

    Removes each section one at a time and measures the impact
    on benchmark resolution rate.
    """
    from tapps_mcp.prompts.prompt_loader import load_agents_template

    template = load_agents_template(engagement_level)

    # Extract section names
    section_names = [
        line.lstrip("#").strip() for line in template.split("\n") if line.startswith("## ")
    ]

    if not section_names:
        click.echo("No sections found in template.", err=True)
        sys.exit(1)

    click.echo(f"Template sections ({len(section_names)}):")
    for name in section_names:
        click.echo(f"  - {name}")

    click.echo(f"\nRunning ablation with {subset} instances (mock)...")
    asyncio.run(
        _run_ablation_async(template, section_names, engagement_level, subset),
    )


async def _run_ablation_async(
    template: str,
    sections: list[str],
    engagement_level: str,
    subset: int,
) -> None:
    """Run ablation analysis asynchronously."""
    from tapps_mcp.benchmark.ablation import AblationConfig, AblationRunner
    from tapps_mcp.benchmark.config import load_benchmark_config
    from tapps_mcp.benchmark.mock_evaluator import MockEvaluator
    from tapps_mcp.benchmark.models import ContextMode

    config = load_benchmark_config(
        overrides={
            "engagement_level": engagement_level,
            "context_mode": ContextMode.TAPPS,
            "subset_size": subset,
        },
    )

    ablation_config = AblationConfig(
        base_template=template,
        sections=sections,
        benchmark_config=config,
    )

    runner = AblationRunner()
    evaluator = MockEvaluator(seed=config.random_seed)
    results = await runner.run_ablation(ablation_config, evaluator)

    click.echo("\nAblation results:")
    click.echo(f"{'Section':<30} {'Rate':>8} {'Delta':>8} {'Class':>10}")
    click.echo("-" * 60)
    for r in results:
        click.echo(
            f"{r.removed_section:<30} "
            f"{r.resolution_rate:>7.1%} "
            f"{r.delta_vs_full:>+7.1%} "
            f"{r.recommendation:>10}"
        )

    essential = [r for r in results if r.recommendation == "essential"]
    harmful = [r for r in results if r.recommendation == "harmful"]
    neutral = [r for r in results if r.recommendation == "neutral"]

    click.echo(
        f"\nSummary: {len(essential)} essential, {len(neutral)} neutral, {len(harmful)} harmful"
    )


@template_group.command("compare")
@click.argument("version_a", type=int)
@click.argument("version_b", type=int)
@click.option(
    "--db-path",
    default=".tapps-mcp/benchmark/template_versions.db",
    show_default=True,
    help="Template versions database path.",
)
def template_compare(
    version_a: int,
    version_b: int,
    db_path: str,
) -> None:
    """Compare two template versions."""
    from tapps_mcp.benchmark.template_versions import TemplateVersionStore

    db = Path(db_path)
    if not db.exists():
        click.echo(f"Database not found: {db_path}", err=True)
        sys.exit(1)

    store = TemplateVersionStore(db_path=db)
    try:
        comparison = store.compare(version_a, version_b)

        if "error" in comparison:
            click.echo(f"Error: {comparison['error']}", err=True)
            sys.exit(1)

        click.echo(f"Template comparison: v{version_a} vs v{version_b}")
        click.echo(f"  Same content: {comparison['same_content']}")
        click.echo(f"  Level A: {comparison['engagement_level_a']}")
        click.echo(f"  Level B: {comparison['engagement_level_b']}")

        if comparison.get("resolution_rate_a") is not None:
            click.echo(f"  Resolution A: {comparison['resolution_rate_a']:.1%}")
        if comparison.get("resolution_rate_b") is not None:
            click.echo(f"  Resolution B: {comparison['resolution_rate_b']:.1%}")
        if comparison.get("resolution_delta") is not None:
            click.echo(f"  Resolution delta: {comparison['resolution_delta']:+.1%}")

        if comparison.get("redundancy_score_a") is not None:
            click.echo(f"  Redundancy A: {comparison['redundancy_score_a']:.2%}")
        if comparison.get("redundancy_score_b") is not None:
            click.echo(f"  Redundancy B: {comparison['redundancy_score_b']:.2%}")
        if comparison.get("redundancy_delta") is not None:
            click.echo(f"  Redundancy delta: {comparison['redundancy_delta']:+.2%}")
    finally:
        store.close()


@template_group.command("history")
@click.option(
    "--engagement-level",
    type=click.Choice(["high", "medium", "low"]),
    default="medium",
    show_default=True,
    help="Engagement level to query.",
)
@click.option(
    "--limit",
    default=10,
    type=int,
    show_default=True,
    help="Maximum versions to show.",
)
@click.option(
    "--db-path",
    default=".tapps-mcp/benchmark/template_versions.db",
    show_default=True,
    help="Template versions database path.",
)
def template_history(
    engagement_level: str,
    limit: int,
    db_path: str,
) -> None:
    """Show template version history."""
    from tapps_mcp.benchmark.template_versions import TemplateVersionStore

    db = Path(db_path)
    if not db.exists():
        click.echo(f"Database not found: {db_path}", err=True)
        sys.exit(1)

    store = TemplateVersionStore(db_path=db)
    try:
        versions = store.get_history(engagement_level, limit=limit)

        if not versions:
            click.echo(f"No versions found for engagement level '{engagement_level}'.")
            return

        click.echo(f"Template history ({engagement_level}, showing {len(versions)}/{limit} max):")
        click.echo()
        click.echo(
            f"{'Ver':>4} {'Hash':>14} {'Created':>20} {'Rate':>8} {'Redund':>8} {'Promoted':>9}"
        )
        click.echo("-" * 70)

        for v in versions:
            rate_str = f"{v.benchmark_scores.resolution_rate:.1%}" if v.benchmark_scores else "  -"
            redund_str = f"{v.redundancy_score:.2%}" if v.redundancy_score is not None else "  -"
            promoted_str = "yes" if v.promoted else "no"

            click.echo(
                f"{v.version:>4} "
                f"{v.content_hash[:12]:>14} "
                f"{v.created_at[:19]:>20} "
                f"{rate_str:>8} "
                f"{redund_str:>8} "
                f"{promoted_str:>9}"
            )

        # Show best version
        best = store.get_best(engagement_level)
        if best and best.benchmark_scores:
            click.echo(
                f"\nBest: v{best.version} ({best.benchmark_scores.resolution_rate:.1%} resolution)"
            )
    finally:
        store.close()
