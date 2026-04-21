"""TAP-516: Contract test against a running tapps-brain HTTP adapter.

Exercises :class:`tapps_core.brain_bridge.HttpBrainBridge` against a real
``tapps-brain-http`` server (or raw HTTP for un-bridgeable endpoints like
``/health``). The module is skipped when ``TAPPS_BRAIN_HTTP_URL`` is unset,
so the default local-dev test run stays hermetic; CI is expected to boot a
brain + Postgres sidecar and export the URL.

Environment contract
--------------------

- ``TAPPS_BRAIN_HTTP_URL`` (required) — e.g. ``http://localhost:8080``.
- ``TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN`` (required for authed calls) — Bearer
  token accepted by the brain's ``/mcp`` data plane.
- ``TAPPS_BRAIN_CONTRACT_PROJECT_ID`` (optional, default
  ``tapps-mcp-contract-tests``) — ``X-Project-Id`` tenant header.
- ``TAPPS_BRAIN_CONTRACT_AGENT_ID`` (optional, default
  ``tapps-mcp-contract``) — ``X-Agent-Id`` header.
- ``TAPPS_BRAIN_OPENAPI_PATH`` (optional) — path to the ``openapi.json`` used
  for schema assertions. Defaults to
  ``../tapps-brain/docs/contracts/openapi.json`` relative to this repo's
  workspace root when that layout exists. When neither the env var nor the
  sibling checkout are present, the test fetches the live spec from
  ``{TAPPS_BRAIN_HTTP_URL}/openapi.json`` so CI against a deployed brain
  works without cloning tapps-brain.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from jsonschema import Draft202012Validator

from tapps_core.brain_bridge import HttpBrainBridge

BRAIN_HTTP_URL = os.environ.get("TAPPS_BRAIN_HTTP_URL", "").rstrip("/")
BRAIN_AUTH_TOKEN = os.environ.get("TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN", "")
PROJECT_ID = os.environ.get("TAPPS_BRAIN_CONTRACT_PROJECT_ID", "tapps-mcp-contract-tests")
AGENT_ID = os.environ.get("TAPPS_BRAIN_CONTRACT_AGENT_ID", "tapps-mcp-contract")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not BRAIN_HTTP_URL,
        reason="TAPPS_BRAIN_HTTP_URL not set — skipping brain HTTP contract tests",
    ),
]


def _authed_headers() -> dict[str, str]:
    headers: dict[str, str] = {
        "X-Project-Id": PROJECT_ID,
        "X-Agent-Id": AGENT_ID,
    }
    if BRAIN_AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {BRAIN_AUTH_TOKEN}"
    return headers


def _openapi_search_paths(brain_version: str | None) -> list[Path]:
    override = os.environ.get("TAPPS_BRAIN_OPENAPI_PATH", "")
    if override:
        return [Path(override)]
    workspace_root = Path(__file__).resolve().parents[5]
    contracts_dir = workspace_root / "tapps-brain" / "docs" / "contracts"
    candidates: list[Path] = []
    if brain_version:
        candidates.append(contracts_dir / f"openapi-{brain_version}.json")
    candidates.append(contracts_dir / "openapi.json")
    return candidates


def _load_openapi_spec(brain_version: str | None, brain_url: str) -> dict[str, Any] | None:
    for path in _openapi_search_paths(brain_version):
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    try:
        response = httpx.get(f"{brain_url}/openapi.json", timeout=5.0)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except (httpx.HTTPError, ValueError):
        return None
    return None


@pytest.fixture(scope="module")
def brain_url() -> str:
    return BRAIN_HTTP_URL


@pytest.fixture(scope="module")
def brain_health_payload(brain_url: str) -> dict[str, Any]:
    response = httpx.get(f"{brain_url}/health", timeout=5.0)
    response.raise_for_status()
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


@pytest.fixture(scope="module")
def openapi_spec(brain_url: str, brain_health_payload: dict[str, Any]) -> dict[str, Any]:
    version = brain_health_payload.get("version")
    spec = _load_openapi_spec(version if isinstance(version, str) else None, brain_url)
    if spec is None:
        pytest.skip(
            "OpenAPI spec not available — set TAPPS_BRAIN_OPENAPI_PATH, check "
            "out tapps-brain alongside tapps-mcp, or ensure the deployed brain "
            "exposes /openapi.json."
        )
    return spec


@pytest.fixture
def bridge(brain_url: str) -> HttpBrainBridge:
    if not BRAIN_AUTH_TOKEN:
        pytest.skip("TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN not set — cannot exercise /mcp")
    return HttpBrainBridge(brain_url, _authed_headers())


class TestHealthContract:
    """Unauthenticated /health contract."""

    def test_health_returns_200_and_has_version(
        self, brain_health_payload: dict[str, Any]
    ) -> None:
        assert isinstance(brain_health_payload.get("version"), str)
        assert brain_health_payload["version"]
        assert brain_health_payload.get("status") == "ok"
        assert brain_health_payload.get("service") == "tapps-brain"

    def test_info_matches_openapi_info_schema(
        self, brain_url: str, openapi_spec: dict[str, Any]
    ) -> None:
        info_schema = openapi_spec.get("components", {}).get("schemas", {}).get("Info")
        if info_schema is None:
            pytest.skip("OpenAPI spec has no components.schemas.Info — cannot validate")
        response = httpx.get(f"{brain_url}/info", headers=_authed_headers(), timeout=5.0)
        if response.status_code in (401, 403):
            pytest.skip(f"/info requires auth and auth probe failed: {response.status_code}")
        response.raise_for_status()
        payload = response.json()
        validator = Draft202012Validator(info_schema)
        errors = sorted(validator.iter_errors(payload), key=lambda e: tuple(e.path))
        assert not errors, [f"{list(e.path)}: {e.message}" for e in errors[:5]]


class TestAuthContract:
    """Authenticated /mcp surface rejects unauthenticated calls when auth is enabled."""

    def test_unauthenticated_mcp_call_is_rejected(self, brain_url: str) -> None:
        if not BRAIN_AUTH_TOKEN:
            pytest.skip(
                "TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN not set — cannot determine "
                "whether auth is enabled on this brain"
            )
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "memory_list", "arguments": {"limit": 1}},
        }
        response = httpx.post(
            f"{brain_url}/mcp",
            json=payload,
            headers={"X-Project-Id": PROJECT_ID, "X-Agent-Id": AGENT_ID},
            timeout=5.0,
        )
        assert response.status_code in (401, 403), (
            f"expected 401/403 without Bearer token, got {response.status_code}: "
            f"{response.text[:200]}"
        )


class TestMemoryLifecycle:
    """save → get → search → list → delete round-trip via HttpBrainBridge."""

    @pytest.mark.asyncio
    async def test_save_get_list_delete_round_trip(self, bridge: HttpBrainBridge) -> None:
        unique = uuid.uuid4().hex[:12]
        key = f"tap-516-contract-{unique}"
        value = f"contract test value {unique}"

        saved = await bridge.save(key, value, tier="pattern", scope="project")
        assert isinstance(saved, dict)

        got = await bridge.get(key)
        assert got is not None, f"get({key!r}) returned None immediately after save"
        assert got.get("value") == value or got.get("key") == key

        listed = await bridge.list_memories(limit=50)
        assert isinstance(listed, list)
        assert any(entry.get("key") == key for entry in listed), (
            f"entry {key!r} not present in memory_list result"
        )

        searched = await bridge.search(value, limit=10)
        assert isinstance(searched, list)

        deleted = await bridge.delete(key)
        assert deleted in (True, False)

        after_delete = await bridge.get(key)
        assert after_delete is None, f"get({key!r}) returned {after_delete!r} after delete"


class TestMaintenanceEndpoints:
    """Non-destructive contract checks for consolidation / diagnostics."""

    @pytest.mark.asyncio
    async def test_consolidate_dry_run_returns_shape(self, bridge: HttpBrainBridge) -> None:
        # TAP-800: bridge returns a graceful degraded stub when the brain
        # no longer exposes ``memory_consolidate`` (brain 3.10+). Older
        # brains should return a real result with ``groups_found``.
        result = await bridge.consolidate(dry_run=True)
        assert isinstance(result, dict)
        assert "groups_found" in result
        if result.get("degraded"):
            assert "memory_consolidate" in result.get("reason", "")

    @pytest.mark.asyncio
    async def test_hive_status_returns_recognisable_shape(self, bridge: HttpBrainBridge) -> None:
        result = await bridge.hive_status(
            agent_id=AGENT_ID, agent_name="contract-tests", register=False
        )
        assert isinstance(result, dict)
        # Accept either the legacy ``enabled`` flag or the 3.10.x payload
        # (``namespaces`` + ``agents`` + ``total_entries``).
        assert "enabled" in result or "namespaces" in result or "agents" in result

    @pytest.mark.asyncio
    async def test_hive_search_returns_list(self, bridge: HttpBrainBridge) -> None:
        result = await bridge.hive_search("tap-516-contract-probe", limit=5)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_hive_propagate_accepts_empty_entries(
        self, bridge: HttpBrainBridge
    ) -> None:
        # Federation smoke: propagating zero entries is a well-formed no-op
        # that never hits the network. Covers the "federation" spec bullet
        # without mutating shared hive state.
        result = await bridge.hive_propagate(
            entries=[], agent_id=AGENT_ID, agent_profile="repo-brain"
        )
        assert isinstance(result, dict)
        assert result.get("propagated", 0) == 0
        assert result.get("scanned", 0) == 0


class TestAgentRegistration:
    """agent_register must accept our identity without raising."""

    @pytest.mark.asyncio
    async def test_agent_register_accepts_identity(self, bridge: HttpBrainBridge) -> None:
        # TAP-800: bridge now sends brain 3.10+ schema — skills as CSV
        # string, no name/project_root. name still echoes back via the
        # Python API for caller back-compat.
        result = await bridge.agent_register(
            agent_id=AGENT_ID,
            name="tapps-mcp-contract-tests",
            profile="repo-brain",
            skills=["python", "testing"],
        )
        assert isinstance(result, dict)
        assert result.get("agent_name") == "tapps-mcp-contract-tests"
