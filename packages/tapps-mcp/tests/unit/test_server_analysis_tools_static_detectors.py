"""MCP handler tests for tapps_static_detectors (CB lane L3: VAL-04/VAL-05)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.usefixtures("envelope_guard")


def _write_pkg(root: Path, rel: str, source: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _patch_common(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[dict[str, object]]:
    mock_settings = MagicMock()
    mock_settings.project_root = tmp_path
    recorded: list[dict[str, object]] = []

    def _capture_execution(tool_name: str, start_ns: int, **kwargs: object) -> None:
        recorded.append({"tool": tool_name, **kwargs})

    # tapps_static_detectors delegates to project.static_detectors.run_static_detector_tool,
    # which imports these lazily from their OWN source modules (not server_analysis_tools) —
    # patch them there.
    monkeypatch.setattr("tapps_core.config.settings.load_settings", lambda: mock_settings)
    monkeypatch.setattr(
        "tapps_mcp.tools.project_paths.resolve_effective_project_root",
        lambda _root, _override: MagicMock(error_code=None, root=tmp_path),
    )
    monkeypatch.setattr("tapps_mcp.server._record_call", lambda *_a, **_k: None)
    monkeypatch.setattr("tapps_mcp.server._record_execution", _capture_execution)
    monkeypatch.setattr("tapps_mcp.server._with_nudges", lambda _t, r, *_a: r)
    return recorded


@pytest.mark.asyncio
async def test_declared_uncalled_reports_via_mcp_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tapps_mcp.server_analysis_tools import tapps_static_detectors

    _write_pkg(
        tmp_path,
        "packages/tapps-mcp/src/tapps_mcp/config.py",
        "CONTENT_MINIMUM = 10\n",
    )
    _write_pkg(
        tmp_path,
        "packages/tapps-mcp/tests/unit/test_config.py",
        "from config import CONTENT_MINIMUM\n\n\ndef test_floor():\n    assert CONTENT_MINIMUM == 10\n",
    )
    recorded = _patch_common(monkeypatch, tmp_path)

    result = await tapps_static_detectors(mode="declared-uncalled", project_root=str(tmp_path))

    assert result["success"] is True
    assert result["data"]["mode"] == "declared-uncalled"
    assert "CONTENT_MINIMUM" in {f["name"] for f in result["data"]["findings"]}
    assert recorded[0]["tool"] == "tapps_static_detectors"


@pytest.mark.asyncio
async def test_consumed_no_producer_via_mcp_handler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tapps_mcp.server_analysis_tools import tapps_static_detectors

    _write_pkg(
        tmp_path,
        "packages/tapps-mcp/src/tapps_mcp/models.py",
        "from dataclasses import dataclass\n\n\n@dataclass\nclass GTM:\n    channel_mix: dict\n",
    )
    _write_pkg(
        tmp_path,
        "packages/tapps-mcp/src/tapps_mcp/renderer.py",
        "def render(gtm):\n    return gtm.channel_mix\n",
    )
    _patch_common(monkeypatch, tmp_path)

    result = await tapps_static_detectors(mode="consumed-no-producer", project_root=str(tmp_path))

    assert result["success"] is True
    assert result["data"]["mode"] == "consumed-no-producer"
    assert "GTM.channel_mix" in {f["name"] for f in result["data"]["findings"]}


@pytest.mark.asyncio
async def test_invalid_mode_returns_error_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tapps_mcp.server_analysis_tools import tapps_static_detectors

    _patch_common(monkeypatch, tmp_path)

    result = await tapps_static_detectors(mode="not-a-mode", project_root=str(tmp_path))

    assert result["success"] is False
    assert result["error"]["code"] == "invalid_mode"
