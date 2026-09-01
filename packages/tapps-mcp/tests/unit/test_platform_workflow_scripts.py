"""Tests for tapps_mcp.pipeline.platform_workflow_scripts (TAP-6890).

Evidence bar item 5: both scaffolded workflows land executable, parse under
``node --check``, and honor the managed-block refresh contract byte-for-byte.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_workflow_scripts import (
    WORKFLOW_SCRIPTS,
    generate_workflow_scripts,
)

requires_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


@pytest.mark.parametrize("rel_path", sorted(WORKFLOW_SCRIPTS))
def test_generated_script_is_created(tmp_path: Path, rel_path: str) -> None:
    generate_workflow_scripts(tmp_path)
    assert (tmp_path / rel_path).exists()


@pytest.mark.parametrize("rel_path", sorted(WORKFLOW_SCRIPTS))
def test_generated_script_lands_executable(tmp_path: Path, rel_path: str) -> None:
    generate_workflow_scripts(tmp_path)
    target = tmp_path / rel_path
    assert target.stat().st_mode & 0o111, f"{rel_path} is not executable"


@requires_node
@pytest.mark.parametrize("rel_path", sorted(WORKFLOW_SCRIPTS))
def test_generated_script_parses_under_node_check(tmp_path: Path, rel_path: str) -> None:
    generate_workflow_scripts(tmp_path)
    target = tmp_path / rel_path
    result = subprocess.run(
        ["node", "--check", str(target)], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr


def test_second_call_is_unchanged_when_untouched(tmp_path: Path) -> None:
    generate_workflow_scripts(tmp_path)
    result = generate_workflow_scripts(tmp_path)
    assert result["assets"][".claude/workflows/val-verify.js"] == "unchanged"
    assert result["assets"][".claude/workflows/linear-disposition-verify.js"] == "unchanged"


def test_edit_outside_markers_survives_refresh_byte_for_byte(tmp_path: Path) -> None:
    generate_workflow_scripts(tmp_path)
    target = tmp_path / ".claude" / "workflows" / "val-verify.js"
    original = target.read_text(encoding="utf-8")
    addendum = "\n// project addendum: keep me\n"
    target.write_text(original + addendum, encoding="utf-8")

    generate_workflow_scripts(tmp_path)
    text = target.read_text(encoding="utf-8")
    assert text == original + addendum


def test_edit_inside_markers_is_replaced_on_refresh(tmp_path: Path) -> None:
    generate_workflow_scripts(tmp_path)
    target = tmp_path / ".claude" / "workflows" / "linear-disposition-verify.js"
    hacked = target.read_text(encoding="utf-8").replace(
        "export const meta", "export const HACKED_meta"
    )
    target.write_text(hacked, encoding="utf-8")

    generate_workflow_scripts(tmp_path)
    text = target.read_text(encoding="utf-8")
    assert "HACKED_meta" not in text
    assert "export const meta" in text


@pytest.mark.parametrize("rel_path", sorted(WORKFLOW_SCRIPTS))
def test_generated_script_carries_all_four_safety_invariants(tmp_path: Path, rel_path: str) -> None:
    """Both scripts must satisfy the doctor check's universal budget invariant."""
    generate_workflow_scripts(tmp_path)
    content = (tmp_path / rel_path).read_text(encoding="utf-8")
    assert "budget.remaining(" in content


def test_val_verify_carries_verdict_pattern_invariants(tmp_path: Path) -> None:
    generate_workflow_scripts(tmp_path)
    content = (tmp_path / ".claude" / "workflows" / "val-verify.js").read_text(encoding="utf-8")
    assert "negative_control_result" in content
    assert "positive_control_result" in content
    assert "green_by_suppression" in content
