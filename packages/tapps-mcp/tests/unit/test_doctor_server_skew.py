"""Tests for tapps_mcp.distribution.doctor_server_skew (lane R3).

collect_build_skew() (tools/session_health.py) only ever compares values read
inside the process running the probe, so it cannot see a live, long-running
MCP server that never got restarted after a CLI upgrade. These tests fix
that against fixtures rather than a real fleet: ``probe_fleet_tool_result``
(network I/O) and ``collect_build_skew`` (disk metadata) are both monkeypatched,
so every assertion here is driven entirely by the fixture values below --
never by whatever tapps-mcp happens to be installed on the machine running
the suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tapps_mcp.distribution import doctor_server_skew as dss
from tapps_mcp.distribution.nlt_mcp_config import NLT_SERVER_SPECS


def _write_mcp_json(root: Path, servers: dict[str, str]) -> None:
    """Write a Claude Code .mcp.json with one http entry per (server_id -> url)."""
    root.joinpath(".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    server_id: {"type": "http", "url": url} for server_id, url in servers.items()
                }
            }
        ),
        encoding="utf-8",
    )


# Sentinels selecting the two live-measured TAP-7018 response shapes (see the
# module docstring): the tool is registered but redirects to its real owner,
# or the tool is not registered on this profile at all.
UNKNOWN_TOOL = "__unknown_tool__"
RELOCATED = "__relocated__"


def _fake_probe(version_by_server: dict[str, str | None]) -> Any:
    """Build a fake ``probe_fleet_tool_result`` returning data.server.version per server_id.

    A ``None`` value simulates a server that cannot be reached at all (the
    ``ok: False`` transport-failure shape); an empty string simulates a
    server that answers but omits ``data.server.version`` for some other
    reason. ``UNKNOWN_TOOL`` and ``RELOCATED`` simulate the two shapes
    ``nlt-linear-issues``/``nlt-release-ship`` and ``nlt-build``/``nlt-setup``
    actually return once ``tapps_session_start`` is relocated (TAP-7018) --
    both measured live against the fleet, see the lane brief.
    """

    def _probe(
        server_id: str, tool_name: str, arguments: dict[str, Any] | None = None, **_kw: Any
    ) -> dict[str, Any]:
        assert tool_name == "tapps_session_start"
        version = version_by_server.get(server_id)
        if version == UNKNOWN_TOOL:
            return {
                "ok": False,
                "server_id": server_id,
                "stage": "tools/call",
                "error": f'tool {tool_name} returned isError: "Unknown tool: {tool_name}"',
            }
        if version == RELOCATED:
            return {
                "ok": True,
                "server_id": server_id,
                "tool": tool_name,
                "data": {
                    "tool": tool_name,
                    "success": False,
                    "elapsed_ms": 0,
                    "error": {
                        "code": "tool_relocated",
                        "message": (
                            "tapps_session_start now runs only on the 'nlt-memory' "
                            "NLT server. Call it there."
                        ),
                        "category": "deprecated",
                        "retryable": False,
                        "owner_preset": "nlt-memory",
                    },
                },
            }
        if version is None:
            return {
                "ok": False,
                "server_id": server_id,
                "stage": "initialize",
                "error": "connection failed: refused",
            }
        return {
            "ok": True,
            "server_id": server_id,
            "tool": tool_name,
            "data": {
                "tool": "tapps_session_start",
                "success": True,
                "data": {"server": {"version": version}} if version else {},
            },
        }

    return _probe


def _fake_build_skew(installed_version: str | None) -> Any:
    return lambda: {
        "running_version": installed_version,
        "installed_version": installed_version,
        "skew": False,
    }


class TestTappsBackedFleetServers:
    def test_no_config_returns_empty(self, tmp_path: Path) -> None:
        assert dss._tapps_backed_fleet_servers(tmp_path) == []

    def test_filters_out_docs_mcp_backed_entry(self, tmp_path: Path) -> None:
        # Threshold check: nlt-project-docs must actually be env_kind "docs" in
        # the live registry, or this test would pass for the wrong reason.
        assert NLT_SERVER_SPECS["nlt-project-docs"]["env_kind"] == "docs"
        assert NLT_SERVER_SPECS["nlt-build"]["env_kind"] == "tapps"
        _write_mcp_json(
            tmp_path,
            {
                "nlt-build": "http://127.0.0.1:8760/mcp",
                "nlt-project-docs": "http://127.0.0.1:8764/mcp",
            },
        )
        candidates = dss._tapps_backed_fleet_servers(tmp_path)
        server_ids = [server_id for server_id, _url in candidates]
        assert server_ids == ["nlt-build"]

    def test_dedupes_by_server_id(self, tmp_path: Path) -> None:
        # Two host configs (.mcp.json + .cursor/mcp.json) declaring the same
        # server_id must be probed once, not twice.
        _write_mcp_json(tmp_path, {"nlt-build": "http://127.0.0.1:8760/mcp"})
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        cursor_dir.joinpath("mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "nlt-build": {"type": "streamableHttp", "url": "http://127.0.0.1:8760/mcp"}
                    }
                }
            ),
            encoding="utf-8",
        )
        candidates = dss._tapps_backed_fleet_servers(tmp_path)
        assert [server_id for server_id, _url in candidates] == ["nlt-build"]


class TestCheckFleetServerCliSkew:
    def test_no_declared_servers_passes(self, tmp_path: Path) -> None:
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is True
        assert "No tapps-mcp HTTP fleet" in result.message

    def test_matched_versions_is_not_skew(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Coverage control (positive control): equal versions -> no skew.

        Expected to pass on both the fixed and unfixed shape of this check --
        it is NOT evidence the fix works, only that the happy path still
        reports clean. See test_skew_detected_names_both_versions for the
        negative control.
        """
        _write_mcp_json(tmp_path, {"nlt-build": "http://127.0.0.1:8760/mcp"})
        monkeypatch.setattr(
            "tapps_mcp.distribution.fleet_smoke.probe_fleet_tool_result",
            _fake_probe({"nlt-build": "3.12.90"}),
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew("3.12.90"),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is True
        assert "3.12.90" in result.message

    def test_skew_detected_names_both_versions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: this MUST fail on unfixed code.

        Mechanism: check_fleet_server_cli_skew reads
        collect_build_skew()["installed_version"] (here forced to "3.12.90")
        and string-compares it against
        probe_fleet_tool_result(...)['data']['data']['server']['version']
        (here forced to "3.12.89") for every candidate server. "3.12.90" !=
        "3.12.89" is a plain string inequality -- there is no rounding or
        normalization between the fixture values and the comparison, so this
        pair is guaranteed to land in the ``skewed`` branch once the probe is
        actually consulted. The unfixed shape of this code (see the module
        docstring: build-skew is an in-process-only comparison) never calls
        probe_fleet_tool_result at all, so it cannot observe "nlt-build" and
        must report ok=True regardless of this fixture -- which is exactly
        the false "skew=False" the lane's motivating measurement showed.
        """
        _write_mcp_json(tmp_path, {"nlt-build": "http://127.0.0.1:8760/mcp"})
        monkeypatch.setattr(
            "tapps_mcp.distribution.fleet_smoke.probe_fleet_tool_result",
            _fake_probe({"nlt-build": "3.12.89"}),
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew("3.12.90"),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is False
        assert "3.12.90" in result.message
        assert "nlt-build=3.12.89" in result.message
        assert "restart" in result.detail.lower()

    def test_unreachable_server_refuses_not_no_skew(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Refusal control: an unreachable declared server must not read as no skew."""
        _write_mcp_json(tmp_path, {"nlt-build": "http://127.0.0.1:8760/mcp"})
        monkeypatch.setattr(
            "tapps_mcp.distribution.fleet_smoke.probe_fleet_tool_result",
            _fake_probe({"nlt-build": None}),
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew("3.12.90"),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is False
        assert "did not report a version" in result.message
        assert "nlt-build" in result.message

    def test_versionless_response_refuses_not_no_skew(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Refusal control: a server that answers without a version must not read as no skew."""
        _write_mcp_json(tmp_path, {"nlt-build": "http://127.0.0.1:8760/mcp"})
        monkeypatch.setattr(
            "tapps_mcp.distribution.fleet_smoke.probe_fleet_tool_result",
            _fake_probe({"nlt-build": ""}),
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew("3.12.90"),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is False
        assert "did not report a version" in result.message

    def test_unreadable_installed_version_refuses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_mcp_json(tmp_path, {"nlt-build": "http://127.0.0.1:8760/mcp"})
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew(None),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is False
        assert "could not be read" in result.message


#: The declared fleet from the lane brief's own live measurement (2026-09-18):
#: nlt-memory reports its version; the other four either relocate or lack the
#: tool entirely. This is the exact shape that aborted every deploy on this
#: host under the unfixed check.
_CASE_1_FLEET = {
    "nlt-build": "http://127.0.0.1:8760/mcp",
    "nlt-memory": "http://127.0.0.1:8761/mcp",
    "nlt-setup": "http://127.0.0.1:8762/mcp",
    "nlt-linear-issues": "http://127.0.0.1:8763/mcp",
    "nlt-release-ship": "http://127.0.0.1:8765/mcp",
}
_CASE_1_VERSIONS = {
    "nlt-build": RELOCATED,
    "nlt-memory": "3.12.90",
    "nlt-setup": RELOCATED,
    "nlt-linear-issues": UNKNOWN_TOOL,
    "nlt-release-ship": UNKNOWN_TOOL,
}


class TestReproductionControlCase1NotSkew:
    """Reproduction control: the lane brief's measured 4/5 "did not report a
    version" fleet must NOT be a skew failure.

    States this fixture never creates: a genuinely unreachable server
    (connection refused/timeout) mixed into the same fleet, and a server
    that both relocates *and* differs in version from the CLI -- those are
    covered by the discrimination and refusal controls below.
    """

    def test_relocated_and_unknown_tool_servers_do_not_fail_the_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_mcp_json(tmp_path, _CASE_1_FLEET)
        monkeypatch.setattr(
            "tapps_mcp.distribution.fleet_smoke.probe_fleet_tool_result",
            _fake_probe(_CASE_1_VERSIONS),
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew("3.12.90"),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is True, result.message
        assert "did not report a version" not in result.message
        assert "not a skew finding" in result.message
        assert "nlt-linear-issues" in result.message
        assert "nlt-release-ship" in result.message
        assert "nlt-build" in result.message
        assert "nlt-setup" in result.message


class TestDiscriminationControlGenuineSkewStillFails:
    """Discrimination control: a real skew hiding among relocated/absent
    servers must still fail. If this cannot fail, the not-applicable
    classification has made the whole check vacuous.
    """

    def test_genuine_skew_among_not_applicable_servers_still_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fleet = {**_CASE_1_FLEET}
        versions = {**_CASE_1_VERSIONS, "nlt-memory": "3.12.89"}  # the real skew
        _write_mcp_json(tmp_path, fleet)
        monkeypatch.setattr(
            "tapps_mcp.distribution.fleet_smoke.probe_fleet_tool_result",
            _fake_probe(versions),
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew("3.12.90"),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        # Mechanism, not just the observable: on unfixed code the relocated/
        # absent servers land in the *unreachable* bucket, which is checked
        # before skew and returns first -- so the message never names the
        # skewed server or the "restart" remediation, even though ok is
        # already False for the wrong reason. Only the fixed classification
        # reaches the skewed branch.
        assert result.ok is False
        assert "nlt-memory=3.12.89" in result.message
        assert "3.12.90" in result.message
        assert "restart" in result.detail.lower()


class TestRefusalControlNotSwallowedByNotApplicable:
    """Refusal control: a genuinely unreachable/malformed server must still
    refuse even when other servers in the same fleet are legitimately
    not-applicable -- the classification must not soften into "some servers
    don't apply, so treat the whole fleet as fine".
    """

    def test_unreachable_server_still_fails_alongside_not_applicable_ones(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fleet = {**_CASE_1_FLEET}
        versions = {**_CASE_1_VERSIONS, "nlt-memory": None}  # network failure, not relocation
        _write_mcp_json(tmp_path, fleet)
        monkeypatch.setattr(
            "tapps_mcp.distribution.fleet_smoke.probe_fleet_tool_result",
            _fake_probe(versions),
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew("3.12.90"),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is False
        assert "did not report a version" in result.message
        assert "nlt-memory" in result.message
        assert "connection failed" in result.message


class TestSmokePathControlCase1DoesNotAbortDeploy:
    """Smoke-path control: drive ``blue_green.smoke_test_release`` -- the
    actual path that aborts ``deploy-local`` with "release sick" -- with the
    case-1 fleet, and confirm it is not aborted.

    Wires the *real* ``check_fleet_server_cli_skew`` output (computed against
    the same mocked ``probe_fleet_tool_result``/``collect_build_skew`` as the
    other controls) into ``smoke_test_release``'s doctor-JSON classification,
    rather than hand-typing a canned "pass" row, so a regression in the check
    itself -- not just in blue_green's classifier -- would show up here too.

    States this fixture never creates: an actual ``tapps-mcp doctor``
    subprocess invocation (``blue_green._run`` is stubbed, per the existing
    TAP-6965 pattern in ``test_blue_green_post_flip_smoke.py``) and a live
    HTTP fleet.
    """

    def test_case_1_fleet_does_not_abort_post_flip_smoke(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_mcp.distribution import blue_green as bg

        project_root = tmp_path / "project"
        project_root.mkdir()
        _write_mcp_json(project_root, _CASE_1_FLEET)
        monkeypatch.setattr(
            "tapps_mcp.distribution.fleet_smoke.probe_fleet_tool_result",
            _fake_probe(_CASE_1_VERSIONS),
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew("3.12.90"),
        )
        skew_result = dss.check_fleet_server_cli_skew(project_root)

        release_dir = tmp_path / "releases" / "3.12.90-abc123"
        bin_dir = release_dir / "bin"
        bin_dir.mkdir(parents=True)
        for tool in bg._REQUIRED_BINARIES:
            exe = bin_dir / tool
            exe.write_text("#!/bin/sh\necho tool, version 3.12.90\n", encoding="utf-8")
            exe.chmod(0o755)
        release = bg.ReleaseRef("3.12.90", "abc123", release_dir)

        checks_payload = json.dumps(
            {
                "checks": [
                    {
                        "name": skew_result.name,
                        "severity": skew_result.severity,
                        "message": skew_result.message,
                        "category": skew_result.category,
                    }
                ]
            }
        )

        def _fake_run(cmd: list[str], **_kwargs: Any) -> Any:
            from unittest.mock import MagicMock

            if cmd[-1] == "--version":
                return MagicMock(returncode=0, stdout="tool, version 3.12.90", stderr="")
            return MagicMock(returncode=0, stdout=checks_payload, stderr="")

        monkeypatch.setattr(bg, "_run", _fake_run)

        result = bg.smoke_test_release(release, project_root=project_root)
        assert result["ok"] is True, result
