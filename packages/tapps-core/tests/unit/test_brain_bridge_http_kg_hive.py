"""Tests for tapps_core.brain_bridge_http_kg_hive — KG-write/hive/feedback/
session/maintenance mixin for HttpBrainBridge.

Split out of test_brain_bridge_kg.py alongside the TAP-6736 megafile split
(and its own further split into session/health/memory/kg_hive mixins).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tapps_core.brain_bridge import HttpBrainBridge


def _make_bridge(*, project_id_header: str = "") -> HttpBrainBridge:
    headers = {"Authorization": "Bearer t"}
    if project_id_header:
        headers["X-Project-Id"] = project_id_header
    bridge = HttpBrainBridge("http://brain:8080", headers)
    bridge._http_mcp_call = AsyncMock(return_value={"recorded": True})
    return bridge


class TestResolveProjectId:
    def test_explicit_arg_wins(self) -> None:
        bridge = _make_bridge(project_id_header="header-project")
        assert bridge._resolve_project_id("explicit-project") == "explicit-project"

    def test_falls_back_to_header(self) -> None:
        bridge = _make_bridge(project_id_header="header-project")
        assert bridge._resolve_project_id("") == "header-project"

    def test_falls_back_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TAPPS_BRAIN_PROJECT", "env-project")
        bridge = _make_bridge()
        assert bridge._resolve_project_id("") == "env-project"


class TestUpsertEntity:
    @pytest.mark.asyncio
    async def test_upsert_entity_returns_deterministic_id(self) -> None:
        bridge = _make_bridge(project_id_header="proj-1")
        result = await bridge.upsert_entity("MyFile", "file")
        assert "entity_id" in result
        assert result["recorded"] is True

    @pytest.mark.asyncio
    async def test_upsert_entity_is_idempotent(self) -> None:
        bridge = _make_bridge(project_id_header="proj-1")
        r1 = await bridge.upsert_entity("MyFile", "file")
        r2 = await bridge.upsert_entity("MyFile", "file")
        assert r1["entity_id"] == r2["entity_id"]

    @pytest.mark.asyncio
    async def test_upsert_entity_queues_when_circuit_open(self) -> None:
        bridge = _make_bridge(project_id_header="proj-1")
        bridge._record_failure()
        bridge._record_failure()
        bridge._record_failure()
        assert bridge.circuit_open is True
        result = await bridge.upsert_entity("MyFile", "file")
        assert result["degraded"] is True
        assert "entity_id" in result


class TestUpsertEdge:
    @pytest.mark.asyncio
    async def test_requires_evidence_with_file_path(self) -> None:
        bridge = _make_bridge()
        with pytest.raises(ValueError, match="evidence"):
            await bridge.upsert_edge("a", "depends_on", "b", evidence={})

    @pytest.mark.asyncio
    async def test_records_edge_with_valid_evidence(self) -> None:
        bridge = _make_bridge()
        result = await bridge.upsert_edge(
            "a", "depends_on", "b", evidence={"file_path": "x.py"}
        )
        assert result["recorded"] is True


class TestHiveStatus:
    @pytest.mark.asyncio
    async def test_hive_status_synthesizes_enabled_on_non_dict_result(self) -> None:
        """brain 3.10+ has no "enabled" key on error; the bridge always injects one."""
        bridge = _make_bridge()
        bridge._http_mcp_call.return_value = "not a dict"
        result = await bridge.hive_status(agent_id="a1")
        assert result == {"enabled": True, "degraded": False}

    @pytest.mark.asyncio
    async def test_hive_status_injects_enabled_when_missing(self) -> None:
        bridge = _make_bridge()
        bridge._http_mcp_call.return_value = {"namespaces": [], "total_entries": 0}
        result = await bridge.hive_status(agent_id="a1")
        assert result["enabled"] is True
        assert result["namespaces"] == []
