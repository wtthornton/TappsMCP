"""Tests for the .claude/workflows/ asset group wired into upgrade_pipeline (TAP-6890)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.upgrade import upgrade_pipeline


def _setup_claude_project(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)


def test_workflow_scripts_created_on_live_upgrade(tmp_path: Path) -> None:
    _setup_claude_project(tmp_path)
    result = upgrade_pipeline(tmp_path, platform="claude")
    assert result["success"] is True

    workflows_dir = tmp_path / ".claude" / "workflows"
    assert (workflows_dir / "val-verify.js").exists()
    assert (workflows_dir / "linear-disposition-verify.js").exists()

    claude_result = result["components"]["platforms"][0]
    workflows_info = claude_result["components"]["workflows"]
    assert workflows_info["assets"][".claude/workflows/val-verify.js"] == "created"
    assert workflows_info["assets"][".claude/workflows/linear-disposition-verify.js"] == "created"


def test_workflow_scripts_skipped_via_skip_token(tmp_path: Path) -> None:
    _setup_claude_project(tmp_path)
    (tmp_path / ".tapps-mcp.yaml").write_text(
        "upgrade_skip_files:\n  - .claude/workflows\n", encoding="utf-8"
    )

    result = upgrade_pipeline(tmp_path, platform="claude")
    assert not (tmp_path / ".claude" / "workflows").exists()

    claude_result = result["components"]["platforms"][0]
    assert claude_result["components"]["workflows"] == "skipped (upgrade_skip_files)"


def test_workflow_scripts_dry_run_reports_would_write(tmp_path: Path) -> None:
    _setup_claude_project(tmp_path)
    result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
    assert not (tmp_path / ".claude" / "workflows").exists()

    claude_result = result["components"]["platforms"][0]
    workflows_info = claude_result["components"]["workflows"]
    assert workflows_info["action"] == "would-write-managed-files"
    assert ".claude/workflows/val-verify.js" in workflows_info["managed_files"]
    assert ".claude/workflows/linear-disposition-verify.js" in workflows_info["managed_files"]


def test_workflow_scripts_edit_outside_markers_survives_second_upgrade(tmp_path: Path) -> None:
    _setup_claude_project(tmp_path)
    upgrade_pipeline(tmp_path, platform="claude")

    target = tmp_path / ".claude" / "workflows" / "val-verify.js"
    original = target.read_text(encoding="utf-8")
    addendum = "\n// project addendum: keep me\n"
    target.write_text(original + addendum, encoding="utf-8")

    upgrade_pipeline(tmp_path, platform="claude")
    assert target.read_text(encoding="utf-8") == original + addendum
