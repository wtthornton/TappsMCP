"""Doctor check for skew between live tapps-mcp fleet servers and the CLI.

``session_health.collect_build_skew()`` compares two values that both come
from *the process running the probe* -- ``tapps_mcp.__version__`` bound at
import versus a fresh ``importlib.metadata`` read. That catches a stale
import inside one interpreter. It cannot see the skew that actually happens
in this fleet: the long-lived HTTP MCP server processes (``tapps-mcp fleet
start``, or a blue/green release under ``~/.tapps-mcp/current``) are
separate OS processes from separate installs, distinct from whichever
process happens to run ``tapps_doctor``/``tapps-mcp doctor``. A CLI upgrade
does not touch a server that is already running; only restarting it does.

This check asks each declared tapps-mcp HTTP fleet server for its own
version over its own MCP session -- the same ``tapps_session_start`` call an
agent already makes -- and compares the answer to the version currently
installed on disk. A server that cannot be reached, or answers without a
version for a reason other than relocation, is reported as unknown rather
than folded into "no skew": a probe that goes silent must not read as a
clean bill of health.

``tapps_session_start`` is not present on every profile (TAP-7018): it now
runs only on ``nlt-memory``, and every other profile either resolves the
name to a "relocated" pointer envelope (``nlt-build``, ``nlt-setup``) or
does not register the name at all, which the MCP SDK reports as ``Unknown
tool`` (``nlt-linear-issues``, ``nlt-release-ship``). Neither is a skew
finding -- nothing was asked to report a version and declined to -- so
both are classified "not applicable" and excluded from the pass/fail
verdict, distinctly from a server that should answer and doesn't.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_result import CheckResult


def _tapps_backed_fleet_servers(project_root: Path) -> list[tuple[str, str]]:
    """Return deduped ``(server_id, url)`` pairs backed by the tapps-mcp distribution.

    Reads declared endpoints from the project's MCP configs (``.mcp.json`` /
    ``.cursor/mcp.json`` / ``.vscode/mcp.json``) via
    :func:`doctor_fleet._iter_http_fleet_endpoints` -- the same source of
    truth ``check_http_fleet_liveness`` uses -- rather than a hardcoded port
    list, so a project that only runs a subset of the fleet is only asked
    about the subset it declared.

    Filtered to ``env_kind == "tapps"`` servers (``nlt-build``, ``nlt-memory``,
    ``nlt-setup``, ``nlt-linear-issues``, ``nlt-release-ship``): these are all
    the ``tapps-mcp`` distribution (``tapps-mcp``/``tapps-platform`` are two
    console-script entry points of the same package, released together).
    ``nlt-project-docs`` (``docs-mcp``) is a different distribution with its
    own ``docsmcp binary version`` doctor check already; duplicating that
    comparison here would be a second source of truth for the same claim.
    """
    from tapps_mcp.distribution.doctor_fleet import _iter_http_fleet_endpoints
    from tapps_mcp.distribution.nlt_mcp_config import NLT_SERVER_SPECS

    seen: set[str] = set()
    candidates: list[tuple[str, str]] = []
    for _label, server_id, url in _iter_http_fleet_endpoints(project_root):
        if server_id in seen:
            continue
        seen.add(server_id)
        if NLT_SERVER_SPECS.get(server_id, {}).get("env_kind") != "tapps":
            continue
        candidates.append((server_id, url))
    return candidates


def _resolve_live_server_version(
    server_id: str, project_root: Path
) -> tuple[str | None, str | None, bool]:
    """Return ``(version, reason, applicable)``.

    ``reason`` is always a human-readable explanation -- never ``None`` when
    *version* is ``None`` -- so a caller can never mistake "could not
    determine" for "matches".

    ``applicable`` is ``False`` for a server that simply does not carry a
    version-reporting ``tapps_session_start`` on this profile: either the
    tool is absent entirely (``Unknown tool`` -- the MCP SDK's own message
    for a name with no registered handler) or it resolves to the relocated-
    tool pointer envelope (``error.code == "tool_relocated"``, TAP-7018 --
    the tool is registered but refuses by design and names its real owner
    via ``owner_preset``). Neither is a skew finding: nothing was asked to
    report a version and declined to, so there is nothing to compare. Every
    other failure (unreachable transport, or an ``ok`` response missing
    ``data.server.version`` for some other reason) keeps ``applicable=True``
    and must still refuse -- a probe that goes silent must not read as a
    clean bill of health.
    """
    from tapps_mcp.distribution.fleet_smoke import probe_fleet_tool_result

    probe = probe_fleet_tool_result(
        server_id, "tapps_session_start", {"quick": True}, project_root=project_root
    )
    if not probe.get("ok"):
        reason = str(probe.get("error") or probe.get("stage") or "unreachable")
        if "Unknown tool" in reason:
            return None, f"tapps_session_start not registered on this server ({reason})", False
        return None, reason, True

    envelope = probe.get("data")
    error = envelope.get("error") if isinstance(envelope, dict) else None
    if isinstance(error, dict) and error.get("code") == "tool_relocated":
        owner = error.get("owner_preset") or "another server"
        return None, f"tapps_session_start relocated to '{owner}'", False

    inner = envelope.get("data") if isinstance(envelope, dict) else None
    server = inner.get("server") if isinstance(inner, dict) else None
    version = server.get("version") if isinstance(server, dict) else None
    if not version:
        return None, "response did not include data.server.version", True
    return str(version), None, True


def check_fleet_server_cli_skew(project_root: Path) -> CheckResult:
    """Compare each live tapps-mcp HTTP fleet server's version against disk.

    ``installed_version`` is a fresh ``importlib.metadata`` read (via
    ``session_health.collect_build_skew``), which is what a freshly invoked
    CLI would report -- so a mismatch here means a *running* server has not
    picked up an install that already happened, not that the install itself
    is broken.
    """
    name = "MCP server/CLI version skew"
    candidates = _tapps_backed_fleet_servers(project_root)
    if not candidates:
        return CheckResult(name, True, "No tapps-mcp HTTP fleet entries declared")

    from tapps_mcp.tools.session_health import collect_build_skew

    installed_version = collect_build_skew().get("installed_version")
    if not installed_version:
        return CheckResult(
            name,
            False,
            "Installed tapps-mcp distribution version could not be read; "
            "server/CLI skew cannot be determined.",
        )

    not_applicable: list[str] = []
    unreachable: list[str] = []
    skewed: list[str] = []
    matched = 0
    for server_id, _url in candidates:
        version, reason, applicable = _resolve_live_server_version(server_id, project_root)
        if version is None and not applicable:
            not_applicable.append(f"{server_id} ({reason})")
        elif version is None:
            unreachable.append(f"{server_id} ({reason})")
        elif version != installed_version:
            skewed.append(f"{server_id}={version}")
        else:
            matched += 1

    if unreachable:
        preview = ", ".join(unreachable[:4])
        return CheckResult(
            name,
            False,
            f"{len(unreachable)}/{len(candidates)} declared tapps-mcp fleet server(s) "
            f"did not report a version: {preview}",
            "An unreachable or silent server is not evidence of no skew. Confirm it is "
            "running (`tapps-mcp fleet status`) and reachable, then re-run doctor.",
        )

    if skewed:
        preview = ", ".join(skewed[:4])
        return CheckResult(
            name,
            False,
            f"Installed tapps-mcp is {installed_version} but running server(s) report: {preview}",
            "Every answer from a skewed server reflects its older build. Restart the "
            "affected MCP server process(es) after the CLI upgrade (`tapps-mcp fleet "
            "restart`, or reload MCP in your client) to pick up the installed version.",
        )

    message = (
        f"{matched}/{len(candidates)} tapps-mcp fleet server(s) match installed "
        f"version {installed_version}"
    )
    if not_applicable:
        preview = ", ".join(not_applicable[:4])
        message += (
            f"; {len(not_applicable)} do not expose a version-reporting tool on this "
            f"profile (not a skew finding): {preview}"
        )
    return CheckResult(name, True, message)


__all__ = ["check_fleet_server_cli_skew"]
