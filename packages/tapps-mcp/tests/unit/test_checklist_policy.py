"""Tests for optional checklist-policy.yaml merge."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.tools.checklist import _ENGAGEMENT_TOOL_MAP
from tapps_mcp.tools.checklist_policy import (
    load_checklist_policy_extras,
    merge_engagement_maps,
)


def test_merge_adds_extra_required(tmp_path: Path) -> None:
    p = tmp_path / ".tapps-mcp"
    p.mkdir()
    (p / "checklist-policy.yaml").write_text(
        "extra_required:\n  feature:\n    - tapps_dependency_scan\n",
        encoding="utf-8",
    )
    extras = load_checklist_policy_extras(tmp_path)
    assert extras is not None
    merged = merge_engagement_maps(_ENGAGEMENT_TOOL_MAP, extras)
    req = merged["medium"]["feature"]["required"]
    assert "tapps_dependency_scan" in req
    assert "tapps_score_file" in req


def test_no_file_returns_none(tmp_path: Path) -> None:
    assert load_checklist_policy_extras(tmp_path) is None
