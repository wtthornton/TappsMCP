"""TAP-5442 fleet patch unit tests (small file — megafile tests untouched)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_core.brain_bridge_fleet_rpc import apply_http_fleet_rpc_patches
from tapps_mcp.memory_project_id import install_memory_project_id_patch, resolve_params_project_id


class _P:
    def __init__(self, project_id: str | None = None) -> None:
        self.project_id = project_id


class TestResolveParamsProjectId:
    def test_explicit_wins(self) -> None:
        assert resolve_params_project_id(_P("other")) == "other"

    def test_falls_back_to_settings(self) -> None:
        settings = MagicMock()
        settings.memory.brain_project_id = "homeiq"
        with patch("tapps_core.config.settings.load_settings", return_value=settings):
            assert resolve_params_project_id(_P(None)) == "homeiq"
            assert resolve_params_project_id(_P("")) == "homeiq"

    def test_install_patch_swaps_memory_tools(self) -> None:
        install_memory_project_id_patch()
        from tapps_mcp import server_memory_tools as smt

        settings = MagicMock()
        settings.memory.brain_project_id = "tapps-mcp"
        with patch("tapps_core.config.settings.load_settings", return_value=settings):
            assert smt._params_project_id(_P(None)) == "tapps-mcp"


class TestFleetRpcPatches:
    @pytest.mark.asyncio
    async def test_serialize_posts_call_original(self) -> None:
        import tapps_core.brain_bridge_fleet_rpc as mod

        mod._PATCHED = False
        apply_http_fleet_rpc_patches()
        from tapps_core.brain_bridge import HttpBrainBridge

        bridge = HttpBrainBridge("http://brain:8080", {"Authorization": "Bearer t"})
        seen: list[str] = []

        async def _orig(
            self: Any,
            tool_name: str,
            arguments: dict[str, Any],
            *,
            project_id: str | None = None,
        ) -> dict[str, Any]:
            seen.append(tool_name)
            return {"ok": True, "tool": tool_name}

        with patch.object(HttpBrainBridge, "_do_mcp_post", _orig):
            mod._PATCHED = False
            apply_http_fleet_rpc_patches()
            out = await bridge._do_mcp_post("memory_get", {"key": "k"})
        assert out == {"ok": True, "tool": "memory_get"}
        assert seen == ["memory_get"]
