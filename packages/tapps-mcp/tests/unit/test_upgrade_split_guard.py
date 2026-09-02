"""Regrowth guard for the ``pipeline/upgrade.py`` decomposition (TAP-6913).

TAP-611 split this module once and the split did not hold: by TAP-6913
``upgrade.py`` was back to ~2,700 lines scoring 51.99 against the repo's 70
gate, with ``upgrade_pipeline`` at cyclomatic complexity 52. Nothing in the
suite noticed, because the quality gate only scores *changed* files and each
individual commit that grew the file was small.

These assertions are the missing feedback. They are size/shape budgets, not
style preferences — a change that trips one is a signal to extract a new leaf
module (or extend an existing one), not to raise the number. Raising a ceiling
is a deliberate decision that belongs in a commit of its own, with the reason
written down.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from radon.complexity import cc_visit

PIPELINE_DIR = Path(__file__).resolve().parents[2] / "src" / "tapps_mcp" / "pipeline"

# The facade: docstring, orchestration, and the backwards-compatible aliases.
# Sized so the orchestrator plus its module map fits, and a re-inlined
# component does not.
UPGRADE_FACADE_MAX_LINES = 750

# Any single leaf module. The repo's own scorer drops maintainability sharply
# past this, which is exactly how the pre-TAP-6913 megafile reached MI 0.00.
LEAF_MODULE_MAX_LINES = 900

# TAP-6913 acceptance: the orchestrator must stay comprehensible at a glance.
UPGRADE_PIPELINE_MAX_COMPLEXITY = 15

# The leaves the facade delegates to. Losing one means work moved back into
# ``upgrade.py`` — the exact regression this file exists to catch.
EXPECTED_LEAF_MODULES = (
    "upgrade_backup.py",
    "upgrade_content_return.py",
    "upgrade_docs.py",
    "upgrade_github.py",
    "upgrade_hooks_migration.py",
    "upgrade_host_claude.py",
    "upgrade_host_context.py",
    "upgrade_host_cursor.py",
    "upgrade_hosts.py",
    "upgrade_mcp_config.py",
    "upgrade_report.py",
    "upgrade_signals.py",
    "upgrade_skip_tokens.py",
)


# Reached through ``upgrade_hosts.py`` rather than directly from the facade.
_DISPATCHED_LEAF_MODULES = frozenset(
    {"upgrade_host_claude.py", "upgrade_host_context.py", "upgrade_host_cursor.py"}
)


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


class TestModuleSizeBudget:
    def test_upgrade_facade_stays_under_its_ceiling(self) -> None:
        path = PIPELINE_DIR / "upgrade.py"
        count = _line_count(path)
        assert count <= UPGRADE_FACADE_MAX_LINES, (
            f"pipeline/upgrade.py is {count} lines (ceiling "
            f"{UPGRADE_FACADE_MAX_LINES}). The TAP-611 split regrew once; "
            f"extract a leaf module rather than raising this number."
        )

    @pytest.mark.parametrize("module_name", EXPECTED_LEAF_MODULES)
    def test_leaf_module_stays_under_its_ceiling(self, module_name: str) -> None:
        path = PIPELINE_DIR / module_name
        assert path.is_file(), (
            f"{module_name} is missing — the upgrade pipeline's decomposition "
            f"(TAP-6913) lost a leaf. Work has moved back into upgrade.py."
        )
        count = _line_count(path)
        assert count <= LEAF_MODULE_MAX_LINES, (
            f"pipeline/{module_name} is {count} lines (ceiling "
            f"{LEAF_MODULE_MAX_LINES}); split it rather than raising this number."
        )


class TestOrchestratorComplexity:
    """``upgrade_pipeline`` was cyclomatic complexity 52 before TAP-6913."""

    def test_upgrade_pipeline_complexity_is_bounded(self) -> None:
        source = (PIPELINE_DIR / "upgrade.py").read_text(encoding="utf-8")
        blocks = {block.name: block.complexity for block in cc_visit(source)}
        assert "upgrade_pipeline" in blocks
        assert blocks["upgrade_pipeline"] < UPGRADE_PIPELINE_MAX_COMPLEXITY, (
            f"upgrade_pipeline complexity is {blocks['upgrade_pipeline']} "
            f"(ceiling {UPGRADE_PIPELINE_MAX_COMPLEXITY - 1}); move a stage into "
            f"its own function or module."
        )

    def test_no_upgrade_module_function_exceeds_the_ceiling(self) -> None:
        """A leaf module is not a place to hide the complexity that was extracted."""
        offenders: list[str] = []
        for path in sorted(PIPELINE_DIR.glob("upgrade*.py")):
            source = path.read_text(encoding="utf-8")
            offenders.extend(
                f"{path.name}::{block.name} ({block.complexity})"
                for block in cc_visit(source)
                if block.complexity >= UPGRADE_PIPELINE_MAX_COMPLEXITY
            )
        assert not offenders, f"complexity ceiling breached: {', '.join(offenders)}"


class TestPublicSurfaceSurvivesTheSplit:
    """Consumers (and the existing suite) import these private names from the facade."""

    HISTORICAL_ALIASES = (
        "_ALL_SKIP_TOKENS",
        "_CANONICAL_HOOK_MANIFEST",
        "_SKIP_TOKENS",
        "_agents_md_opt_out",
        "_apply_or_skip",
        "_build_upgrade_manifest",
        "_collect_upgrade_targets",
        "_detect_platform",
        "_dry_run_status",
        "_has_infra_signals",
        "_has_python_signals",
        "_mcp_json_has_tapps_entry",
        "_migrate_retired_hooks",
        "_refresh_karpathy_blocks",
        "_skipped",
        "_upgrade_agents_md_content_return",
        "_upgrade_content_return",
        "_upgrade_platform",
        "_upgrade_platform_content_return",
        "upgrade_pipeline",
    )

    def test_facade_still_exports_the_historical_names(self) -> None:
        from tapps_mcp.pipeline import upgrade

        missing = [name for name in self.HISTORICAL_ALIASES if not hasattr(upgrade, name)]
        assert not missing, f"pipeline/upgrade.py no longer re-exports: {missing}"

    def test_bump_versions_can_still_find_the_hook_manifest(self) -> None:
        """``scripts/bump_versions.py`` locates the manifest by regex, not import.

        It globs ``upgrade*.py`` for a ``CANONICAL_HOOK_MANIFEST`` assignment, so
        moving the manifest again is fine — deleting the literal is not.
        """
        found = [
            path.name
            for path in sorted(PIPELINE_DIR.glob("upgrade*.py"))
            if "CANONICAL_HOOK_MANIFEST: frozenset[str] = frozenset(" in path.read_text("utf-8")
        ]
        assert len(found) == 1, f"expected exactly one manifest definition, found {found}"


class TestFacadeDelegates:
    """The facade must import its leaves, not re-implement them."""

    def test_upgrade_imports_every_expected_leaf(self) -> None:
        tree = ast.parse((PIPELINE_DIR / "upgrade.py").read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        expected = {
            f"tapps_mcp.pipeline.{name.removesuffix('.py')}"
            for name in EXPECTED_LEAF_MODULES
            if name not in _DISPATCHED_LEAF_MODULES
        }
        assert expected <= imported, f"facade stopped importing: {sorted(expected - imported)}"

    def test_dispatcher_imports_every_per_host_module(self) -> None:
        tree = ast.parse((PIPELINE_DIR / "upgrade_hosts.py").read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        expected = {
            f"tapps_mcp.pipeline.{name.removesuffix('.py')}" for name in _DISPATCHED_LEAF_MODULES
        }
        assert expected <= imported, (
            f"upgrade_hosts.py stopped importing: {sorted(expected - imported)}"
        )
