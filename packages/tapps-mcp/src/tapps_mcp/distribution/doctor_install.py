"""Doctor checks for binary/version drift and install layout (TAP-5606 split).

Covers the ``tapps-mcp``/``docsmcp`` PATH check, global-binary version-mismatch
detection, blue/green deploy status, and local-checkout install drift.
"""

from __future__ import annotations

import shutil

from tapps_mcp.distribution.doctor_result import CheckResult


def check_binary_on_path() -> CheckResult:
    """Check that ``tapps-mcp`` is available.

    If running as a PyInstaller frozen exe, the binary is the current
    process itself, so the check always passes.
    """
    import sys as _sys

    # Running as a frozen exe (PyInstaller) — binary is the current process
    if getattr(_sys, "frozen", False):
        return CheckResult(
            "tapps-mcp binary",
            True,
            f"Running as frozen exe: {_sys.executable}",
        )

    found = shutil.which("tapps-mcp") is not None
    if found:
        return CheckResult("tapps-mcp binary", True, "tapps-mcp is on PATH")
    return CheckResult(
        "tapps-mcp binary",
        False,
        "tapps-mcp not found on PATH",
        "Install: pip install tapps-mcp (or pipx install tapps-mcp)",
    )


def _check_binary_version_mismatch_for(
    label: str,
    binary_name: str,
    source_version: str,
    reinstall_path: str,
) -> CheckResult:
    """Compare the global ``<binary_name>`` version against *source_version*.

    Returns a passing CheckResult when the binary is absent (silent skip) or
    when versions match. Returns a failing CheckResult with the modern
    ``uv tool install -e --reinstall`` remediation when versions differ.
    """
    import subprocess

    check_name = f"{label} binary version"
    binary_path = shutil.which(binary_name)
    if not binary_path:
        return CheckResult(
            check_name,
            True,
            f"{binary_name} not on PATH (version check skipped)",
        )

    try:
        result = subprocess.run(
            [binary_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return CheckResult(
                check_name,
                True,
                f"Could not determine {binary_name} version (check skipped)",
            )
        bin_version = result.stdout.strip().split()[-1]
    except Exception:
        return CheckResult(
            check_name,
            True,
            f"{binary_name} version check failed (skipped)",
        )

    if bin_version == source_version:
        return CheckResult(
            check_name,
            True,
            f"{binary_name} binary and server versions match: {source_version}",
        )
    return CheckResult(
        check_name,
        False,
        f"Version mismatch: {binary_name}={bin_version}, server={source_version}",
        f"Refresh: uv tool install -e --reinstall {reinstall_path}",
    )


def check_binary_version_mismatch() -> CheckResult:
    """Warn when the global ``tapps-mcp`` binary differs from this server's version."""
    from tapps_mcp import __version__

    return _check_binary_version_mismatch_for(
        label="tapps-mcp",
        binary_name="tapps-mcp",
        source_version=__version__,
        reinstall_path="<tapps-mcp-checkout>/packages/tapps-mcp",
    )


def check_docsmcp_binary_version_mismatch() -> CheckResult:
    """TAP-2129: warn when the global ``docsmcp`` binary differs from this server's docs-mcp version."""
    from docs_mcp import __version__ as docs_mcp_version

    return _check_binary_version_mismatch_for(
        label="docsmcp",
        binary_name="docsmcp",
        source_version=docs_mcp_version,
        reinstall_path="<tapps-mcp-checkout>/packages/docs-mcp",
    )


def check_blue_green_deploy() -> CheckResult:
    """Verify dev-monorepo blue/green MCP deploy layout when present."""
    from tapps_mcp.distribution.blue_green import (
        CURRENT_LINK,
        RELEASES_DIR,
        blue_green_status,
        current_release_path,
    )

    current = current_release_path()
    if current is None and not RELEASES_DIR.is_dir():
        return CheckResult(
            "Blue/green MCP deploy",
            True,
            "Not configured (legacy uv tool install or fresh checkout)",
            "Run tapps-mcp deploy-local from the tapps-mcp checkout to enable zero-downtime deploys.",
        )

    status = blue_green_status()
    if current is None and RELEASES_DIR.is_dir() and any(RELEASES_DIR.iterdir()):
        return CheckResult(
            "Blue/green MCP deploy",
            True,
            "Release built; awaiting first flip (current symlink not yet set)",
        )

    if current is None:
        return CheckResult(
            "Blue/green MCP deploy",
            False,
            f"Releases present ({len(status.get('releases') or [])}) but current symlink missing",
            f"Run tapps-mcp deploy-local or recreate {CURRENT_LINK}",
        )

    manifest = status.get("manifest") or {}
    version = manifest.get("version", "unknown")
    short_sha = manifest.get("short_sha", "unknown")
    detail = f"current={current.name} ({version}-{short_sha}), releases={len(status.get('releases') or [])}"
    if status.get("deploy_lock_held"):
        detail += "; deploy lock held"
    return CheckResult(
        "Blue/green MCP deploy",
        True,
        detail,
    )


def check_global_local_install() -> CheckResult:
    """TAP-4099: warn when global CLIs were installed from a local checkout path."""
    from tapps_mcp.distribution.blue_green import current_release_path

    if current_release_path() is not None:
        return CheckResult(
            "Global CLI install source",
            True,
            "Blue/green current release active (~/.tapps-mcp/current)",
            "Deploy updates via tapps-mcp deploy-local; running servers stay pinned until MCP reload.",
        )

    from tapps_mcp.diagnostics import check_install_drift

    drift = check_install_drift()
    local_entries = [e for e in drift.entries if e.from_local_source]
    if not local_entries:
        return CheckResult(
            "Global CLI install source",
            True,
            "No local-path global installs detected (or globals absent)",
        )
    names = ", ".join(e.binary for e in local_entries)
    sources = "; ".join(f"{e.binary}←{e.install_source}" for e in local_entries if e.install_source)
    return CheckResult(
        "Global CLI install source",
        True,
        f"WARN: {names} installed from local checkout ({sources})",
        drift.remediation_hint
        or (
            "Pin consumer globals to release tags; dev monorepo deploys via "
            "tapps-mcp deploy-local (blue/green) then MCP reload."
        ),
    )
