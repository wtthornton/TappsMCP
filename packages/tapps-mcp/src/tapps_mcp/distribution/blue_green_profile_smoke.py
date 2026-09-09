"""Pre-flip tool-preset smoke for blue/green deploys (TAP-7234).

``blue_green.smoke_test_release`` only ever checked that a release's binaries
exist and run ``--version`` -- it never imports ``server.py``, so a broken
tool registration (release 3.12.84's missing ``TOOL_DESCRIPTIONS`` entry) was
invisible until the *post-flip* fleet restart, by which point ``current``
already pointed at the broken release. ``pre_flip_profile_smoke`` starts
every ``_NLT_TAPPS_TOOL_PRESETS`` profile from the release's own binary on a
scratch port and runs the same ``initialize`` -> ``notifications/initialized``
-> ``tools/list`` handshake the shared HTTP fleet uses (via
``fleet_smoke.probe_fleet_mcp_session``), so a broken registration is caught
before ``flip_current`` runs.
"""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tapps_mcp.distribution.blue_green import ReleaseRef


def _scratch_port() -> int:
    """Reserve an ephemeral localhost port for a throwaway server process.

    Binds and immediately releases -- a small TOCTOU window exists (another
    process could grab the port before the smoke subprocess starts), but a
    scratch smoke against a fresh loopback port doesn't warrant a stronger
    reservation scheme than the OS's own ephemeral-port allocator.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_profile_server(tapps_mcp_bin: Path, profile: str, port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            str(tapps_mcp_bin),
            "serve",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--profile",
            profile,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def _stop_profile_server(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
    if proc.stdout:
        proc.stdout.close()


def _wait_for_handshake(
    proc: subprocess.Popen[str], profile: str, *, port: int, project_root: Path, timeout: float
) -> dict[str, Any]:
    """Poll *proc* with the MCP handshake until it answers, exits, or times out."""
    from tapps_mcp.distribution.fleet_smoke import probe_fleet_mcp_session

    last_error = "did not answer tools/list before timeout"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        exit_code = proc.poll()
        if exit_code is not None:
            output = (proc.stdout.read() if proc.stdout else "").strip()
            return {"ok": False, "error": f"process exited with code {exit_code}: {output[-1000:]}"}
        probe = probe_fleet_mcp_session(profile, project_root=project_root, port=port, timeout=2.0)
        if probe.get("ok"):
            return probe
        last_error = probe.get("error") or last_error
        time.sleep(0.3)
    return {"ok": False, "error": last_error}


def _smoke_one_profile(
    tapps_mcp_bin: Path, profile: str, *, project_root: Path, timeout: float
) -> dict[str, Any]:
    """Start *profile* from *tapps_mcp_bin* on a scratch port and handshake it."""
    port = _scratch_port()
    start = time.monotonic()
    proc = _start_profile_server(tapps_mcp_bin, profile, port)
    try:
        result = _wait_for_handshake(
            proc, profile, port=port, project_root=project_root, timeout=timeout
        )
    finally:
        _stop_profile_server(proc)
    result["profile"] = profile
    result["tool_count"] = result.get("tool_count", 0)
    result["elapsed_s"] = round(time.monotonic() - start, 3)
    return result


def pre_flip_profile_smoke(
    release: ReleaseRef, *, project_root: Path, timeout: float = 60.0
) -> dict[str, Any]:
    """Start every tapps-mcp tool preset from *release*'s own binary and handshake it.

    Runs the release's own binary (not the dev venv), so a broken build --
    e.g. a ``TOOL_DESCRIPTIONS`` entry missing for a tool a preset registers
    -- fails here, before the flip, instead of at the next fleet restart.
    """
    from tapps_mcp.server import _NLT_TAPPS_TOOL_PRESETS

    tapps_mcp_bin = release.path / "bin" / "tapps-mcp"
    profiles: dict[str, dict[str, Any]] = {}
    ok = True
    for profile in sorted(_NLT_TAPPS_TOOL_PRESETS):
        row = _smoke_one_profile(tapps_mcp_bin, profile, project_root=project_root, timeout=timeout)
        profiles[profile] = row
        if not row.get("ok"):
            ok = False
    return {"ok": ok, "profiles": profiles}
