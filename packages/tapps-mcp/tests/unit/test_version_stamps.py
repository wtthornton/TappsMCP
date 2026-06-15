"""Tests for version stamp bump helpers."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.version_stamps import bump_stamp_if_stale, read_stamp, rewrite_stamp


def test_bump_stamp_if_stale_updates_file(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("<!-- tapps-agents-version: 1.0.0 -->\n# AGENTS\n", encoding="utf-8")

    result = bump_stamp_if_stale(path, "tapps-agents-version", "2.0.0", dry_run=False)

    assert result["action"] == "bumped-stamp"
    assert read_stamp(path, "tapps-agents-version") == "2.0.0"


def test_bump_stamp_if_stale_unchanged_when_current(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("<!-- tapps-agents-version: 2.0.0 -->\n", encoding="utf-8")

    result = bump_stamp_if_stale(path, "tapps-agents-version", "2.0.0", dry_run=False)

    assert result["action"] == "unchanged"


def test_rewrite_stamp_raises_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("# no stamp\n", encoding="utf-8")
    try:
        rewrite_stamp(path, "tapps-agents-version", "2.0.0")
    except ValueError as exc:
        assert "tapps-agents-version" in str(exc)
    else:
        raise AssertionError("expected ValueError")
