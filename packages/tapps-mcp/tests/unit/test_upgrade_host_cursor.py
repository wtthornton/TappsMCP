"""Tests for the Cursor pipeline-rule dedup and retirement (TAP-6440).

Two writers used to emit a Cursor pipeline rule: ``_bootstrap_cursor``
(``.cursor/rules/tapps-pipeline.md``) and ``generate_cursor_rules`` via
``platform_rules.CURSOR_RULE_TEMPLATES`` (``.cursor/rules/tapps-pipeline.mdc``).
Cursor only loads ``.mdc`` frontmatter rule files, so ``.mdc`` is canonical;
``generate_cursor_rules`` no longer writes a pipeline entry, and
``upgrade_cursor`` removes the retired ``.md`` file from consumers.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.upgrade_hosts import upgrade_platform


def test_upgrade_writes_no_duplicate_pipeline_rule(tmp_path: Path) -> None:
    """``tapps_upgrade`` emits exactly one Cursor pipeline rule file."""
    upgrade_platform("cursor", tmp_path, force=True)

    rules_dir = tmp_path / ".cursor" / "rules"
    pipeline_rule_files = [
        p for p in rules_dir.iterdir() if p.stem == "tapps-pipeline"
    ]
    assert [p.name for p in pipeline_rule_files] == ["tapps-pipeline.mdc"]


def test_upgrade_removes_retired_pipeline_rule_from_consumers(tmp_path: Path) -> None:
    """A consumer left with the retired ``.md`` copy has it removed by upgrade."""
    rules_dir = tmp_path / ".cursor" / "rules"
    rules_dir.mkdir(parents=True)
    retired = rules_dir / "tapps-pipeline.md"
    retired.write_text("# stale pipeline rule\n", encoding="utf-8")

    result = upgrade_platform("cursor", tmp_path, force=True)

    assert not retired.exists()
    assert (rules_dir / "tapps-pipeline.mdc").exists()
    assert result["components"]["cursor_rules"]["retired_tapps-pipeline.md"] == "removed"
