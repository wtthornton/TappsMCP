"""Tests for tapps_upgrade dry-run: three states for managed root files.

TAP-2201: ``upgrade_pipeline(dry_run=True)`` must distinguish three states
for files in MANAGED_GITHUB_ROOT_FILES (e.g. ``PULL_REQUEST_TEMPLATE.md``):

1. **Fresh project** — file absent because tapps was never initialised.
   ``would_recreate_deleted_files`` stays empty; safe-to-run verdict unchanged.
2. **Outdated baseline** — file exists with old content; it will be overwritten.
   ``would_recreate_deleted_files`` stays empty (file is present, not deleted).
3. **Deliberately deleted** — established project (AGENTS.md exists) where the
   consumer removed the file.  ``would_recreate_deleted_files`` flags it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tapps_mcp.pipeline.upgrade import upgrade_pipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_project(tmp_path: Path) -> None:
    """Create the minimal directory structure tapps_upgrade expects."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / ".tapps-mcp.yaml").write_text("{}\n", encoding="utf-8")
    (tmp_path / ".claude").mkdir()


def _run_dry(tmp_path: Path) -> dict[str, Any]:
    return upgrade_pipeline(project_root=tmp_path, dry_run=True)  # type: ignore[arg-type]


def _github_templates(result: dict[str, Any]) -> dict[str, Any]:
    return result["components"].get("github_templates", {})


def _would_recreate(result: dict[str, Any]) -> list[dict[str, str]]:
    return _github_templates(result).get("would_recreate_deleted_files", [])


def _summary_would_recreate(result: dict[str, Any]) -> list[dict[str, str]]:
    return result.get("dry_run_summary", {}).get("would_recreate_deleted_files", [])


# ---------------------------------------------------------------------------
# State 1: fresh project (AGENTS.md absent)
# ---------------------------------------------------------------------------


class TestFreshProject:
    """No AGENTS.md → never initialised → would_recreate_deleted_files is empty."""

    def test_no_agents_md_gives_empty_would_recreate(self, tmp_path: Path) -> None:
        # Fresh project: no AGENTS.md, no .github/
        (tmp_path / ".tapps-mcp.yaml").write_text("{}\n", encoding="utf-8")
        (tmp_path / ".claude").mkdir()

        result = _run_dry(tmp_path)

        assert _would_recreate(result) == []

    def test_summary_would_recreate_empty_for_fresh_project(self, tmp_path: Path) -> None:
        (tmp_path / ".tapps-mcp.yaml").write_text("{}\n", encoding="utf-8")
        (tmp_path / ".claude").mkdir()

        result = _run_dry(tmp_path)

        assert _summary_would_recreate(result) == []

    def test_would_recreate_not_in_review_flags(self, tmp_path: Path) -> None:
        """would_recreate_deleted_files must never add to review_recommended_for."""
        (tmp_path / ".tapps-mcp.yaml").write_text("{}\n", encoding="utf-8")
        (tmp_path / ".claude").mkdir()

        result = _run_dry(tmp_path)

        summary = result.get("dry_run_summary", {})
        # Absent managed files are informational — they must not add a new
        # review_recommended_for entry of their own.
        review_for = summary.get("review_recommended_for", [])
        assert "github_templates" not in review_for


# ---------------------------------------------------------------------------
# State 2: outdated baseline — file exists (would be overwritten)
# ---------------------------------------------------------------------------


class TestOutdatedBaseline:
    """Managed file exists → not deleted → would_recreate_deleted_files is empty."""

    def test_existing_pr_template_not_flagged(self, tmp_path: Path) -> None:
        _seed_project(tmp_path)
        github_dir = tmp_path / ".github"
        github_dir.mkdir(parents=True, exist_ok=True)
        (github_dir / "PULL_REQUEST_TEMPLATE.md").write_text("## PR\n", encoding="utf-8")

        result = _run_dry(tmp_path)

        flagged_files = [e["file"] for e in _would_recreate(result)]
        assert ".github/PULL_REQUEST_TEMPLATE.md" not in flagged_files


# ---------------------------------------------------------------------------
# State 3: deliberately deleted — AGENTS.md present, managed file absent
# ---------------------------------------------------------------------------


class TestDeliberatelyDeleted:
    """Established project (AGENTS.md exists) + managed file absent → flagged."""

    def test_missing_pr_template_flagged(self, tmp_path: Path) -> None:
        _seed_project(tmp_path)
        # .github/ exists but PULL_REQUEST_TEMPLATE.md was deleted.
        (tmp_path / ".github").mkdir(parents=True, exist_ok=True)

        result = _run_dry(tmp_path)

        flagged = _would_recreate(result)
        flagged_files = [e["file"] for e in flagged]
        assert ".github/PULL_REQUEST_TEMPLATE.md" in flagged_files

    def test_entry_includes_upgrade_skip_hint(self, tmp_path: Path) -> None:
        _seed_project(tmp_path)
        (tmp_path / ".github").mkdir(parents=True, exist_ok=True)

        result = _run_dry(tmp_path)

        flagged = _would_recreate(result)
        assert flagged, "expected at least one entry"
        note = flagged[0]["note"]
        assert "upgrade_skip_files" in note

    def test_summary_rollup_contains_deleted_files(self, tmp_path: Path) -> None:
        _seed_project(tmp_path)
        (tmp_path / ".github").mkdir(parents=True, exist_ok=True)

        result = _run_dry(tmp_path)

        summary_recreate = _summary_would_recreate(result)
        flagged_files = [e["file"] for e in summary_recreate]
        assert ".github/PULL_REQUEST_TEMPLATE.md" in flagged_files

    def test_deleted_files_not_in_review_flags(self, tmp_path: Path) -> None:
        """would_recreate_deleted_files must not add github_templates to review_recommended_for."""
        _seed_project(tmp_path)
        (tmp_path / ".github").mkdir(parents=True, exist_ok=True)

        result = _run_dry(tmp_path)

        summary = result.get("dry_run_summary", {})
        # Informational only — must not escalate to review-recommended on its own.
        review_for = summary.get("review_recommended_for", [])
        assert "github_templates" not in review_for
        # But the would_recreate key must still be populated.
        assert _summary_would_recreate(result), "expected entries in summary rollup"

    def test_all_managed_root_files_covered(self, tmp_path: Path) -> None:
        """Every entry in MANAGED_GITHUB_ROOT_FILES is checked."""
        from tapps_mcp.pipeline.github_templates import MANAGED_GITHUB_ROOT_FILES

        _seed_project(tmp_path)
        # .github/ exists but all managed root files are absent.
        (tmp_path / ".github").mkdir(parents=True, exist_ok=True)

        result = _run_dry(tmp_path)

        flagged_files = {e["file"] for e in _would_recreate(result)}
        for fname in MANAGED_GITHUB_ROOT_FILES:
            assert f".github/{fname}" in flagged_files, f"{fname} not flagged"
