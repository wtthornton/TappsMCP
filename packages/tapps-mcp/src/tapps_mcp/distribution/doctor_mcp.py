"""Doctor checks for MCP host configs and the bridge-only brain-MCP entry (TAP-5606 split).

Covers per-host JSON config validation (Claude Code, Cursor, VS Code), the
brain-MCP entry check + strip helper (``strip_brain_mcp_entries``, ADR-0001 /
TAP-1888), the aggregate client-config check, and the unresolved
``${PROJECT_ROOT}`` placeholder check. HTTP fleet liveness/crash-loop probes
and transport-drift detection live in :mod:`tapps_mcp.distribution.doctor_fleet`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tapps_core.common.logging import get_logger
from tapps_mcp.distribution.doctor_result import CheckResult

log = get_logger(__name__)


def check_json_config(
    config_path: Path,
    servers_key: str,
    label: str,
) -> CheckResult:
    """Check a JSON MCP config file for a valid ``tapps-mcp`` entry."""
    name = f"{label} config"
    error = _validate_json_config(config_path, servers_key)
    if error is not None:
        return CheckResult(name, False, error)
    return CheckResult(name, True, f"Configured in {config_path}")


def _validate_mcp_entry_command(entry: dict[str, Any], config_path: Path) -> str | None:
    """Return an error message if the resolved server *entry* command is invalid."""
    from tapps_mcp.distribution.nlt_http_fleet import is_valid_http_fleet_mcp_entry
    from tapps_mcp.distribution.setup_generator import _is_valid_tapps_command

    if is_valid_http_fleet_mcp_entry(entry):
        return None

    command = entry.get("command", "")
    args = entry.get("args", [])
    if _is_valid_tapps_command(command, args if isinstance(args, list) else None):
        return None
    if isinstance(args, list) and any("--profile" in str(a) for a in args):
        wrapper_name = Path(str(command).replace("\\", "/")).name.lower()
        if wrapper_name.endswith("-serve.sh") or wrapper_name == "tapps-mcp-serve.sh":
            return None
    return (
        f"Unexpected command: '{command}' (expected 'tapps-mcp', 'uv run tapps-mcp serve',"
        " or path to tapps-mcp.exe)"
    )


def _validate_json_config(config_path: Path, servers_key: str) -> str | None:
    """Return an error message if *config_path* is invalid, else ``None``."""
    from tapps_mcp.distribution.setup_generator import _load_mcp_config_json

    if not config_path.exists():
        return f"Not found: {config_path}"

    data = _load_mcp_config_json(config_path)
    if not data and config_path.read_text(encoding="utf-8").strip():
        return f"Invalid JSON: {config_path}"

    if not isinstance(data, dict):
        return f"Invalid structure: {config_path}"

    servers = data.get(servers_key, {})
    if not isinstance(servers, dict):
        return f"Invalid structure: {config_path}"

    entry = servers.get("tapps-mcp")
    if not isinstance(entry, dict):
        entry = servers.get("nlt-build") or servers.get("nlt-code-quality")
        if not isinstance(entry, dict):
            return f"tapps-mcp / nlt-build not in {config_path}"

    return _validate_mcp_entry_command(entry, config_path)


def check_claude_code_user(
    home: Path | None = None,
    project_root: Path | None = None,
) -> CheckResult:
    """Check ``~/.claude.json`` for tapps-mcp entry.

    When the user file omits tapps-mcp but project ``.mcp.json`` registers it
    (Epic 80.9), this check passes with an informational detail.
    """
    base = home or Path.home()
    user_path = base / ".claude.json"
    if user_path.exists() and _validate_json_config(user_path, "mcpServers") is None:
        return CheckResult("Claude Code (user)", True, f"Configured in {user_path}")
    if project_root is not None:
        proj_path = project_root / ".mcp.json"
        if proj_path.exists() and _validate_json_config(proj_path, "mcpServers") is None:
            return CheckResult(
                "Claude Code (user)",
                True,
                "Project .mcp.json configures tapps-mcp (~/.claude.json optional)",
                "User-level Claude MCP is optional when the project registers tapps-mcp.",
            )
    return check_json_config(user_path, "mcpServers", "Claude Code (user)")


def check_claude_code_project(project_root: Path) -> CheckResult:
    """Check ``.mcp.json`` in project root for tapps-mcp entry."""
    return check_json_config(project_root / ".mcp.json", "mcpServers", "Claude Code (project)")


def check_cursor_config(project_root: Path) -> CheckResult:
    """Check ``.cursor/mcp.json`` for tapps-mcp entry."""
    return check_json_config(
        project_root / ".cursor" / "mcp.json",
        "mcpServers",
        "Cursor",
    )


def _other_mcp_host_configured(project_root: Path) -> bool:
    """Return True when the project already wires Cursor or Claude Code MCP."""
    return (project_root / ".cursor" / "mcp.json").is_file() or (
        project_root / ".mcp.json"
    ).is_file()


def check_vscode_config(
    project_root: Path,
    *,
    vscode_detected: bool | None = None,
) -> CheckResult:
    """Check ``.vscode/mcp.json`` for tapps-mcp entry.

    TAP-5360: a missing file is ``warn`` (not ``fail``) when VS Code is not an
    active platform for this consumer — either the IDE is not installed, or the
    project already configures Cursor/Claude without a VS Code MCP file. That
    avoids an unclearable hard fail (``tapps_upgrade`` never generates
    ``.vscode/mcp.json``). Invalid existing files still fail. When VS Code is
    installed and no other host is configured, missing remains ``fail`` with a
    remediation pointing at ``tapps-mcp init --host vscode``.
    """
    config_path = project_root / ".vscode" / "mcp.json"
    if config_path.exists():
        return check_json_config(config_path, "servers", "VS Code")

    if vscode_detected is None:
        from tapps_mcp.distribution.setup_generator import _detect_hosts

        vscode_detected = "vscode" in _detect_hosts()

    # Hard-fail only when VS Code looks like the intended sole host — then
    # ``tapps-mcp init --host vscode`` clears the finding.
    if vscode_detected and not _other_mcp_host_configured(project_root):
        return CheckResult(
            "VS Code config",
            False,
            f"Not found: {config_path}",
            "VS Code is installed but .vscode/mcp.json is missing. "
            "Run: tapps-mcp init --host vscode",
        )
    return CheckResult(
        "VS Code config",
        False,
        f"WARN: Not found: {config_path} (VS Code MCP not required for this project)",
        "Optional when the project uses Cursor or Claude Code only. "
        "To configure VS Code: tapps-mcp init --host vscode",
        severity="warn",
    )


_BRAIN_MCP_SERVER_NAMES: frozenset[str] = frozenset({"tapps-brain", "tapps-brain-mcp"})
_BRAIN_MCP_CONFIG_PATHS: tuple[tuple[str, str], ...] = (
    (".mcp.json", "mcpServers"),
    (".cursor/mcp.json", "mcpServers"),
    (".vscode/mcp.json", "servers"),
)
_ADR_0001_REF = "docs/adr/0001-in-process-agentbrain-via-brainbridge.md"


def _brain_http_url_for_checks(project_root: Path) -> str:
    """Resolve brain HTTP URL for doctor checks: env first, then ``.tapps-mcp.yaml``.

    MCP subprocesses receive ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` from ``.mcp.json``.
    CLI ``tapps-mcp doctor`` should still exercise brain probes when the URL is
    configured only under ``memory.brain_http_url`` in project yaml.
    """
    import os

    url = os.environ.get("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "").strip()
    if url:
        return url
    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings(project_root=project_root)
        raw = getattr(settings.memory, "brain_http_url", "")
        return str(raw or "").strip()
    except Exception:
        return ""


def _is_unsubstituted_placeholder(value: str) -> bool:
    """True when *value* is an unresolved ``${VAR}`` MCP-config placeholder."""
    from tapps_core.brain_auth import is_unsubstituted_brain_token_placeholder

    return is_unsubstituted_brain_token_placeholder(value)


def _resolve_brain_auth_token(settings: Any) -> str | None:
    """Resolve the client bearer token for doctor brain probes."""
    from tapps_core.brain_auth import resolve_brain_auth_token

    return resolve_brain_auth_token(settings)


def _doctor_brain_headers(settings: Any) -> dict[str, str]:
    """Build brain HTTP headers for doctor probes with env token fallback."""
    from tapps_core.brain_auth import build_brain_headers

    headers = build_brain_headers(settings)
    bearer = _resolve_brain_auth_token(settings)
    if bearer and "Authorization" not in headers:
        headers = {**headers, "Authorization": f"Bearer {bearer}"}
    return headers


def _brain_mcp_offenses(project_root: Path) -> list[str]:
    """Return human-readable offenses for direct tapps-brain MCP server entries."""
    offenses: list[str] = []
    for rel_path, servers_key in _BRAIN_MCP_CONFIG_PATHS:
        config_path = project_root / rel_path
        if not config_path.exists():
            continue
        try:
            raw = config_path.read_text(encoding="utf-8-sig")
            data = json.loads(raw) if raw.strip() else {}
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        servers = data.get(servers_key, {})
        if not isinstance(servers, dict):
            continue
        found = sorted(k for k in servers if k in _BRAIN_MCP_SERVER_NAMES)
        if found:
            offenses.append(f"{rel_path}: {', '.join(found)}")
    return offenses


def check_brain_mcp_entry(project_root: Path) -> CheckResult:
    """Fail when MCP configs declare a direct tapps-brain server (ADR-0001).

    Memory must flow through tapps-mcp's BrainBridge — not a parallel MCP
    server entry that bypasses profile filtering and flywheel semantics.
    """
    offenses = _brain_mcp_offenses(project_root)
    if offenses:
        return CheckResult(
            "Brain MCP entry (bridge-only)",
            False,
            f"Direct tapps-brain server configured: {'; '.join(offenses)}",
            "Remove tapps-brain from MCP config — use tapps_memory via tapps-mcp only "
            f"(see {_ADR_0001_REF}). Run tapps_upgrade to strip automatically.",
        )
    return CheckResult(
        "Brain MCP entry (bridge-only)",
        True,
        "No direct tapps-brain MCP server entry",
    )


def _strip_brain_mcp_entry(
    config_path: Path, servers_key: str, rel_path: str, *, dry_run: bool
) -> str | None:
    """Remove direct tapps-brain MCP server keys from a single config file.

    Returns a stripped-summary string, or ``None`` if nothing was removed.
    """
    from tapps_mcp.distribution.setup_generator import _load_mcp_config_json

    try:
        data = _load_mcp_config_json(config_path)
    except OSError:
        return None
    if not data or not isinstance(data, dict):
        return None
    servers = data.get(servers_key, {})
    if not isinstance(servers, dict):
        return None
    removed_keys = [k for k in list(servers) if k in _BRAIN_MCP_SERVER_NAMES]
    if not removed_keys:
        return None
    for key in removed_keys:
        del servers[key]
    if dry_run:
        return f"{rel_path} (would remove: {', '.join(removed_keys)})"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return rel_path


def strip_brain_mcp_entries(
    project_root: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Remove direct tapps-brain MCP server keys from host config files (TAP-1888)."""
    stripped: list[str] = []
    for rel_path, servers_key in _BRAIN_MCP_CONFIG_PATHS:
        config_path = project_root / rel_path
        if not config_path.exists():
            continue
        result = _strip_brain_mcp_entry(config_path, servers_key, rel_path, dry_run=dry_run)
        if result is not None:
            stripped.append(result)
    return {"stripped": stripped, "dry_run": dry_run}


def check_mcp_client_config(
    project_root: Path,
    home: Path | None = None,
) -> CheckResult:
    """Aggregate check: is tapps-mcp registered in *any* MCP client config?

    Scans project-level and user-level config files for Cursor, VS Code, and
    Claude Code.  Returns a pass if at least one config references tapps-mcp,
    otherwise returns a failure with a suggested config snippet.

    Args:
        project_root: The project root directory.
        home: Override for home directory (for testing).
    """
    base = home or Path.home()

    # (path, servers_key, label) tuples to probe
    candidates: list[tuple[Path, str, str]] = [
        (project_root / ".cursor" / "mcp.json", "mcpServers", "Cursor"),
        (project_root / ".vscode" / "mcp.json", "servers", "VS Code"),
        (project_root / ".mcp.json", "mcpServers", "Claude Code (project)"),
        (
            project_root / ".claude" / "settings.json",
            "mcpServers",
            "Claude Code (project settings)",
        ),
        (base / ".claude.json", "mcpServers", "Claude Code (user)"),
        (base / ".claude" / "settings.json", "mcpServers", "Claude Code (settings)"),
    ]

    found_in: list[str] = []
    nlt_note = ""
    for path, servers_key, label in candidates:
        result = check_json_config(path, servers_key, label)
        if result.ok:
            found_in.append(label)
            if not nlt_note and path.exists():
                try:
                    from tapps_mcp.distribution.nlt_mcp_config import list_nlt_server_ids_in_config
                    from tapps_mcp.distribution.setup_generator import _load_mcp_config_json

                    data = _load_mcp_config_json(path)
                    servers = data.get(servers_key, {})
                    if isinstance(servers, dict):
                        nlt_ids = list_nlt_server_ids_in_config(servers)
                        if nlt_ids:
                            nlt_note = (
                                f"; NLT plugin: {len(nlt_ids)} enabled ({', '.join(nlt_ids)})"
                            )
                except Exception:
                    pass

    if found_in:
        return CheckResult(
            "MCP client config",
            True,
            f"tapps-mcp registered in: {', '.join(found_in)}{nlt_note}",
        )

    snippet = (
        '{\n  "mcpServers": {\n    "tapps-mcp": {\n'
        '      "command": "uv",\n'
        '      "args": ["run", "tapps-mcp", "serve"]\n'
        "    }\n  }\n}"
    )
    return CheckResult(
        "MCP client config",
        False,
        "tapps-mcp not found in any MCP client config",
        f"Add tapps-mcp to your MCP client config. "
        f"Cursor: .cursor/mcp.json, VS Code: .vscode/mcp.json, "
        f"Claude Code: .mcp.json. Example:\n{snippet}",
    )


_UNRESOLVED_VAR_RE = re.compile(r"\$\{[^}]+\}")
_PROJECT_ROOT_ENV_KEYS = ("TAPPS_MCP_PROJECT_ROOT", "DOCS_MCP_PROJECT_ROOT")


def _unresolved_project_root_in_mcp_json(
    config_path: Path,
    servers_key: str,
) -> list[tuple[str, str, str]]:
    """Return [(server_name, env_key, value), ...] for tapps/docs servers whose
    ``*_PROJECT_ROOT`` env value contains an unresolved ``${...}`` reference.

    TAP-2199: Claude Code CLI does not expand VS Code variables. A literal
    ``${workspaceFolder}`` in the consumer's ``.mcp.json`` would cause the
    server to mkdir a phantom directory at the real project root. Surface
    the broken state to ``tapps doctor`` so consumers can run ``tapps_upgrade``
    (which self-heals) instead of silently running with a corrupted root.
    """
    if not config_path.exists():
        return []
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    servers = data.get(servers_key)
    if not isinstance(servers, dict):
        return []
    findings: list[tuple[str, str, str]] = []
    for server_name, entry in servers.items():
        if not isinstance(entry, dict):
            continue
        env = entry.get("env")
        if not isinstance(env, dict):
            continue
        for key in _PROJECT_ROOT_ENV_KEYS:
            value = env.get(key)
            if isinstance(value, str) and _UNRESOLVED_VAR_RE.search(value):
                findings.append((str(server_name), key, value))
    return findings


def check_mcp_config_unresolved_project_root(project_root: Path) -> CheckResult:
    """TAP-2199: detect broken ``${workspaceFolder}`` in any .mcp.json on disk.

    Runs across the project-scoped Cursor, VS Code, and Claude Code config
    paths.  When any ``TAPPS_MCP_PROJECT_ROOT`` / ``DOCS_MCP_PROJECT_ROOT``
    holds an unresolved ``${...}`` reference, the consumer's MCP server is
    silently mkdir'ing a phantom directory at the real project root. The
    fix is one ``tapps_upgrade`` call (the upgrade flow self-heals).
    """
    candidates: list[tuple[Path, str, str]] = [
        (project_root / ".mcp.json", "mcpServers", "Claude Code (project)"),
        (project_root / ".cursor" / "mcp.json", "mcpServers", "Cursor"),
        (project_root / ".vscode" / "mcp.json", "servers", "VS Code"),
    ]
    broken: list[str] = []
    for path, servers_key, label in candidates:
        for server_name, env_key, value in _unresolved_project_root_in_mcp_json(path, servers_key):
            broken.append(f"{label} [{server_name}].env.{env_key} = {value!r}")
    if not broken:
        return CheckResult(
            "MCP env (TAP-2199)",
            True,
            "no unresolved ${...} in any TAPPS_MCP_PROJECT_ROOT / DOCS_MCP_PROJECT_ROOT",
        )
    return CheckResult(
        "MCP env (TAP-2199)",
        False,
        f"Unresolved variable refs in {len(broken)} env value(s)",
        "Run `tapps-mcp upgrade` to rewrite to an absolute project root "
        "(self-heals per TAP-2199). Found:\n  " + "\n  ".join(broken),
    )
