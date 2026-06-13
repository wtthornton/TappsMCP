"""Tests for ADR-0014 session-start brain doc warm routing."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tapps_mcp.tools.session_start_helpers import _schedule_lookup_docs_warm


def test_schedule_lookup_docs_warm_skips_empty_covered(tmp_path: Path) -> None:
    result = _schedule_lookup_docs_warm(tmp_path, [])
    assert result == {"scheduled": False, "skipped": "no_covered_libraries"}


def test_schedule_lookup_docs_warm_uses_brain_marker(tmp_path: Path) -> None:
    os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = "1"
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
    marker = tmp_path / ".tapps-mcp" / ".brain-docs-warm-marker"
    marker.parent.mkdir(parents=True)
    marker.write_text("1", encoding="utf-8")
    covered = [{"library": "pytest", "topic": "fixtures", "reason": "tests"}]
    try:
        result = _schedule_lookup_docs_warm(tmp_path, covered)
        assert result["via_brain"] is True
        assert result["scheduled"] is False
        assert result["skipped"] == "warmed_within_24h"
    finally:
        os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)


@pytest.mark.asyncio
async def test_schedule_lookup_docs_warm_brain_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = "1"
    (tmp_path / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
    covered = [{"library": "pytest", "topic": "fixtures", "reason": "tests"}]

    async def _fake_warm(_bridge: object, libraries: list[str]) -> dict[str, int]:
        return {"warmed": len(libraries)}

    monkeypatch.setattr(
        "tapps_core.brain_bridge.create_brain_bridge",
        lambda *_args, **_kwargs: MagicMock(),
    )
    monkeypatch.setattr("tapps_core.knowledge.brain_docs.warm_via_brain", _fake_warm)

    try:
        result = _schedule_lookup_docs_warm(tmp_path, covered)
        assert result["via_brain"] is True
        assert result["scheduled"] is True
        await asyncio.sleep(0.05)
        marker = tmp_path / ".tapps-mcp" / ".brain-docs-warm-marker"
        assert marker.is_file()
    finally:
        os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)
