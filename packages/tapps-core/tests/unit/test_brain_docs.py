"""Tests for brain-central doc lookup helpers."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

from pathlib import Path

import pytest

from tapps_core.knowledge.brain_docs import (
    apply_docs_via_brain_mcp_env,
    brain_docs_warm_marker_path,
    docs_via_brain_enabled,
    lookup_result_from_brain_payload,
    lookup_via_brain,
    warm_via_brain,
)
from tapps_core.knowledge.models import LookupResult


def test_docs_via_brain_env_truthy() -> None:
    os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = "1"
    try:
        assert docs_via_brain_enabled() is True
    finally:
        os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)


def test_docs_via_brain_env_falsy() -> None:
    os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = "0"
    try:
        assert docs_via_brain_enabled() is False
    finally:
        os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)


def test_lookup_result_from_brain_payload() -> None:
    result = lookup_result_from_brain_payload(
        {
            "success": True,
            "content": "# pytest docs",
            "source": "cache",
            "library": "pytest",
            "topic": "fixtures",
            "context7_id": "/pytest/docs",
            "cache_hit": True,
        },
        start=0.0,
    )
    assert isinstance(result, LookupResult)
    assert result.success is True
    assert result.cache_hit is True
    assert result.library == "pytest"


@pytest.mark.asyncio
async def test_lookup_via_brain_returns_none_on_unknown_tool() -> None:
    bridge = MagicMock()
    bridge.docs_lookup = AsyncMock(side_effect=RuntimeError("Unknown tool docs_lookup"))
    assert await lookup_via_brain(bridge, "pytest", "fixtures") is None


@pytest.mark.asyncio
async def test_warm_via_brain_empty() -> None:
    bridge = MagicMock()
    result = await warm_via_brain(bridge, [])
    assert result == {"warmed": 0, "libraries": []}


def test_apply_docs_via_brain_mcp_env_strips_context7() -> None:
    os.environ["TAPPS_MCP_DOCS_VIA_BRAIN"] = "1"
    try:
        env = apply_docs_via_brain_mcp_env(
            {"TAPPS_MCP_CONTEXT7_API_KEY": "${TAPPS_MCP_CONTEXT7_API_KEY}", "KEEP": "1"},
        )
        assert "TAPPS_MCP_CONTEXT7_API_KEY" not in env
        assert env["TAPPS_MCP_DOCS_VIA_BRAIN"] == "1"
        assert env["KEEP"] == "1"
    finally:
        os.environ.pop("TAPPS_MCP_DOCS_VIA_BRAIN", None)


def test_brain_docs_warm_marker_path(tmp_path: Path) -> None:
    assert brain_docs_warm_marker_path(tmp_path) == tmp_path / ".tapps-mcp" / ".brain-docs-warm-marker"
