"""TappsMCP doctor: diagnose configuration, rules, and connectivity."""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import UTC, datetime, timedelta
from importlib.metadata import requires as _requires
from pathlib import Path
from typing import Any, cast

import click
import httpx

from tapps_core.common.logging import get_logger
from tapps_mcp.pipeline.platform_hook_templates import (
    SUPPORTED_CLAUDE_HOOK_KEYS,
    SUPPORTED_CURSOR_HOOK_KEYS,
)

log = get_logger(__name__)


def _upgrade_skip_tokens(project_root: Path) -> frozenset[str]:
    """Return configured ``upgrade_skip_files`` tokens for *project_root*."""
    try:
        from tapps_core.config.settings import load_settings

        return frozenset(load_settings(project_root=project_root).upgrade_skip_files)
    except Exception:
        log.debug("upgrade_skip_tokens_load_failed", exc_info=True)
        return frozenset()


def _resolved_mcp_bundle(project_root: Path) -> str:
    """Bundle from ``.tapps-mcp.yaml`` or inference from MCP config."""
    from tapps_mcp.distribution.nlt_mcp_config import normalize_mcp_bundle
    from tapps_mcp.tools.session_start_helpers import _infer_mcp_bundle

    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings(project_root=project_root)
        if settings.mcp_bundle is not None:
            return normalize_mcp_bundle(settings.mcp_bundle)
    except Exception:
        log.debug("resolved_mcp_bundle_settings_failed", exc_info=True)
    return normalize_mcp_bundle(_infer_mcp_bundle(project_root))


# ---------------------------------------------------------------------------
# Diagnostic check result
# ---------------------------------------------------------------------------


class CheckResult:
    """A single diagnostic check result."""

    __slots__ = ("detail", "message", "name", "ok")

    def __init__(
        self,
        name: str,
        ok: bool,
        message: str,
        detail: str = "",
    ) -> None:
        self.name = name
        self.ok = ok
        self.message = message
        self.detail = detail


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------


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


def _validate_json_config(config_path: Path, servers_key: str) -> str | None:
    """Return an error message if *config_path* is invalid, else ``None``."""
    from tapps_mcp.distribution.setup_generator import _is_valid_tapps_command, _load_mcp_config_json

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

    from tapps_mcp.distribution.nlt_http_fleet import is_valid_http_fleet_mcp_entry

    if isinstance(entry, dict) and is_valid_http_fleet_mcp_entry(entry):
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


def check_vscode_config(project_root: Path) -> CheckResult:
    """Check ``.vscode/mcp.json`` for tapps-mcp entry."""
    return check_json_config(
        project_root / ".vscode" / "mcp.json",
        "servers",
        "VS Code",
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
        try:
            from tapps_mcp.distribution.setup_generator import _load_mcp_config_json

            data = _load_mcp_config_json(config_path)
        except OSError:
            continue
        if not data:
            continue
        if not isinstance(data, dict):
            continue
        servers = data.get(servers_key, {})
        if not isinstance(servers, dict):
            continue
        removed_keys = [k for k in list(servers) if k in _BRAIN_MCP_SERVER_NAMES]
        if not removed_keys:
            continue
        for key in removed_keys:
            del servers[key]
        if dry_run:
            stripped.append(f"{rel_path} (would remove: {', '.join(removed_keys)})")
            continue
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        stripped.append(rel_path)
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
                            nlt_note = f"; NLT plugin: {len(nlt_ids)} enabled ({', '.join(nlt_ids)})"
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
        for server_name, env_key, value in _unresolved_project_root_in_mcp_json(
            path, servers_key
        ):
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


_HOOK_SCRIPT_PATH_RE = re.compile(
    r'(\.claude/hooks/tapps-[^"\'\s]+\.(?:ps1|sh))',
    re.IGNORECASE,
)


def _hook_paths_from_claude_settings(data: dict[str, object]) -> list[str]:
    """Collect relative ``.claude/hooks/tapps-*`` paths from a settings dict."""
    out: list[str] = []
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return out
    for groups in hooks.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            for hook in group.get("hooks") or []:
                if not isinstance(hook, dict):
                    continue
                cmd = hook.get("command", "")
                if not isinstance(cmd, str) or "tapps-" not in cmd:
                    continue
                for m in _HOOK_SCRIPT_PATH_RE.finditer(cmd):
                    out.append(m.group(1).replace("\\", "/"))
    return out


def check_claude_hook_scripts(project_root: Path) -> CheckResult:
    """Verify hook scripts referenced under ``.claude/settings*.json`` exist."""
    found_settings = False
    missing: list[str] = []
    for name in ("settings.json", "settings.local.json"):
        sf = project_root / ".claude" / name
        if not sf.exists():
            continue
        found_settings = True
        try:
            raw = sf.read_text(encoding="utf-8-sig")
            data = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        rels = _hook_paths_from_claude_settings(cast("dict[str, object]", data))
        root_res = project_root.resolve()
        for rel in rels:
            candidate = (project_root / rel).resolve()
            try:
                candidate.relative_to(root_res)
            except ValueError:
                continue
            if not candidate.is_file():
                missing.append(f"{rel} (via {name})")
    if not found_settings:
        return CheckResult(
            "Claude hook scripts",
            True,
            "No .claude/settings*.json (hook path check skipped)",
        )
    if missing:
        return CheckResult(
            "Claude hook scripts",
            False,
            f"Missing hook file(s): {', '.join(missing)}",
            "Run: tapps-mcp upgrade --host claude-code --force",
        )
    return CheckResult(
        "Claude hook scripts",
        True,
        "All tapps-* hook scripts referenced in Claude settings exist",
    )


def check_claude_md(project_root: Path) -> CheckResult:
    """Check if CLAUDE.md exists and contains TAPPS reference.

    When Cursor rules are present (``.cursor/rules/tapps-pipeline.md``),
    a missing CLAUDE.md reference is reported as a soft pass rather than a
    failure, since the project may target Cursor rather than Claude Code.
    """
    cursor_rules_present = (project_root / ".cursor" / "rules" / "tapps-pipeline.md").exists()
    claude_md = project_root / "CLAUDE.md"
    if not claude_md.exists():
        if cursor_rules_present:
            return CheckResult(
                "CLAUDE.md rules",
                True,
                "CLAUDE.md not found (Cursor rules present instead)",
            )
        return CheckResult(
            "CLAUDE.md rules",
            False,
            "CLAUDE.md not found in project root",
            "Run: tapps-mcp init --host claude-code --rules",
        )
    content = claude_md.read_text(encoding="utf-8")
    if "TAPPS" in content:
        return CheckResult("CLAUDE.md rules", True, "CLAUDE.md contains TAPPS pipeline rules")
    if cursor_rules_present:
        return CheckResult(
            "CLAUDE.md rules",
            True,
            "CLAUDE.md exists without TAPPS reference (Cursor rules present)",
        )
    return CheckResult(
        "CLAUDE.md rules",
        False,
        "CLAUDE.md exists but has no TAPPS reference",
        "Run: tapps-mcp init --host claude-code --rules",
    )


def check_cursor_rules(project_root: Path) -> CheckResult:
    """Check if ``.cursor/rules/tapps-pipeline.md`` exists."""
    rules_path = project_root / ".cursor" / "rules" / "tapps-pipeline.md"
    if rules_path.exists():
        return CheckResult("Cursor rules", True, f"Present: {rules_path}")
    return CheckResult(
        "Cursor rules",
        False,
        ".cursor/rules/tapps-pipeline.md not found",
        "Run: tapps-mcp init --host cursor --rules",
    )


def check_claude_md_stamp(project_root: Path) -> CheckResult:
    """Verify CLAUDE.md carries the ``<!-- tapps-claude-version: X.Y.Z -->`` stamp
    and that it matches the installed TappsMCP (TAP-2334).

    Parallel to :func:`check_agents_md_stamp_matches_package` — surfaces stale
    or unversioned CLAUDE.md files so consumers know to run
    ``tapps-mcp upgrade``. When CLAUDE.md does not exist (Cursor-only project),
    this check is reported as a soft pass.
    """
    claude_md = project_root / "CLAUDE.md"
    if not claude_md.exists():
        cursor_rules = project_root / ".cursor" / "rules" / "tapps-pipeline.md"
        if cursor_rules.exists():
            return CheckResult(
                "CLAUDE.md stamp",
                True,
                "CLAUDE.md not found (Cursor rules present instead)",
            )
        return CheckResult(
            "CLAUDE.md stamp",
            False,
            "CLAUDE.md not found in project root",
            "Run: tapps-mcp upgrade (or tapps_init via MCP)",
        )

    from tapps_mcp import __version__
    from tapps_mcp.pipeline.claude_md import ClaudeValidation

    validation = ClaudeValidation(claude_md.read_text(encoding="utf-8"))
    existing = validation.existing_version or "<none>"

    if validation.existing_version is None:
        return CheckResult(
            "CLAUDE.md stamp",
            False,
            "CLAUDE.md has no tapps-claude-version marker (legacy consumer)",
            "Run `uv run tapps-mcp upgrade` to add the stamp and refresh canonical sections",
        )
    if validation.existing_version != __version__:
        if "CLAUDE.md" in _upgrade_skip_tokens(project_root):
            return CheckResult(
                "CLAUDE.md stamp",
                False,
                f"stamp {existing} != package {__version__} (upgrade_skip_files)",
                "Run `tapps-mcp bump-stamps` or `tapps-mcp upgrade` (stamp-only bump when skipped)",
            )
        return CheckResult(
            "CLAUDE.md stamp",
            False,
            f"stamp {existing} != package {__version__}",
            "Run `uv run tapps-mcp upgrade` then commit CLAUDE.md",
        )
    if validation.sections_missing:
        return CheckResult(
            "CLAUDE.md stamp",
            False,
            f"stamp {existing} matches but sections missing: {', '.join(validation.sections_missing)}",
            "Run `uv run tapps-mcp upgrade` to restore canonical sections",
        )
    return CheckResult(
        "CLAUDE.md stamp",
        True,
        f"stamp {existing} matches package {__version__}",
    )


def check_agents_md_stamp_matches_package(project_root: Path) -> CheckResult:
    """Strict stamp check for release gating (TAP-982).

    Compares ``AGENTS.md`` ``<!-- tapps-agents-version: X.Y.Z -->`` against
    the installed ``tapps_mcp.__version__``. Unlike ``check_agents_md`` this
    check reports only the stamp mismatch (not missing sections / tools), so
    it fits a release-gate step that wants a single yes/no signal.

    Fails when AGENTS.md is absent, when the stamp is missing, or when the
    stamp does not equal the package version.
    """
    agents_md = project_root / "AGENTS.md"
    if not agents_md.exists():
        return CheckResult(
            "AGENTS.md stamp",
            False,
            "AGENTS.md not found in project root",
            "Run: tapps-mcp upgrade (or tapps_init via MCP)",
        )
    from tapps_mcp import __version__
    from tapps_mcp.pipeline.agents_md import AgentsValidation

    content = agents_md.read_text(encoding="utf-8")
    validation = AgentsValidation(content)
    existing = validation.existing_version or "<none>"
    if validation.existing_version == __version__:
        return CheckResult(
            "AGENTS.md stamp",
            True,
            f"stamp {existing} matches package {__version__}",
        )
    if "AGENTS.md" in _upgrade_skip_tokens(project_root):
        return CheckResult(
            "AGENTS.md stamp",
            False,
            f"stamp {existing} != package {__version__} (upgrade_skip_files)",
            "Run `tapps-mcp bump-stamps` or `tapps-mcp upgrade` (stamp-only bump when skipped)",
        )
    return CheckResult(
        "AGENTS.md stamp",
        False,
        f"stamp {existing} != package {__version__}",
        "Run `uv run tapps-mcp upgrade` then commit AGENTS.md",
    )


def check_linear_standards_rule(project_root: Path) -> CheckResult:
    """Check ``.claude/rules/linear-standards.md`` is present.

    Shipped by ``generate_claude_linear_standards_rule`` (TAP-980). The rule
    codifies the docs-mcp template pipeline for Linear epic/story creation
    and documents the Linear markdown-rendering workarounds discovered in
    the TAP-971 fleet audit.
    """
    rule_path = project_root / ".claude" / "rules" / "linear-standards.md"
    if not rule_path.exists():
        return CheckResult(
            "Linear standards rule",
            False,
            ".claude/rules/linear-standards.md not found",
            "Run: tapps-mcp upgrade",
        )
    return CheckResult(
        "Linear standards rule",
        True,
        f"Present: {rule_path}",
    )


def check_autonomy_rule(project_root: Path) -> CheckResult:
    """Check ``.claude/rules/autonomy.md`` is present and current.

    Shipped by ``generate_claude_autonomy_rule``. The rule flips the agent's
    default from "ask before acting" to "act within scope" and pins Linear
    issue assignees to the agent identity, never the OAuth human. Stale
    copies that still say "Confirm with user" reintroduce HITL pauses.
    """
    rule_path = project_root / ".claude" / "rules" / "autonomy.md"
    if not rule_path.exists():
        return CheckResult(
            "Agent autonomy rule",
            False,
            ".claude/rules/autonomy.md not found",
            "Run: tapps-mcp upgrade",
        )
    content = rule_path.read_text(encoding="utf-8")
    if "NO human-in-the-loop" not in content or "assignee=" not in content:
        return CheckResult(
            "Agent autonomy rule",
            False,
            "autonomy.md missing no-HITL default or Linear assignee guidance (stale)",
            "Run: tapps-mcp upgrade --force",
        )
    return CheckResult(
        "Agent autonomy rule",
        True,
        f"Present: {rule_path}",
    )


def _python_signal_present(project_root: Path) -> bool:
    """True when the project shows any Python marker.

    Mirrors the upgrade-time language gate without importing it (avoids
    pulling the upgrade module into doctor's call graph). Cheap shallow
    check — pyproject/setup files plus ``requirements*.txt``.
    """
    for marker in ("pyproject.toml", "setup.py", "setup.cfg"):
        if (project_root / marker).exists():
            return True
    try:
        return any(project_root.glob("requirements*.txt"))
    except OSError:
        return False


def _infra_signal_present(project_root: Path) -> bool:
    """True when the project has Dockerfile or docker-compose files."""
    try:
        if any(project_root.glob("Dockerfile*")):
            return True
        if any(project_root.glob("docker-compose*.yml")):
            return True
        return any(project_root.glob("docker-compose*.yaml"))
    except OSError:
        return False


def _check_scoped_rule(
    *,
    name: str,
    rule_filename: str,
    project_root: Path,
    gate_ok: bool,
    gate_label: str,
) -> CheckResult:
    """Shared doctor check for a path-scoped rule (TAP-978).

    Reports BOTH presence and whether the rule's language/infra gate is
    satisfied. ok=True only when present AND gate matches; absent-but-gated
    surfaces as a warning ("would not be installed by upgrade") so users
    aren't told to run upgrade on a project where it would skip.
    """
    rule_path = project_root / ".claude" / "rules" / rule_filename
    present = rule_path.exists()
    if present and gate_ok:
        return CheckResult(name, True, f"Present and gate satisfied ({gate_label})")
    if present and not gate_ok:
        return CheckResult(
            name,
            True,
            f"Present (gate not satisfied: {gate_label})",
            "Rule will continue to load. Remove via upgrade_skip_files if no longer wanted.",
        )
    if not present and gate_ok:
        return CheckResult(
            name,
            False,
            f".claude/rules/{rule_filename} not found (gate satisfied: {gate_label})",
            "Run: tapps-mcp upgrade",
        )
    return CheckResult(
        name,
        True,
        f"Absent (gate not satisfied: {gate_label}) — upgrade would skip this rule",
    )


def check_security_rule(project_root: Path) -> CheckResult:
    """Check ``.claude/rules/security.md`` (TAP-978).

    Python-gated rule shipped by ``generate_claude_security_rule``. Reports
    presence and whether Python signals are detected (the upgrade-time gate).
    """
    return _check_scoped_rule(
        name="Security rule",
        rule_filename="security.md",
        project_root=project_root,
        gate_ok=_python_signal_present(project_root),
        gate_label="python signals",
    )


def check_test_quality_rule(project_root: Path) -> CheckResult:
    """Check ``.claude/rules/test-quality.md`` (TAP-978).

    Python-gated rule shipped by ``generate_claude_test_quality_rule``.
    """
    return _check_scoped_rule(
        name="Test quality rule",
        rule_filename="test-quality.md",
        project_root=project_root,
        gate_ok=_python_signal_present(project_root),
        gate_label="python signals",
    )


def check_config_files_rule(project_root: Path) -> CheckResult:
    """Check ``.claude/rules/config-files.md`` (TAP-978).

    Python-or-infra-gated rule shipped by ``generate_claude_config_files_rule``.
    """
    python_ok = _python_signal_present(project_root)
    infra_ok = _infra_signal_present(project_root)
    if python_ok and infra_ok:
        gate_label = "python and infra signals"
    elif python_ok:
        gate_label = "python signals"
    elif infra_ok:
        gate_label = "infra signals"
    else:
        gate_label = "no python or infra signals"
    return _check_scoped_rule(
        name="Config files rule",
        rule_filename="config-files.md",
        project_root=project_root,
        gate_ok=python_ok or infra_ok,
        gate_label=gate_label,
    )


def _linear_issue_skill_marker(host_label: str) -> str:
    """Content marker proving the linear-issue skill can complete writes."""
    if host_label == "claude":
        return "mcp__plugin_linear_linear__save_issue"
    return "docs_validate_linear_issue"


def check_linear_issue_skill_current(project_root: Path) -> CheckResult:
    """Check the ``linear-issue`` skill is deployed and includes write tooling.

    Inspects each bootstrapped skill host (``.claude`` / ``.cursor``). Claude
    skills must grant ``save_issue``; Cursor skills must include the docs-mcp
    validator in ``mcp_tools``.
    """
    valid_hosts: list[str] = []
    problems: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        skill_path = base / "linear-issue" / "SKILL.md"
        if not skill_path.exists():
            problems.append(f"{host_label}/linear-issue missing")
            continue
        content = skill_path.read_text(encoding="utf-8")
        marker = _linear_issue_skill_marker(host_label)
        if marker not in content:
            problems.append(f"{host_label}/linear-issue stale (missing {marker})")
            continue
        valid_hosts.append(host_label)

    if valid_hosts:
        return CheckResult(
            "linear-issue skill",
            True,
            f"linear-issue skill current on: {', '.join(valid_hosts)}",
        )
    detail = "Run: tapps-mcp upgrade --force"
    message = problems[0] if len(problems) == 1 else f"Issues: {'; '.join(problems)}"
    return CheckResult("linear-issue skill", False, message, detail)


def check_pretooluse_matchers(project_root: Path) -> CheckResult:
    """Report each PreToolUse matcher present in .claude/settings.json (TAP-981).

    Lists matcher names (e.g., "Bash", "mcp__plugin_linear_linear__save_issue")
    so users can tell *what* is being blocked, not just whether any PreToolUse
    hook is wired. Calls out the Linear routing gate explicitly when it is
    absent — that's the highest-impact gate for fleet quality and silent
    omission was a deployment-gap finding (TAP-974).

    Always returns ok=True — this is informational, not a gate; absence of a
    matcher is often intentional (opt-in flags control deployment).
    """
    settings_path = project_root / ".claude" / "settings.json"
    if not settings_path.exists():
        return CheckResult(
            "PreToolUse matchers",
            True,
            ".claude/settings.json not present (no matchers to list)",
        )
    try:
        raw = settings_path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError) as exc:
        return CheckResult(
            "PreToolUse matchers",
            False,
            f"settings.json unreadable: {exc}",
            "Fix or regenerate via tapps-mcp upgrade",
        )
    entries = (data.get("hooks") or {}).get("PreToolUse") or []
    matchers: list[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            m = entry.get("matcher")
            if isinstance(m, str) and m:
                matchers.append(m)

    linear_matcher = "mcp__plugin_linear_linear__save_issue"
    linear_active = linear_matcher in matchers
    linear_status = (
        "Linear routing gate: active"
        if linear_active
        else "Linear routing gate: NOT enabled (set linear_enforce_gate: true in .tapps-mcp.yaml)"
    )

    # TAP-1224: cache-first read gate state + violation count.
    cache_matcher = "mcp__plugin_linear_linear__list_issues"
    cache_active = cache_matcher in matchers
    cache_mode = _detect_cache_gate_mode(project_root) if cache_active else "off"
    viol_24h = _count_cache_gate_violations_24h(project_root) if cache_active else 0
    cache_status = (
        f"Linear cache-first read gate: {cache_mode} ({viol_24h} violations in last 24h)"
        if cache_active
        else "Linear cache-first read gate: NOT enabled (set linear_enforce_cache_gate: warn|block in .tapps-mcp.yaml)"
    )

    if not matchers:
        return CheckResult(
            "PreToolUse matchers",
            True,
            f"no PreToolUse matchers wired (no opt-in gates enabled). {linear_status}. {cache_status}",
        )
    return CheckResult(
        "PreToolUse matchers",
        True,
        f"wired: {', '.join(matchers)}. {linear_status}. {cache_status}",
    )


def _detect_cache_gate_mode(project_root: Path) -> str:
    """Read the baked MODE from the installed pre-list hook script (TAP-1224).

    Returns "warn" or "block" when the script is present and parseable; "off"
    otherwise. Reads the first 20 lines so the file does not have to be loaded
    in full for a doctor sweep.
    """
    script = project_root / ".claude" / "hooks" / "tapps-pre-linear-list.sh"
    if not script.exists():
        return "off"
    try:
        with script.open(encoding="utf-8") as f:
            head = "".join(f.readline() for _ in range(20))
    except OSError:
        return "off"
    if 'MODE="block"' in head:
        return "block"
    if 'MODE="warn"' in head:
        return "warn"
    return "off"


def _count_cache_gate_violations_24h(project_root: Path) -> int:
    """Count cache-gate violations from the last 24 h (TAP-1224).

    Reads ``.tapps-mcp/.cache-gate-violations.jsonl`` and counts entries whose
    ``ts`` field is within 24 hours of now. Returns 0 when the log is missing
    or unparseable — this is a doctor-time signal, not a gate, so failures
    degrade silently.

    TAP-1411: only counts ``category=gate_miss`` (default for legacy entries
    without the field). ``category=cross_project`` entries are tracked
    separately and not flagged as actionable violations.
    """
    return _categorize_cache_gate_violations_24h(project_root)["gate_miss"]


def _categorize_cache_gate_violations_24h(project_root: Path) -> dict[str, int]:
    """Bucket the 24-h cache-gate violations by ``category`` (TAP-1411).

    Returns a dict with keys ``gate_miss`` and ``cross_project``. Legacy
    entries that pre-date the category field are counted as ``gate_miss``.
    """
    counts = {"gate_miss": 0, "cross_project": 0}
    log_path = project_root / ".tapps-mcp" / ".cache-gate-violations.jsonl"
    if not log_path.exists():
        return counts
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    try:
        with log_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_raw = entry.get("ts", "")
                if not isinstance(ts_raw, str):
                    continue
                try:
                    ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if ts < cutoff:
                    continue
                category = entry.get("category", "gate_miss")
                if category == "cross_project":
                    counts["cross_project"] += 1
                else:
                    counts["gate_miss"] += 1
    except OSError:
        return counts
    return counts


def _host_has_deployed_skills(base: Path) -> bool:
    """True when *base* contains at least one skill with a ``SKILL.md`` file."""
    if not base.is_dir():
        return False
    return any(child.is_dir() and (child / "SKILL.md").exists() for child in base.iterdir())


def _tapps_skill_bases(project_root: Path) -> list[tuple[str, Path]]:
    """Return ``(host_label, skills_dir)`` for hosts that should be validated.

    Prefer MCP-configured hosts (``.mcp.json`` / ``.cursor/mcp.json``). Otherwise
    include hosts with deployed skills so Cursor-only projects are not forced to
    mirror Claude scaffolding.
    """
    host_mcp: dict[str, Path] = {
        "claude": project_root / ".mcp.json",
        "cursor": project_root / ".cursor" / "mcp.json",
    }
    bases: list[tuple[str, Path]] = []
    for host_label, rel in (("claude", ".claude/skills"), ("cursor", ".cursor/skills")):
        base = project_root / rel
        if host_mcp[host_label].exists() or _host_has_deployed_skills(base):
            bases.append((host_label, base))
    if not bases:
        bases.append(("claude", project_root / ".claude" / "skills"))
    return bases


def _missing_tapps_skills(project_root: Path, skill_names: tuple[str, ...]) -> list[str]:
    """List ``host/skill`` paths missing ``SKILL.md`` under each skills host."""
    missing: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        if not base.is_dir():
            missing.append(f"{host_label}: skills directory missing")
            continue
        for skill_name in skill_names:
            skill_path = base / skill_name / "SKILL.md"
            if not skill_path.exists():
                missing.append(f"{host_label}/{skill_name}")
    return missing


def _memory_skill_content_ok(skill_name: str, content: str) -> bool:
    """Reject skills that still route agents at removed ``tapps_memory`` MCP."""
    lowered = content.lower()
    if len(content.strip()) < 80:
        return False
    if "mcp__tapps-mcp__tapps_memory" in lowered:
        return False
    if skill_name == "tapps-memory":
        has_cli = "tapps-mcp memory" in lowered
        has_facade = "nlt-memory" in lowered or "tap-3895" in lowered
        return has_cli and has_facade and "tapps_session_notes" in lowered
    if skill_name == "tapps-finish-task":
        if "tapps_validate_changed" not in lowered or "tapps_checklist" not in lowered:
            return False
        return "tapps-mcp memory save" in lowered
    return False


def check_deprecated_wrapper_skills(project_root: Path) -> CheckResult:
    """Warn when v3.12.0-removed wrapper skills are still deployed (TAP-3930)."""
    from tapps_mcp.pipeline.platform_skills import DEPRECATED_TAPPS_SKILLS

    found: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        for skill_name in DEPRECATED_TAPPS_SKILLS:
            if (base / skill_name / "SKILL.md").is_file():
                found.append(f"{host_label}/{skill_name}")
    if found:
        return CheckResult(
            "Deprecated wrapper skills",
            False,
            f"Still deployed: {', '.join(sorted(found))}",
            "Run: tapps-mcp upgrade --force — v3.12.0 removed tapps-score, "
            "tapps-gate, tapps-validate, and tapps-report. Use /tapps-finish-task "
            "and direct MCP tools instead.",
        )
    return CheckResult(
        "Deprecated wrapper skills",
        True,
        "No deprecated wrapper skills on disk",
    )


def check_finish_task_skill(project_root: Path) -> CheckResult:
    """Check the ``tapps-finish-task`` composite skill is deployed (TAP-977).

    The skill bundles validate_changed -> checklist -> optional memory.save as
    one invocation so agents don't drop steps of the closing sequence.
    """
    missing = _missing_tapps_skills(project_root, ("tapps-finish-task",))
    if missing:
        return CheckResult(
            "tapps-finish-task skill",
            False,
            f"Missing: {', '.join(missing)}",
            "Run: tapps-mcp upgrade (or upgrade --host cursor for Cursor-only projects)",
        )
    stale: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        skill_path = base / "tapps-finish-task" / "SKILL.md"
        if skill_path.exists():
            content = skill_path.read_text(encoding="utf-8")
            if not _memory_skill_content_ok("tapps-finish-task", content):
                stale.append(f"{host_label}/tapps-finish-task")
    if stale:
        return CheckResult(
            "tapps-finish-task skill",
            False,
            f"Stale or stub skill: {', '.join(stale)}",
            "Run: tapps-mcp upgrade --force",
        )
    hosts = ", ".join(host for host, _ in _tapps_skill_bases(project_root))
    return CheckResult(
        "tapps-finish-task skill",
        True,
        f"Present on: {hosts}",
    )


def check_tapps_memory_skill(project_root: Path) -> CheckResult:
    """Check ``tapps-memory`` skill is deployed and routes via CLI (TAP-1994)."""
    missing = _missing_tapps_skills(project_root, ("tapps-memory",))
    if missing:
        return CheckResult(
            "tapps-memory skill",
            False,
            f"Missing: {', '.join(missing)}",
            "Run: tapps-mcp upgrade --force",
        )
    stale: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        skill_path = base / "tapps-memory" / "SKILL.md"
        if skill_path.exists():
            content = skill_path.read_text(encoding="utf-8")
            if not _memory_skill_content_ok("tapps-memory", content):
                stale.append(f"{host_label}/tapps-memory")
    if stale:
        return CheckResult(
            "tapps-memory skill",
            False,
            f"Stale skill (missing CLI bridge or nlt-memory facade): {', '.join(stale)}",
            "Run: tapps-mcp upgrade --force",
        )
    hosts = ", ".join(host for host, _ in _tapps_skill_bases(project_root))
    return CheckResult(
        "tapps-memory skill",
        True,
        f"Present on: {hosts}",
    )


def _handoff_skill_content_ok(skill_name: str, content: str) -> bool:
    """Minimal markers proving handoff skills are functional, not empty stubs."""
    lowered = content.lower()
    if len(content.strip()) < 80:
        return False
    if "session-handoff.md" not in lowered:
        return False
    # TAP-1994: tapps_memory removed from MCP catalog — stale skills still point agents at it.
    if "mcp__tapps-mcp__tapps_memory" in lowered:
        return False
    if skill_name == "tapps-handoff-session":
        if "tapps_handoff_save" not in lowered:
            return False
        if "session_end=true" not in lowered:
            return False
        if "p0 gate" not in lowered:
            return False
        return "tapps_session_start" in lowered
    if skill_name == "tapps-continue-session":
        return (
            "tapps_session_start" in lowered
            and "memory search" in lowered
            and "p0 fallback" in lowered
        )
    return False


def check_session_handoff_skills(project_root: Path) -> CheckResult:
    """Check session-transfer skills are deployed (``tapps-handoff-session`` + ``tapps-continue-session``).

    These skills write/read ``.tapps-mcp/session-handoff.md`` via
    ``tapps_handoff_save`` (with ``session_end=true``) and
    ``tapps_session_start`` for cross-chat continuity.
    """
    skill_names = ("tapps-handoff-session", "tapps-continue-session")
    missing = _missing_tapps_skills(project_root, skill_names)
    if missing:
        return CheckResult(
            "session handoff skills",
            False,
            f"Missing: {', '.join(missing)}",
            "Run: tapps-mcp upgrade --force (or upgrade --host cursor)",
        )

    stale: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        for skill_name in skill_names:
            skill_path = base / skill_name / "SKILL.md"
            if skill_path.exists():
                content = skill_path.read_text(encoding="utf-8")
                if not _handoff_skill_content_ok(skill_name, content):
                    stale.append(f"{host_label}/{skill_name}")

    if stale:
        return CheckResult(
            "session handoff skills",
            False,
            f"Stale or stub skills: {', '.join(stale)}",
            "Run: tapps-mcp upgrade --force",
        )

    hosts = ", ".join(host for host, _ in _tapps_skill_bases(project_root))
    return CheckResult(
        "session handoff skills",
        True,
        f"tapps-handoff-session + tapps-continue-session present on: {hosts}",
    )


def check_session_handoff_schema(project_root: Path) -> CheckResult:
    """Lint ``.tapps-mcp/session-handoff.md`` for P0/Open consistency (TAP-3573)."""
    from tapps_mcp.tools.handoff_schema import handoff_path, load_and_lint_handoff

    path = handoff_path(project_root)
    if not path.is_file():
        return CheckResult(
            "session handoff schema",
            True,
            "No session-handoff.md (optional until handoff)",
        )

    _doc, lint = load_and_lint_handoff(project_root)
    if not lint.ok:
        return CheckResult(
            "session handoff schema",
            False,
            "; ".join(lint.errors),
            "Fix `.tapps-mcp/session-handoff.md` — add Next (P0) when Open has items, "
            "or invoke `/tapps-handoff-session` with a complete handoff.",
        )

    if lint.warnings:
        rel = path.name
        try:
            rel = str(path.relative_to(project_root.resolve()))
        except ValueError:
            pass
        return CheckResult(
            "session handoff schema",
            True,
            f"Handoff present with warnings: {'; '.join(lint.warnings)}",
            rel,
        )

    return CheckResult(
        "session handoff schema",
        True,
        "session-handoff.md schema OK",
    )


_CACHE_GATE_BLOCK_HINT_THRESHOLD = 20
_PIPELINE_ENFORCE_SKIP_THRESHOLD = 0.30
_PIPELINE_ENFORCE_MIN_LOOPS = 7


def check_pipeline_enforce_recommendations(project_root: Path) -> CheckResult:
    """Recommend git hooks / cache-gate block from 7d loop-metrics (TAP-3923)."""
    from tapps_core.config.settings import load_settings
    from tapps_mcp.tools.loop_metrics import (
        _PROMOTE_WINDOW_DAYS,
        compute_rolling_stats,
        should_auto_promote_cache_gate,
    )

    stats = compute_rolling_stats(project_root, window_days=_PROMOTE_WINDOW_DAYS)
    skip_rate = float(stats.get("gate_skip_rate", 0.0))
    loops = int(stats.get("loops", 0))
    skip_pct = int(round(skip_rate * 100))
    message = f"7d gate_skip_rate={skip_pct}% ({loops} loops in loop-metrics)"

    engagement = _read_engagement_level(project_root) or "medium"
    settings = None
    try:
        settings = load_settings(project_root=project_root)
        engagement = settings.llm_engagement_level
    except Exception:
        pass

    yaml_snippets: list[str] = []
    hints: list[str] = []

    if (
        loops >= _PIPELINE_ENFORCE_MIN_LOOPS
        and skip_rate >= _PIPELINE_ENFORCE_SKIP_THRESHOLD
        and engagement in ("medium", "high")
    ):
        install_hooks = bool(getattr(settings, "install_git_hooks", False)) if settings else False
        hook_path = project_root / ".githooks" / "pre-commit"
        if not install_hooks and not hook_path.is_file():
            yaml_snippets.append("install_git_hooks: true")
            hints.append(
                f"Chronic gate skips ({skip_pct}% ≥ {_PIPELINE_ENFORCE_SKIP_THRESHOLD:.0%}) "
                f"at {engagement} engagement — enforce validate-changed on commit"
            )

    cache_mode = _detect_cache_gate_mode(project_root)
    if settings is not None:
        cache_mode = settings.linear_enforce_cache_gate_resolved()

    viol_24h = _count_cache_gate_violations_24h(project_root)
    if cache_mode != "block":
        if viol_24h >= _CACHE_GATE_BLOCK_HINT_THRESHOLD:
            yaml_snippets.append("linear_enforce_cache_gate: block")
            hints.append(
                f"{viol_24h} Linear cache-gate misses in 24h while mode={cache_mode}"
            )
        elif settings is not None and settings.linear_enforce_cache_gate_auto_promote:
            promote, _telemetry = should_auto_promote_cache_gate(
                project_root,
                current_mode=cache_mode,
                auto_promote_enabled=True,
            )
            if promote:
                yaml_snippets.append("linear_enforce_cache_gate: block")
                hints.append(
                    "TAP-1333 auto-promote criteria met (stable pipeline, low skip rate)"
                )

    detail_parts = list(hints)
    if yaml_snippets:
        detail_parts.append(
            "Suggested .tapps-mcp.yaml:\n" + "\n".join(yaml_snippets)
        )
    detail = "\n".join(detail_parts)

    suffix = (
        f"; {len(yaml_snippets)} enforcement snippet(s)"
        if yaml_snippets
        else "; no enforcement changes suggested"
    )
    return CheckResult(
        "Pipeline enforcement recommendations",
        True,
        message + suffix,
        detail,
    )


def check_cursor_loop_metrics_telemetry(project_root: Path) -> CheckResult:
    """Report Cursor CallMcpTool transcript trustworthiness (TAP-4025)."""
    import time

    from tapps_mcp.tools.loop_metrics import (
        _DAY_SECONDS,
        _PROMOTE_WINDOW_DAYS,
        _legacy_cursor_unparsed_callmcptool,
        is_gate_tool,
        read_loop_metrics,
    )

    cutoff = int(time.time()) - _PROMOTE_WINDOW_DAYS * _DAY_SECONDS
    rows = [r for r in read_loop_metrics(project_root) if int(r.get("ts", 0)) >= cutoff]
    legacy_unparsed = sum(1 for r in rows if _legacy_cursor_unparsed_callmcptool(r))
    callmcptool_rows = sum(
        1
        for r in rows
        if "CallMcpTool" in [str(t) for t in (r.get("tools_used") or [])]
    )
    resolved_gate_rows = 0
    for row in rows:
        tools = [str(t) for t in row.get("tools_used") or []]
        if any(is_gate_tool(t) for t in tools):
            resolved_gate_rows += 1

    parts = [f"7d loops={len(rows)}", "callmcptool_unwrap=active"]
    if legacy_unparsed:
        parts.append(f"legacy_unparsed_callmcptool={legacy_unparsed}")
    detail_parts: list[str] = []
    if legacy_unparsed:
        detail_parts.append(
            f"{legacy_unparsed} pre-TAP-4017 Cursor rows excluded from rolling "
            "gate_skip_rate (is_reliable_edit_loop_row filter)."
        )
    if callmcptool_rows > 0 and resolved_gate_rows == 0:
        detail_parts.append(
            f"{callmcptool_rows} loop-metrics rows contain CallMcpTool but zero "
            "resolved tapps_* gate/checklist calls — gate_skip_rate may be inflated. "
            "See docs/TROUBLESHOOTING.md#cursor-vs-claude-transcript-parsing."
        )
    ok = not (callmcptool_rows > 0 and resolved_gate_rows == 0)
    return CheckResult(
        "Cursor loop-metrics telemetry",
        ok,
        "; ".join(parts),
        "\n".join(detail_parts) if detail_parts else None,
    )


def check_cursor_stop_completion_gate(project_root: Path) -> CheckResult:
    """Report Cursor stop completion gate mode and hook presence (TAP-3921)."""
    from tapps_core.config.settings import load_settings

    claude_hook = project_root / ".claude" / "hooks" / "tapps-stop.sh"
    cursor_hook = project_root / ".cursor" / "hooks" / "tapps-stop.sh"
    hook_paths = [p for p in (claude_hook, cursor_hook) if p.exists()]

    try:
        settings = load_settings(project_root=project_root)
        resolved = settings.cursor_stop_completion_gate_resolved()
        explicit = settings.cursor_stop_completion_gate
    except Exception as exc:
        return CheckResult(
            "Cursor stop completion gate",
            False,
            "Could not load settings",
            str(exc),
        )

    hook_note = (
        f"stop hook installed ({', '.join(p.name for p in hook_paths)})"
        if hook_paths
        else "stop hook missing — run tapps-mcp upgrade"
    )
    explicit_note = explicit if explicit is not None else "default"
    message = f"mode={resolved} (configured={explicit_note}); {hook_note}"

    if explicit == "block":
        return CheckResult(
            "Cursor stop completion gate",
            False,
            message,
            "cursor_stop_completion_gate is block — run tapps-mcp upgrade to migrate to warn",
        )

    if resolved == "block":
        return CheckResult(
            "Cursor stop completion gate",
            False,
            message,
            "Resolved mode is block — set cursor_stop_completion_gate: warn in "
            ".tapps-mcp.yaml or run tapps-mcp upgrade",
        )

    detail = None
    if explicit is None:
        detail = (
            "cursor_stop_completion_gate not pinned in .tapps-mcp.yaml — "
            "run tapps-mcp upgrade --dry-run to add cursor_stop_completion_gate: warn"
        )

    return CheckResult(
        "Cursor stop completion gate",
        True,
        message,
        detail,
    )


def check_cache_gate_block_hint(project_root: Path) -> CheckResult:
    """Recommend ``linear_enforce_cache_gate: block`` on high-traffic projects (TAP-3577)."""
    from tapps_core.config.settings import load_settings

    try:
        settings = load_settings(project_root=project_root)
        resolved_mode = settings.linear_enforce_cache_gate_resolved()
    except Exception:
        resolved_mode = _detect_cache_gate_mode(project_root)

    if resolved_mode == "block":
        return CheckResult(
            "Linear cache-gate promotion",
            True,
            "linear_enforce_cache_gate is block",
        )

    viol_24h = _count_cache_gate_violations_24h(project_root)
    if resolved_mode == "warn" and viol_24h >= _CACHE_GATE_BLOCK_HINT_THRESHOLD:
        return CheckResult(
            "Linear cache-gate promotion",
            True,
            f"{viol_24h} cache-gate misses in 24h while mode=warn",
            "Set linear_enforce_cache_gate: block in .tapps-mcp.yaml and run "
            "tapps-mcp upgrade --force. Route multi-issue reads through the linear-read skill.",
        )

    if resolved_mode == "off" and viol_24h > 0:
        return CheckResult(
            "Linear cache-gate promotion",
            True,
            f"{viol_24h} raw list_issues gate misses logged while mode=off",
            "Enable linear_enforce_cache_gate: warn (or block for high-traffic repos) "
            "in .tapps-mcp.yaml, then tapps-mcp upgrade --force.",
        )

    return CheckResult(
        "Linear cache-gate promotion",
        True,
        f"mode={resolved_mode}, {viol_24h} gate_miss violations in 24h",
    )


def check_install_git_hooks_hint(project_root: Path) -> CheckResult:
    """Recommend ``install_git_hooks: true`` when high engagement + low gate pass (TAP-3579)."""
    from tapps_core.config.settings import load_settings
    from tapps_mcp.tools.loop_metrics import compute_gate_pass_rate_7d

    try:
        settings = load_settings(project_root=project_root)
        if settings.install_git_hooks:
            return CheckResult(
                "Git pre-commit hook",
                True,
                "install_git_hooks is enabled",
            )
    except Exception:
        settings = None

    hook_path = project_root / ".githooks" / "pre-commit"
    if hook_path.is_file():
        return CheckResult(
            "Git pre-commit hook",
            True,
            ".githooks/pre-commit present",
        )

    engagement = _read_engagement_level(project_root) or "medium"
    if engagement != "high":
        return CheckResult(
            "Git pre-commit hook",
            True,
            f"optional at llm_engagement_level={engagement}",
        )

    gate_pass = compute_gate_pass_rate_7d(project_root)
    if gate_pass is None:
        return CheckResult(
            "Git pre-commit hook",
            True,
            "insufficient 7d gate metrics for recommendation",
        )

    if gate_pass < 0.70:
        pct = round(gate_pass * 100)
        return CheckResult(
            "Git pre-commit hook",
            True,
            f"7d gate pass rate {pct}% (<70%) at high engagement",
            "Set install_git_hooks: true in .tapps-mcp.yaml and run tapps-mcp upgrade "
            "to enforce validate-changed on git commit.",
        )

    pct = round(gate_pass * 100)
    return CheckResult(
        "Git pre-commit hook",
        True,
        f"7d gate pass rate {pct}% — install_git_hooks not required",
    )


def check_continuous_learning_v2_skill(project_root: Path) -> CheckResult:
    """Check the ``continuous-learning-v2`` skill is deployed (ECC v2.1).

    The skill bundles instinct-based session observation, project-scoped
    instinct storage, and evolution commands (instinct-status, evolve,
    promote, projects).  Hooks fire deterministically (100%) vs the v1
    skill-based observation (~50-80%).
    """
    present: list[str] = []
    for host_label, base in _tapps_skill_bases(project_root):
        skill_path = base / "continuous-learning-v2" / "SKILL.md"
        if skill_path.exists():
            present.append(host_label)

    if present:
        return CheckResult(
            "continuous-learning-v2 skill",
            True,
            f"Present on: {', '.join(present)}",
        )
    return CheckResult(
        "continuous-learning-v2 skill",
        False,
        "continuous-learning-v2/SKILL.md not found on any skill host",
        "Run: tapps-mcp upgrade",
    )


def check_agents_md(project_root: Path) -> CheckResult:
    """Check if AGENTS.md exists and its version matches the installed TappsMCP."""
    agents_md = project_root / "AGENTS.md"
    if not agents_md.exists():
        return CheckResult(
            "AGENTS.md",
            False,
            "AGENTS.md not found in project root",
            "Run: tapps-mcp upgrade (or tapps_init via MCP)",
        )
    from tapps_mcp import __version__
    from tapps_mcp.pipeline.agents_md import AgentsValidation

    content = agents_md.read_text(encoding="utf-8")
    validation = AgentsValidation(content)
    if validation.is_up_to_date:
        return CheckResult(
            "AGENTS.md",
            True,
            f"AGENTS.md version {validation.existing_version} matches TappsMCP {__version__}",
        )
    issues: list[str] = []
    if validation.existing_version != __version__:
        issues.append(f"version {validation.existing_version or 'none'} != TappsMCP {__version__}")
    if validation.sections_missing:
        issues.append(f"missing sections: {', '.join(validation.sections_missing)}")
    if validation.tools_missing:
        issues.append(f"missing tools: {', '.join(validation.tools_missing)}")
    return CheckResult(
        "AGENTS.md",
        False,
        f"AGENTS.md outdated ({'; '.join(issues)})",
        "Run: tapps-mcp upgrade (or tapps_init with overwrite_agents_md=True)",
    )


def check_karpathy_guidelines(project_root: Path) -> CheckResult:
    """Check the Karpathy guidelines block across AGENTS.md and CLAUDE.md.

    - Passes when every file that exists carries the block pinned to the
      vendored SHA.
    - Passes (informational) when neither file exists.
    - Fails when any existing file is missing the block or is pinned to a
      stale SHA.
    """
    from tapps_mcp.pipeline import karpathy_block

    reports: dict[str, dict[str, str | None]] = {
        rel: karpathy_block.check(project_root / rel) for rel in ("AGENTS.md", "CLAUDE.md")
    }
    expected_sha = karpathy_block.KARPATHY_GUIDELINES_SOURCE_SHA
    expected_short = expected_sha[:7]

    existing = {rel: r for rel, r in reports.items() if r["state"] != "file_absent"}
    if not existing:
        return CheckResult(
            "Karpathy guidelines",
            False,
            "Neither AGENTS.md nor CLAUDE.md found — block cannot be installed",
            "Run: tapps_init",
        )

    stale: list[str] = []
    missing: list[str] = []
    ok: list[str] = []
    for rel, rep in existing.items():
        state = rep["state"]
        if state == "ok":
            ok.append(rel)
        elif state == "missing":
            missing.append(rel)
        elif state == "stale":
            current = rep["current_sha"] or "unknown"
            stale.append(f"{rel}@{current}")

    if not missing and not stale:
        return CheckResult(
            "Karpathy guidelines",
            True,
            f"Karpathy guidelines block present in {', '.join(ok)}; pinned to {expected_short}",
        )

    parts: list[str] = []
    if missing:
        parts.append(f"missing in: {', '.join(missing)}")
    if stale:
        parts.append(f"stale ({', '.join(stale)}; expected {expected_short})")
    return CheckResult(
        "Karpathy guidelines",
        False,
        "; ".join(parts),
        "Run: tapps_upgrade (or tapps_init with include_karpathy=True)",
    )


def check_tapps_mcp_yaml(project_root: Path) -> CheckResult:
    """TAP-1787: surface ``.tapps-mcp.yaml`` YAML parse / read failures.

    Without this check, a typo in the config silently turns off
    ``linear_enforce_gate``, ``memory.safety`` enforcement, and scoring
    weights, because ``_load_yaml_config`` falls back to an empty dict.
    """
    from tapps_core.config.settings import _load_yaml_config, get_last_yaml_load_error

    config_path = project_root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return CheckResult(
            ".tapps-mcp.yaml",
            True,
            ".tapps-mcp.yaml not present (defaults in effect)",
        )

    # Force a fresh load so the cached error reflects this invocation.
    _load_yaml_config(project_root)
    err = get_last_yaml_load_error()
    if err is None:
        return CheckResult(
            ".tapps-mcp.yaml",
            True,
            ".tapps-mcp.yaml parses cleanly",
        )

    return CheckResult(
        ".tapps-mcp.yaml",
        False,
        "Failed to parse .tapps-mcp.yaml — settings fell back to defaults",
        err.get("reason", ""),
    )


def check_claude_settings(project_root: Path) -> CheckResult:
    """Check ``.claude/settings.json`` for permissions and hook schema validity.

    Verifies:
    - Permission entries: both ``mcp__tapps-mcp`` and ``mcp__tapps-mcp__*``
      (work around Claude Code permission bugs #3107, #13077, #27139).
    - Hook keys: only schema-supported keys (e.g. no PostCompact); invalid
      keys cause Claude Code to skip the entire settings file.
    """
    settings_file = project_root / ".claude" / "settings.json"
    if not settings_file.exists():
        return CheckResult(
            ".claude/settings.json",
            False,
            ".claude/settings.json not found",
            "Run: tapps-mcp upgrade --host claude-code",
        )
    try:
        raw = settings_file.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return CheckResult(
            ".claude/settings.json",
            False,
            "Invalid JSON in .claude/settings.json",
        )
    allow_list = data.get("permissions", {}).get("allow", [])
    required = ["mcp__tapps-mcp", "mcp__tapps-mcp__*"]
    missing = [e for e in required if e not in allow_list]
    if missing:
        return CheckResult(
            ".claude/settings.json",
            False,
            f"Missing permission entries: {', '.join(missing)}",
            "Run: tapps-mcp upgrade --host claude-code",
        )
    # Invalid hook keys (e.g. PostCompact) cause Claude Code to skip the entire file
    hooks_obj = data.get("hooks") or {}
    if isinstance(hooks_obj, dict):
        invalid = [k for k in hooks_obj if k not in SUPPORTED_CLAUDE_HOOK_KEYS]
        if invalid:
            return CheckResult(
                ".claude/settings.json",
                False,
                f"Unsupported hook keys (Claude Code will skip file): {', '.join(sorted(invalid))}",
                "Run: tapps-mcp upgrade --host claude-code to write only supported hooks.",
            )
    return CheckResult(
        ".claude/settings.json",
        True,
        "TappsMCP permission entries present (bare + wildcard), hooks schema valid",
    )


def _check_cursor_mcp_zombie_cleanup(project_root: Path) -> CheckResult | None:
    """Verify Cursor sessionStart does NOT run MCP zombie cleanup (deploy-local only)."""
    hooks_json = project_root / ".cursor" / "hooks.json"
    if not hooks_json.exists():
        return None
    try:
        data = json.loads(hooks_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    hooks_obj = data.get("hooks")
    if not isinstance(hooks_obj, dict):
        return None
    session_entries = hooks_obj.get("sessionStart")
    if not isinstance(session_entries, list) or not session_entries:
        return None
    zombie_cmds = {
        ".cursor/hooks/tapps-mcp-zombie-cleanup.sh",
        "powershell -NoProfile -ExecutionPolicy Bypass -File .cursor/hooks/tapps-mcp-zombie-cleanup.ps1",
    }
    stale = [
        e.get("command", "")
        for e in session_entries
        if isinstance(e, dict) and e.get("command", "") in zombie_cmds
    ]
    if stale:
        return CheckResult(
            "MCP zombie cleanup hook",
            False,
            "sessionStart must not run zombie cleanup — reap runs on deploy-local only",
            "Run: tapps-mcp upgrade --host cursor --force",
        )
    recall_cmd = ".cursor/hooks/tapps-memory-auto-recall.sh"
    has_recall = any(
        isinstance(e, dict) and e.get("command") == recall_cmd for e in session_entries
    )
    if not has_recall:
        return None
    return CheckResult(
        "MCP zombie cleanup hook",
        True,
        "sessionStart correctly omits zombie cleanup (reap on deploy-local)",
    )


def _check_cursor_hooks_config(
    project_root: Path,
    found: list[str],
) -> CheckResult | None:
    """Validate .cursor/hooks.json existence, format, and platform. Returns failure or None."""
    cursor_hooks_json = project_root / ".cursor" / "hooks.json"
    if not cursor_hooks_json.exists():
        return CheckResult(
            "Hooks",
            False,
            f"TappsMCP hooks found for: {', '.join(found)}, but .cursor/hooks.json missing",
            "Run: tapps-mcp upgrade --host cursor or upgrade --force",
        )

    format_errors: list[str] = []
    hook_warnings: list[str] = []
    try:
        data = json.loads(cursor_hooks_json.read_text(encoding="utf-8"))
        if not isinstance(data.get("version"), (int, float)):
            format_errors.append("missing or non-numeric 'version' field")
        if isinstance(data.get("hooks"), list):
            format_errors.append("'hooks' is an array (should be an object)")
        elif not isinstance(data.get("hooks"), dict):
            format_errors.append("'hooks' is not an object")
        else:
            hooks_obj = data.get("hooks", {})
            unknown = [k for k in hooks_obj if k not in SUPPORTED_CURSOR_HOOK_KEYS]
            if unknown:
                hook_warnings.append(
                    "non-catalog hook keys (preserved by upgrade; verify against "
                    f"Cursor docs): {', '.join(sorted(unknown))}"
                )
    except (json.JSONDecodeError, OSError) as exc:
        format_errors.append(f"could not parse: {exc}")

    if format_errors:
        return CheckResult(
            "Hooks",
            False,
            f"TappsMCP hooks found for: {', '.join(found)}, "
            f"but .cursor/hooks.json has invalid format: {'; '.join(format_errors)}",
            "Run: tapps-mcp upgrade --host cursor or upgrade --force to write only supported hooks",
        )

    if hook_warnings:
        return CheckResult(
            "Hooks",
            True,
            f"TappsMCP hooks found for: {', '.join(found)} ({'; '.join(hook_warnings)})",
        )

    zombie_result = _check_cursor_mcp_zombie_cleanup(project_root)
    if zombie_result is not None and not zombie_result.ok:
        return zombie_result

    # On Windows, .sh hook commands open in the editor instead of running
    if sys.platform == "win32":
        hooks_obj = data.get("hooks", {})
        for entries in hooks_obj.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                cmd = entry.get("command", "")
                if "tapps-" in cmd and cmd.rstrip().endswith(".sh"):
                    return CheckResult(
                        "Hooks",
                        False,
                        "On Windows, Cursor hooks are configured as .sh (Bash); "
                        "they open in the editor instead of running. Use PowerShell (.ps1) hooks.",
                        "Run: tapps-mcp upgrade --host cursor (or uv run tapps-mcp upgrade --host cursor)",
                    )
    return None


def check_cursor_mcp_zombie_cleanup(project_root: Path) -> CheckResult:
    """Epic 109 / ADR-0005: sessionStart must not run zombie cleanup (deploy-local only)."""
    result = _check_cursor_mcp_zombie_cleanup(project_root)
    if result is not None:
        return result
    return CheckResult(
        "MCP zombie cleanup hook",
        True,
        "Not applicable (memory auto-recall not wired on sessionStart)",
    )


def check_hooks(project_root: Path) -> CheckResult:
    """Check TappsMCP hooks: directory, session-start script, and config validity.

    For Claude Code, hook keys are validated in check_claude_settings.
    For Cursor, requires .cursor/hooks.json when scripts exist. Unknown hook
    event keys outside the catalog are reported as warnings (never stripped).
    """
    claude_hooks = project_root / ".claude" / "hooks"
    cursor_hooks = project_root / ".cursor" / "hooks"
    found: list[str] = []
    missing_session_start: list[str] = []

    if claude_hooks.is_dir() and any(claude_hooks.glob("tapps-*")):
        found.append("Claude Code")
        has_sh = (claude_hooks / "tapps-session-start.sh").exists()
        has_ps1 = (claude_hooks / "tapps-session-start.ps1").exists()
        if not has_sh and not has_ps1:
            missing_session_start.append("Claude Code")

    if cursor_hooks.is_dir() and any(cursor_hooks.glob("tapps-*")):
        found.append("Cursor")
        has_sh = (cursor_hooks / "tapps-before-mcp.sh").exists()
        has_ps1 = (cursor_hooks / "tapps-before-mcp.ps1").exists()
        if not has_sh and not has_ps1:
            missing_session_start.append("Cursor")

    if not found:
        return CheckResult(
            "Hooks",
            False,
            "No TappsMCP hooks found",
            "Run: tapps-mcp upgrade",
        )

    if missing_session_start:
        return CheckResult(
            "Hooks",
            False,
            f"TappsMCP hooks found for: {', '.join(found)}, "
            f"but session-start hook missing for: {', '.join(missing_session_start)}",
            "Run: tapps-mcp upgrade --force (or upgrade --host cursor)",
        )

    zombie_note = ""
    if "Cursor" in found:
        cursor_result = _check_cursor_hooks_config(project_root, found)
        if cursor_result is not None:
            return cursor_result
        zombie_result = _check_cursor_mcp_zombie_cleanup(project_root)
        if zombie_result is not None and zombie_result.ok:
            zombie_note = "; MCP zombie reap on deploy-local (not sessionStart)"

    return CheckResult(
        "Hooks",
        True,
        f"TappsMCP hooks found for: {', '.join(found)} (including session-start){zombie_note}",
    )


def check_scope_recommendation(project_root: Path, home: Path | None = None) -> CheckResult:
    """Warn when tapps-mcp is configured in user scope (~/.claude.json).

    Project-scoped config (.mcp.json in project root) is recommended so
    that TappsMCP is enabled only for this workspace and doesn't affect
    other projects.

    Args:
        project_root: The project root directory.
        home: Override for home directory (for testing).

    Returns:
        A :class:`CheckResult` with a warning if user-scoped config is found.
    """
    base = home or Path.home()
    user_config = base / ".claude.json"

    if not user_config.exists():
        return CheckResult(
            "Config scope",
            True,
            "No user-scoped config found (good)",
        )

    # Check if it actually has a tapps-mcp entry
    try:
        raw = user_config.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return CheckResult(
            "Config scope",
            True,
            "User config exists but could not be parsed (skipping scope check)",
        )

    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict) or "tapps-mcp" not in servers:
        return CheckResult(
            "Config scope",
            True,
            "No tapps-mcp entry in user-scoped config",
        )

    # tapps-mcp is in ~/.claude.json — warn
    project_config = project_root / ".mcp.json"
    if project_config.exists():
        return CheckResult(
            "Config scope",
            False,
            "tapps-mcp configured in both ~/.claude.json (user) and .mcp.json (project)",
            "Consider removing the entry from ~/.claude.json to avoid "
            "global side effects. Project-scoped .mcp.json is sufficient.",
        )

    return CheckResult(
        "Config scope",
        False,
        "tapps-mcp is configured in ~/.claude.json (user scope)",
        "Recommend: tapps-mcp init --scope project (writes .mcp.json in "
        "project root instead of ~/.claude.json). Then remove the tapps-mcp "
        "entry from ~/.claude.json.",
    )


def check_stale_exe_backups() -> CheckResult:
    """Check for stale ``.old`` exe backups next to the running binary.

    Only relevant when running as a frozen exe.  Stale backups indicate
    previous replace-exe operations where cleanup did not complete.
    """
    import sys as _sys

    from tapps_mcp.distribution.exe_manager import detect_stale_backups

    if not getattr(_sys, "frozen", False):
        return CheckResult(
            "Stale exe backups",
            True,
            "Not running as frozen exe (check not applicable)",
        )

    old_files = detect_stale_backups()
    if not old_files:
        return CheckResult("Stale exe backups", True, "No stale .old backups found")

    names = [f.name for f in old_files]
    return CheckResult(
        "Stale exe backups",
        False,
        f"Stale exe backup(s) found: {', '.join(names)}",
        "These will be cleaned up automatically on next startup, "
        "or delete them manually if no other tapps-mcp processes are running.",
    )


def check_tapps_brain() -> CheckResult:
    """Check that the tapps-brain memory library is importable.

    tapps-brain was extracted from tapps-core as a standalone library.
    All memory modules in tapps-core delegate to tapps-brain; if it is
    missing, memory operations will fail at runtime.
    """
    try:
        import tapps_brain

        version = getattr(tapps_brain, "__version__", "(unknown)")
        return CheckResult(
            "tapps-brain library",
            True,
            f"tapps-brain {version} available",
        )
    except ImportError as exc:
        return CheckResult(
            "tapps-brain library",
            False,
            "tapps-brain not importable (memory subsystem unavailable)",
            f"Error: {exc}. Install: pip install tapps-brain>=1.0.0",
        )


def _run_auth_probe(http_url: str, settings: Any) -> dict[str, Any] | None:
    """TAP-2098: run a synchronous :meth:`HttpBrainBridge.auth_probe` for the
    doctor check.

    Builds a transient ``HttpBrainBridge`` from doctor-resolved settings so
    we never share state with the long-lived server bridge. Returns the
    probe dict (carrying ``ok``, ``gated``, ``suggested_profile`` …) or
    ``None`` when the probe cannot run.
    """
    try:
        from tapps_core.brain_bridge import HttpBrainBridge
    except Exception:
        return None
    try:
        headers = _doctor_brain_headers(settings)
        bridge = HttpBrainBridge(http_url, headers)
        result = bridge.auth_probe()
    except Exception:
        return None
    return result if isinstance(result, dict) else None


def check_brain_http_auth(root: Path) -> CheckResult:
    """Verify that HTTP-bridge auth config is complete when HTTP mode is active.

    When ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` is set, the client must also have
    ``memory.brain_auth_token`` (env: ``TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN``) and
    ``memory.brain_project_id``. Missing either silently sends unauthenticated
    (or partially authenticated) requests and every memory/hive call returns
    401 or 403 — but ``memory_status.degraded`` looked OK until we fixed it
    because the old probe only hit ``/health`` (unauthenticated).

    A common mistake is exporting ``TAPPS_BRAIN_AUTH_TOKEN`` in the shell but
    not mapping it to ``TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN`` for CLI doctor
    (MCP hosts expand ``${TAPPS_BRAIN_AUTH_TOKEN}`` in ``.mcp.json`` at launch).
    """
    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            "tapps-brain HTTP auth",
            True,
            "Not in HTTP mode (brain_http_url unset in env and .tapps-mcp.yaml)",
        )

    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings(project_root=root)
        token_present = _resolve_brain_auth_token(settings) is not None
        project_id_present = bool(settings.memory.brain_project_id)
    except Exception as exc:
        return CheckResult(
            "tapps-brain HTTP auth",
            False,
            f"Could not load settings: {exc}",
            "Fix .tapps-mcp.yaml or env vars and re-run doctor.",
        )

    if token_present and project_id_present:
        # TAP-2098: config looks good — actually probe the wire so the operator
        # sees ``out_of_profile`` denials (server returns 200 with a JSON-RPC
        # ``error.data.reason == "out_of_profile"`` envelope) before the first
        # runtime memory call fails. ``suggested_profile`` (v3.19.0+) becomes
        # the remediation hint.
        probe = _run_auth_probe(http_url, settings)
        if probe is not None and probe.get("gated"):
            tool = probe.get("tool") or "probe tool"
            profile = probe.get("profile") or "<unset>"
            suggested = probe.get("suggested_profile")
            hint = (
                f"Set TAPPS_BRAIN_PROFILE (or memory.brain_profile in "
                f".tapps-mcp.yaml) to {suggested!r} to expose {tool!r}."
                if suggested
                else (
                    f"No profile suggested by brain — pick a profile that "
                    f"exposes {tool!r} (e.g. ``operator`` or ``full``)."
                )
            )
            return CheckResult(
                "tapps-brain HTTP auth",
                False,
                f"HTTP auth ok but profile {profile!r} hides {tool!r}",
                hint,
            )
        return CheckResult(
            "tapps-brain HTTP auth",
            True,
            f"HTTP mode configured with bearer token + project id ({http_url})",
        )

    missing: list[str] = []
    hints: list[str] = []
    if not token_present:
        missing.append("brain_auth_token")
        hints.append(
            "Set TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN or memory.brain_auth_token in "
            ".tapps-mcp.yaml (same value as TAPPS_BRAIN_AUTH_TOKEN is fine). "
            "Shell CLI (`tapps-mcp memory save/get`, `session-end`) reads this "
            "env directly — export it in .env/direnv even when MCP expands "
            "${TAPPS_BRAIN_AUTH_TOKEN} at IDE launch."
        )
    if not project_id_present:
        missing.append("brain_project_id")
        hints.append(
            "Set TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID or memory.brain_project_id "
            "in .tapps-mcp.yaml (registered tapps-brain project slug)."
        )

    return CheckResult(
        "tapps-brain HTTP auth",
        False,
        f"HTTP mode active but missing: {', '.join(missing)}",
        " ".join(hints),
    )


# TAP-2115: module-level ETag cache for /v1/tools/list responses, keyed by
# (http_url, profile-header). Lets repeat `tapps doctor` invocations within
# the brain's 300 s Cache-Control window short-circuit to 304 + cached set.
_TOOLS_CATALOG_CACHE: dict[tuple[str, str], tuple[str, frozenset[str]]] = {}


class _ProfileProbeError(Exception):
    """Internal control-flow exception for check_brain_profile failures."""

    def __init__(self, detail: str, hint: str = "") -> None:
        super().__init__(detail)
        self.detail = detail
        self.hint = hint


def _fetch_exposed_tools(
    http_url: str,
    headers: dict[str, str],
    httpx_mod: Any,
    mcp_accept_headers: dict[str, str],
) -> tuple[set[str], str]:
    """TAP-2115 (consumes TAP-1971): fetch the exposed tool set, preferring
    the cacheable REST endpoint and falling back to the JSON-RPC handshake
    on older brains.

    Returns ``(exposed_tool_names, source_label)`` where ``source_label`` is
    one of ``"rest"``, ``"rest-cached"`` (304 hit), or ``"jsonrpc"``.
    """
    try:
        return _fetch_exposed_tools_rest(http_url, headers, httpx_mod)
    except _ProfileProbeFallbackError:
        return _fetch_exposed_tools_jsonrpc(http_url, headers, httpx_mod, mcp_accept_headers)


class _ProfileProbeFallbackError(Exception):
    """Internal signal that the REST path is unavailable; try JSON-RPC."""


def _fetch_exposed_tools_rest(
    http_url: str, headers: dict[str, str], httpx_mod: Any
) -> tuple[set[str], str]:
    """GET ``/v1/tools/list`` with ``If-None-Match`` from the module cache.

    Sends only ``X-Brain-Profile`` and ``If-None-Match`` — the REST endpoint
    is unauthenticated and Origin-exempt (TAP-1843), so we deliberately do
    NOT forward the bearer token here. Raises :class:`_ProfileProbeFallbackError`
    when the endpoint isn't available (404 ⇒ pre-TAP-1843 brain) so the
    caller can switch to the JSON-RPC handshake.
    """
    profile_header = headers.get("X-Brain-Profile") or ""
    cache_key = (http_url, profile_header)
    cached = _TOOLS_CATALOG_CACHE.get(cache_key)
    req_headers: dict[str, str] = {}
    if profile_header:
        req_headers["X-Brain-Profile"] = profile_header
    if cached is not None:
        req_headers["If-None-Match"] = cached[0]
    try:
        response = httpx_mod.get(
            f"{http_url.rstrip('/')}/v1/tools/list",
            headers=req_headers,
            timeout=5.0,
            follow_redirects=True,
        )
    except Exception:
        raise _ProfileProbeFallbackError() from None
    if response.status_code == 304 and cached is not None:
        return set(cached[1]), "rest-cached"
    if response.status_code == 404:
        raise _ProfileProbeFallbackError()
    if response.status_code != 200:
        raise _ProfileProbeError(
            f"/v1/tools/list returned {response.status_code}",
            "Brain rejected the REST tool-list probe; check brain version + profile name.",
        )
    try:
        payload = response.json()
    except Exception as exc:
        raise _ProfileProbeError(
            f"/v1/tools/list returned non-JSON body: {exc}",
            "Brain misconfigured; expected application/json with a `tools` array.",
        ) from exc
    tools = payload.get("tools", []) if isinstance(payload, dict) else []
    exposed = {
        str(t["name"])
        for t in tools
        if isinstance(t, dict) and isinstance(t.get("name"), str) and t["name"]
    }
    etag = response.headers.get("etag") or response.headers.get("ETag") or ""
    if etag:
        _TOOLS_CATALOG_CACHE[cache_key] = (etag, frozenset(exposed))
    return exposed, "rest"


def _fetch_exposed_tools_jsonrpc(
    http_url: str,
    headers: dict[str, str],
    httpx_mod: Any,
    mcp_accept_headers: dict[str, str],
) -> tuple[set[str], str]:
    """Legacy fallback: full MCP handshake + JSON-RPC ``tools/list``.

    Kept for brains <3.18.0 that don't expose the REST endpoint.
    """
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "tapps-mcp-doctor", "version": "1"},
        },
    }
    try:
        init_response = httpx_mod.post(
            f"{http_url.rstrip('/')}/mcp/",
            json=init_payload,
            headers={**headers, **mcp_accept_headers},
            timeout=5.0,
            follow_redirects=True,
        )
        init_response.raise_for_status()
    except Exception as exc:
        raise _ProfileProbeError(
            f"Could not initialize MCP session at {http_url}: {exc}",
            "Brain may be down or unreachable; see brain logs.",
        ) from exc
    session_id = init_response.headers.get("mcp-session-id", "")
    list_headers = {**headers, **mcp_accept_headers}
    if session_id:
        list_headers["Mcp-Session-Id"] = session_id
    try:
        list_response = httpx_mod.post(
            f"{http_url.rstrip('/')}/mcp/",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers=list_headers,
            timeout=5.0,
            follow_redirects=True,
        )
        list_response.raise_for_status()
        payload = list_response.json()
    except Exception as exc:
        raise _ProfileProbeError(
            f"tools/list failed: {exc}",
            "Brain returned an error to tools/list; check brain version + auth.",
        ) from exc
    tools_meta = payload.get("result", {}).get("tools", [])
    exposed = {
        str(t["name"])
        for t in tools_meta
        if isinstance(t, dict) and isinstance(t.get("name"), str) and t["name"]
    }
    return exposed, "jsonrpc"


def _probe_warm_cache_status(root: Path, headers: dict[str, str]) -> str:
    """TAP-1927: return a short human-readable label for the warm-cache state.

    Labels: ``warm(<age>s)`` when the pre-warm file is present and within TTL,
    ``stale(<age>s)`` when it exists but has expired, or ``miss`` when absent.
    """
    import re as _re
    import time as _time

    from tapps_core.brain_bridge import _TOOLS_CACHE_TTL_SECONDS

    raw_profile = headers.get("X-Brain-Profile") or ""
    safe_profile = _re.sub(r"[^A-Za-z0-9_-]", "_", raw_profile) if raw_profile else ""
    cache_file = root / ".tapps-mcp" / f".brain-tools-list.{safe_profile}.json"
    try:
        if not cache_file.exists():
            return "miss"
        age = _time.time() - cache_file.stat().st_mtime
        age_s = int(age)
        if age < _TOOLS_CACHE_TTL_SECONDS:
            return f"warm({age_s}s)"
        return f"stale({age_s}s)"
    except Exception:
        return "miss"


def check_brain_profile(root: Path) -> CheckResult:
    """TAP-1629 / TAP-2100: probe the tapps-brain capability profile via tools/list.

    Surfaces (a) the declared ``X-Brain-Profile`` header, (b) the count of
    tools the active profile's eager ``tools/list`` returns, and (c) any
    tools the HTTP bridge invokes that are missing from that catalog.

    Under tapps-brain v3.19.0+ (TAP-1985), the ``full`` and ``operator``
    profiles default to an 8-tool eager catalog with the remaining tools
    deferred-loaded — these are still callable via ``tools/call`` but
    absent from ``tools/list``. After TAP-2100 the bridge no longer
    preflight-rejects on this list, so missing entries are diagnostic, not
    runtime-blocking. A genuine profile mismatch (e.g. switching to
    ``coder`` on a brain that hides ``memory_save``) still surfaces as
    :class:`ToolNotInProfileError` on the first call.

    Skipped (passing) when HTTP mode is not active.
    """
    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            "tapps-brain capability profile",
            True,
            "Not in HTTP mode (brain_http_url unset in env and .tapps-mcp.yaml)",
        )

    try:
        import tapps_mcp.server_memory_tools  # noqa: F401 — TAP-1961 registration
        from tapps_core.brain_bridge import (
            _MCP_ACCEPT_HEADERS,
            BRAIN_PROFILE_SERVER,
            BRAIN_PROFILES_DEFERRED_OK,
            get_bridge_used_tools,
        )
        from tapps_core.config.settings import load_settings
    except Exception as exc:
        return CheckResult(
            "tapps-brain capability profile",
            False,
            f"Could not load bridge modules: {exc}",
            "Re-run after fixing the import error.",
        )

    try:
        settings = load_settings(project_root=root)
        headers = _doctor_brain_headers(settings)
    except Exception as exc:
        return CheckResult(
            "tapps-brain capability profile",
            False,
            f"Could not build brain auth headers: {exc}",
            "Fix .tapps-mcp.yaml or env vars and re-run doctor.",
        )

    # ADR-0012: when no profile is configured, the runtime server bridge applies
    # BRAIN_PROFILE_SERVER as its default_profile. Probe with that same effective
    # profile so the diagnosis matches what the tapps_memory facade actually uses.
    if "X-Brain-Profile" not in headers:
        headers["X-Brain-Profile"] = BRAIN_PROFILE_SERVER
        effective_profile = BRAIN_PROFILE_SERVER
        declared = f"{BRAIN_PROFILE_SERVER} (server default)"
    else:
        effective_profile = headers["X-Brain-Profile"]
        declared = effective_profile

    # TAP-1927: report the warm-cache status alongside the live probe result.
    _warm_cache_label = _probe_warm_cache_status(root, headers)

    try:
        import httpx as _httpx
    except Exception as exc:
        return CheckResult(
            "tapps-brain capability profile",
            False,
            f"httpx unavailable: {exc}",
        )

    try:
        exposed, source = _fetch_exposed_tools(http_url, headers, _httpx, _MCP_ACCEPT_HEADERS)
    except _ProfileProbeError as exc:
        return CheckResult(
            "tapps-brain capability profile",
            False,
            exc.detail,
            exc.hint,
        )

    gated_used = sorted(get_bridge_used_tools() - exposed)

    if not gated_used:
        return CheckResult(
            "tapps-brain capability profile",
            True,
            f"profile={declared}, exposed={len(exposed)} tools "
            f"({source}), no bridge mismatch; warm-cache={_warm_cache_label}",
        )

    # ADR-0012: distinguish a benign deferred-loading gap (``full``/``operator``,
    # where the missing tools carry ``defer_loading`` and remain callable via
    # tools/call — TAP-1985) from a genuine profile gate (``coder``/``reviewer``/
    # ``agent_brain``/``seeder``, where the tools are absent from the profile and
    # tools/call rejects them with ToolNotInProfileError).
    if effective_profile in BRAIN_PROFILES_DEFERRED_OK:
        return CheckResult(
            "tapps-brain capability profile",
            True,
            f"profile={declared}, {len(gated_used)} bridge tool(s) deferred from eager "
            f"tools/list but callable via tools/call ({source}); warm-cache={_warm_cache_label}",
        )

    return CheckResult(
        "tapps-brain capability profile",
        False,
        f"profile={declared} GATES {len(gated_used)} bridge tool(s) ({source}): "
        f"{', '.join(gated_used)}; these calls fail with ToolNotInProfileError on "
        f"tapps-brain v3.20.0+; warm-cache={_warm_cache_label}",
        "The declared profile is too narrow for the tapps_memory facade. Set "
        "memory.brain_profile (or TAPPS_BRAIN_PROFILE) to 'full' (ADR-0012) — or "
        "'operator' if maintenance ops must run live — so the bridge's tools are "
        "exposed. 'coder'/'reviewer'/'agent_brain' are intended for narrower consumers.",
    )


_BRAIN_PROBE_METRIC = "tapps_brain_mcp_probe_duration_seconds"


def _parse_histogram_quantiles(
    metrics_text: str,
    metric: str,
    quantiles: tuple[float, ...],
) -> dict[float, float] | None:
    """Parse a Prometheus histogram from ``/metrics`` text into quantiles.

    Returns ``{quantile: seconds}`` computed from the cumulative
    ``<metric>_bucket{le=...}`` counts via linear interpolation within the
    matched bucket (the ``histogram_quantile`` algorithm). Bucket counts are
    summed across label sets at the same ``le`` (equivalent to PromQL
    ``sum by (le)``) so multi-series histograms aggregate cleanly. Returns
    ``None`` when the metric/buckets are absent or the total count is zero.
    """
    import math
    import re

    pattern = re.compile(
        r"^" + re.escape(metric) + r'_bucket\{[^}]*\ble="([^"]+)"[^}]*\}\s+([0-9.eE+]+)',
        re.MULTILINE,
    )
    agg: dict[float, float] = {}
    for le_raw, count_raw in pattern.findall(metrics_text):
        try:
            le = math.inf if le_raw in ("+Inf", "Inf") else float(le_raw)
            count = float(count_raw)
        except ValueError:
            continue
        agg[le] = agg.get(le, 0.0) + count
    if not agg:
        return None
    buckets = sorted(agg.items())  # ascending by le; +Inf sorts last
    total = buckets[-1][1]
    if total <= 0:
        return None

    out: dict[float, float] = {}
    for q in quantiles:
        rank = q * total
        prev_le = 0.0
        prev_count = 0.0
        value = buckets[-1][0]
        for le, cum in buckets:
            if cum >= rank:
                if math.isinf(le):
                    # quantile falls in the +Inf bucket — best lower-bound
                    # estimate is the largest finite le seen so far.
                    value = prev_le
                else:
                    bucket_count = cum - prev_count
                    value = (
                        le
                        if bucket_count <= 0
                        else prev_le + (le - prev_le) * (rank - prev_count) / bucket_count
                    )
                break
            prev_le = le
            prev_count = cum
        out[q] = value
    return out


def check_brain_probe_latency(root: Path) -> CheckResult:
    """TAP-1931: surface tapps-brain MCP probe latency quantiles in doctor.

    GETs ``{brain_http_url}/metrics`` and parses the
    ``tapps_brain_mcp_probe_duration_seconds`` histogram (TAP-1849) into
    p50 / p95 / p99. Reports ``unavailable`` (passing) on any error or when
    the metric is absent — telemetry gaps must never fail the doctor run.
    Profile parity stays in :func:`check_brain_profile`; this check is
    latency-only.

    Skipped (passing) when HTTP mode is not active.
    """
    name = "tapps-brain probe latency"
    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            name,
            True,
            "Not in HTTP mode (brain_http_url unset in env and .tapps-mcp.yaml)",
        )

    headers: dict[str, str] = {}
    try:
        from tapps_core.config.settings import load_settings

        headers = _doctor_brain_headers(load_settings(project_root=root))
    except Exception:
        headers = {}

    metrics_url = http_url.rstrip("/") + "/metrics"
    try:
        resp = httpx.get(metrics_url, headers=headers, timeout=5.0)
    except Exception as exc:
        return CheckResult(name, True, f"probe latency: unavailable ({type(exc).__name__})")
    if resp.status_code != 200:
        return CheckResult(
            name, True, f"probe latency: unavailable (/metrics HTTP {resp.status_code})"
        )

    quantiles = _parse_histogram_quantiles(resp.text, _BRAIN_PROBE_METRIC, (0.5, 0.95, 0.99))
    if not quantiles:
        return CheckResult(name, True, "probe latency: unavailable (metric absent in /metrics)")

    return CheckResult(
        name,
        True,
        "mcp_probe_duration "
        f"p50: {quantiles[0.5]:.3f}s / p95: {quantiles[0.95]:.3f}s "
        f"/ p99: {quantiles[0.99]:.3f}s",
    )


def check_brain_health(root: Path) -> CheckResult:
    """TAP-1632: pull flywheel + diagnostics summary from tapps-brain.

    Synchronously calls ``flywheel_report`` and ``diagnostics_report``
    against the configured HTTP brain and renders a compact summary so
    operators can see at a glance whether feedback is flowing into the
    flywheel and whether brain-side quality metrics are degrading.
    Skipped (passing) when HTTP mode is not active.
    """
    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            "tapps-brain health",
            True,
            "Not in HTTP mode (brain_http_url unset in env and .tapps-mcp.yaml)",
        )

    try:
        from tapps_core.brain_bridge import _MCP_ACCEPT_HEADERS
        from tapps_core.config.settings import load_settings
    except Exception as exc:
        return CheckResult(
            "tapps-brain health",
            False,
            f"Could not load bridge modules: {exc}",
            "Re-run after fixing the import error.",
        )

    try:
        settings = load_settings(project_root=root)
        headers = _doctor_brain_headers(settings)
    except Exception as exc:
        return CheckResult(
            "tapps-brain health",
            False,
            f"Could not build brain auth headers: {exc}",
            "Fix .tapps-mcp.yaml or env vars and re-run doctor.",
        )

    try:
        import httpx as _httpx
    except Exception as exc:
        return CheckResult(
            "tapps-brain health",
            False,
            f"httpx unavailable: {exc}",
        )

    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "tapps-mcp-doctor", "version": "1"},
        },
    }
    try:
        init_response = _httpx.post(
            f"{http_url.rstrip('/')}/mcp/",
            json=init_payload,
            headers={**headers, **_MCP_ACCEPT_HEADERS},
            timeout=5.0,
            follow_redirects=True,
        )
        init_response.raise_for_status()
    except Exception as exc:
        return CheckResult(
            "tapps-brain health",
            False,
            f"Could not initialize MCP session: {exc}",
            "Brain may be down or unreachable; see brain logs.",
        )

    session_id = init_response.headers.get("mcp-session-id", "")
    call_headers = {**headers, **_MCP_ACCEPT_HEADERS}
    if session_id:
        call_headers["Mcp-Session-Id"] = session_id

    def _tool_call(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        try:
            response = _httpx.post(
                f"{http_url.rstrip('/')}/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": args},
                },
                headers=call_headers,
                timeout=5.0,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None
        result = payload.get("result", {})
        if not isinstance(result, dict) or result.get("isError"):
            return None
        content = result.get("content", [])
        if not content or content[0].get("type") != "text":
            return None
        try:
            import json as _json

            parsed = _json.loads(content[0]["text"])
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    flywheel = _tool_call("flywheel_report", {"period_days": 7})
    diagnostics = _tool_call("diagnostics_report", {"record_history": False})

    if flywheel is None and diagnostics is None:
        return CheckResult(
            "tapps-brain health",
            False,
            "Could not fetch flywheel_report or diagnostics_report from brain",
            "These tools require tapps-brain 3.17+ and the operator/full profile.",
        )

    parts: list[str] = []
    if flywheel is not None:
        gaps = flywheel.get("gap_count") or flywheel.get("gaps") or 0
        rates = flywheel.get("rating_count") or flywheel.get("ratings") or 0
        period = flywheel.get("period_days", 7)
        parts.append(f"flywheel: {gaps} gap(s) / {rates} rating(s) in {period}d")
    if diagnostics is not None:
        score = diagnostics.get("health_score") or diagnostics.get("score")
        if score is not None:
            parts.append(f"diagnostics health_score={score}")
        else:
            parts.append("diagnostics: snapshot available")

    return CheckResult(
        "tapps-brain health",
        True,
        "; ".join(parts) if parts else "brain reports clean health",
        (
            "Detail under `tapps_memory(action=health)` and the brain's "
            "flywheel_report/diagnostics_report tools."
        ),
    )


def _parse_version_tuple(ver_str: str) -> tuple[int, int, int]:
    """Parse ``'3.18.0'`` → ``(3, 18, 0)``.  Returns ``(0, 0, 0)`` on error."""
    try:
        parts = ver_str.split(".")[:3]
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0, int(parts[2]) if len(parts) > 2 else 0)
    except Exception:
        return (0, 0, 0)


def _read_brain_floor_pin() -> str | None:
    """Return the ``tapps-brain`` floor version from ``tapps-core`` package metadata.

    Parses ``requires('tapps-core')`` looking for a ``tapps-brain>=X.Y.Z`` entry and
    returns ``X.Y.Z``.  Returns ``None`` when the metadata is unavailable or the
    requirement cannot be parsed.
    """
    try:
        for req in (_requires("tapps-core") or []):
            m = re.match(r"^tapps.brain\s*>=\s*([0-9]+\.[0-9]+(?:\.[0-9]+)?)", req, re.IGNORECASE)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def check_brain_version_floor(root: Path) -> CheckResult:
    """Fail when the running brain HTTP service is below the pinned version floor.

    Uses :func:`tapps_core.brain_bridge.check_brain_version` against the resolved
    HTTP URL so operators see the same hard floor enforcement as
    ``brain_bridge_health.details.brain_version`` at session start.
    """
    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            "tapps-brain version floor",
            True,
            "Not in HTTP mode (brain_http_url unset in env and .tapps-mcp.yaml)",
        )

    from tapps_core.brain_bridge import _BRAIN_VERSION_FLOOR, check_brain_version

    probe = check_brain_version(http_url)
    floor = probe.get("floor") or _BRAIN_VERSION_FLOOR
    version = probe.get("version")
    if probe.get("skipped"):
        return CheckResult(
            "tapps-brain version floor",
            True,
            "Version probe skipped (no HTTP URL)",
        )
    if probe.get("degraded") and not version:
        return CheckResult(
            "tapps-brain version floor",
            False,
            f"Could not reach brain at {http_url} for version probe",
            "Start tapps-brain-http and re-run doctor.",
        )
    if probe.get("ok"):
        return CheckResult(
            "tapps-brain version floor",
            True,
            f"brain {version} satisfies >={floor}",
        )
    errors = probe.get("errors") or probe.get("warnings") or []
    detail = errors[0] if errors else f"brain {version!s} below required >={floor}"
    return CheckResult(
        "tapps-brain version floor",
        False,
        detail,
        f"Upgrade tapps-brain-http to >={floor} (see ADR-0013).",
    )


def check_brain_version_delta(root: Path) -> CheckResult:
    """TAP-2025: compare the running brain-service version against the pinned floor.

    Reads the ``tapps-brain>=X.Y.Z`` floor constraint from ``tapps-core``'s
    installed package metadata and compares it against the live
    ``brain_version`` field returned by ``{brain_http_url}/healthz``.

    Emits WARN when the running brain version is more than 2 minor versions
    ahead of the floor pin — a signal that it is time to bump the pin.
    Emits CRITICAL when the major version differs (API-breaking).

    The check is skipped (passes) when HTTP mode is inactive.
    """
    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            "tapps-brain version delta",
            True,
            "Not in HTTP mode (brain_http_url unset in env and .tapps-mcp.yaml)",
        )

    # Probe /healthz (v3.19.0+) first; fall back to /health for older brains
    brain_ver_str: str | None = None
    for path in ("/healthz", "/health"):
        try:
            resp = httpx.get(f"{http_url.rstrip('/')}{path}", timeout=3.0)
            resp.raise_for_status()
            body = resp.json()
            brain_ver_str = body.get("brain_version") or body.get("version")
            if brain_ver_str:
                break
        except Exception:
            continue

    if not brain_ver_str:
        return CheckResult(
            "tapps-brain version delta",
            True,
            "Brain health endpoint did not return a version — skipping delta check",
        )

    floor_str = _read_brain_floor_pin()
    if not floor_str:
        return CheckResult(
            "tapps-brain version delta",
            True,
            f"Running brain {brain_ver_str} (floor pin unresolvable from tapps-core metadata)",
        )

    running = _parse_version_tuple(brain_ver_str)
    floor = _parse_version_tuple(floor_str)
    running_str = ".".join(str(v) for v in running)
    floor_str_fmt = ".".join(str(v) for v in floor)

    if running[0] != floor[0]:
        return CheckResult(
            "tapps-brain version delta",
            False,
            f"CRITICAL: major version mismatch — running {running_str}, floor pin {floor_str_fmt}",
            "Update the tapps-brain pin in tapps-core/pyproject.toml and re-install.",
        )

    minor_delta = running[1] - floor[1]
    if minor_delta > 2:
        return CheckResult(
            "tapps-brain version delta",
            False,
            (
                f"WARN: running brain {running_str} is {minor_delta} minor version(s) "
                f"ahead of floor pin {floor_str_fmt}"
            ),
            f"Bump tapps-brain floor in tapps-core/pyproject.toml to >={running_str}.",
        )

    return CheckResult(
        "tapps-brain version delta",
        True,
        (
            f"brain {running_str} within 2 minor versions of floor pin "
            f"{floor_str_fmt} (delta={minor_delta})"
        ),
    )


# ---------------------------------------------------------------------------
# TAP-2026 / TAP-1989: per-server eager-tool budget
# ---------------------------------------------------------------------------

# Known preset tool counts — keep in sync with server.py (ALL_TOOL_NAMES,
# TAPPS_TOOL_PRESET_QUALITY, TAPPS_TOOL_PRESET_ADMIN).
# TAP-1986: counts reflect EAGER tools only (defer_loading=False).
# Non-daily-driver tools carry defer_loading=True and are loaded on-demand via Tool Search.
_TAPPS_MCP_MODE_TOOL_COUNTS: dict[str, int] = {
    # TAP-1986 set 8 eager; tapps_usage added in v3.11.0 raised this to 9.
    # Eager set: session_start, validate_changed, score_file, quality_gate,
    # quick_check, lookup_docs, checklist, impact_analysis, usage (9 total).
    # Deferred: 26 (full=35 total; quality=15 total; admin=13 total).
    "full": 9,     # 9 eager daily-driver tools; 26 deferred via Tool Search (35 total)
    "quality": 9,  # 9 eager (all 9 daily drivers are in the quality preset; 6 deferred)
    "admin": 1,    # 1 eager (tapps_usage); 12 deferred
}
_DOCS_MCP_TOOL_COUNT: int = 6  # TAP-1987: 6 eager tools; 32 deferred via Tool Search
_DEFAULT_TOOL_BUDGET: int = 20


def _detect_server_tool_count(server_name: str, server_cfg: dict[str, object]) -> int | None:
    """Return the eager-tool count for a known tapps-family MCP server, or None.

    Returns ``None`` for servers that require a live connection to probe
    (e.g. HTTP or unknown stdio servers).
    """
    from tapps_mcp.distribution.nlt_mcp_config import (
        NLT_SERVER_EAGER_COUNTS,
        is_nlt_server_id,
        nlt_eager_count,
    )

    if is_nlt_server_id(server_name):
        return nlt_eager_count(server_name)

    raw_args = server_cfg.get("args", [])
    args: list[str] = list(raw_args) if isinstance(raw_args, list) else []
    command: str = str(server_cfg.get("command", ""))

    if "--profile" in args:
        idx = args.index("--profile")
        if idx + 1 < len(args):
            profile = str(args[idx + 1])
            if profile in NLT_SERVER_EAGER_COUNTS:
                return NLT_SERVER_EAGER_COUNTS[profile]

    # tapps-mcp family: command is uv/uvx/python3, "tapps-mcp" and "serve" in args
    if "tapps-mcp" in args and "serve" in args:
        mode = "full"
        if "--mode" in args:
            idx = args.index("--mode")
            if idx + 1 < len(args):
                mode = args[idx + 1]
        return _TAPPS_MCP_MODE_TOOL_COUNTS.get(mode, _TAPPS_MCP_MODE_TOOL_COUNTS["full"])
    # uvx tapps-mcp serve (no explicit "run")
    if command in ("uvx",) and "tapps-mcp" in args:
        return _TAPPS_MCP_MODE_TOOL_COUNTS["full"]
    # docs-mcp family: "docsmcp" in args or command
    if "docsmcp" in args or "docsmcp" in command:
        return _DOCS_MCP_TOOL_COUNT
    # tapps-platform NLT profiles (Epic 109)
    if "tapps-platform" in args and "serve" in args and "--profile" in args:
        idx = args.index("--profile")
        if idx + 1 < len(args):
            profile = str(args[idx + 1])
            from tapps_mcp.distribution.nlt_mcp_config import NLT_SERVER_EAGER_COUNTS

            if profile in NLT_SERVER_EAGER_COUNTS:
                return NLT_SERVER_EAGER_COUNTS[profile]
    return None


_CALL_GRAPH_TOOLS: frozenset[str] = frozenset({"tapps_call_graph", "tapps_diff_impact"})
_CALL_GRAPH_MIN_VERSION: str = "3.12.30"


def _project_uses_nlt_build(servers: dict[str, dict[str, object]]) -> bool:
    """True when MCP config enables nlt-build (or legacy nlt-code-quality)."""
    if "nlt-build" in servers or "nlt-code-quality" in servers:
        return True
    for _name, cfg in servers.items():
        raw_args = cfg.get("args", [])
        args: list[str] = list(raw_args) if isinstance(raw_args, list) else []
        if "--profile" in args:
            idx = args.index("--profile")
            if idx + 1 < len(args) and str(args[idx + 1]) in {"nlt-build", "nlt-code-quality"}:
                return True
        command = str(cfg.get("command", ""))
        if "nlt-build-serve" in command or "nlt-code-quality-serve" in command:
            return True
    return False


def _resolve_nlt_build_allowed_tools(settings: Any) -> frozenset[str]:
    """Tools exposed by the nlt-build MCP server (ignores host process preset)."""
    from tapps_mcp.server import ALL_TOOL_NAMES, TOOL_PROFILE_NLT_BUILD

    if settings.enabled_tools:
        allowed = set(settings.enabled_tools) & ALL_TOOL_NAMES
    else:
        allowed = set(TOOL_PROFILE_NLT_BUILD)
    allowed -= set(settings.disabled_tools)
    return frozenset(allowed)


def check_call_graph_tools_profile(root: Path) -> CheckResult:
    """Epic 114: WARN when call-graph MCP tools are stripped or package is too old."""
    from packaging.version import Version

    from tapps_core.config.settings import load_settings
    from tapps_mcp import __version__

    servers = _collect_project_mcp_servers(root)
    if not _project_uses_nlt_build(servers):
        return CheckResult(
            "Call graph tools",
            True,
            "No nlt-build MCP server configured (skipped)",
        )

    if Version(__version__) < Version(_CALL_GRAPH_MIN_VERSION):
        return CheckResult(
            "Call graph tools",
            False,
            (
                f"tapps-mcp {__version__} < {_CALL_GRAPH_MIN_VERSION} — "
                "call graph unavailable; reinstall globals and reload MCP"
            ),
            "uv tool install --reinstall --from <checkout>/packages/tapps-mcp tapps-mcp",
        )

    try:
        settings = load_settings(project_root=root)
    except Exception as exc:
        return CheckResult(
            "Call graph tools",
            True,
            f"Skipped (could not load settings: {exc})",
        )

    allowed = _resolve_nlt_build_allowed_tools(settings)
    missing = _CALL_GRAPH_TOOLS - allowed
    if missing:
        return CheckResult(
            "Call graph tools",
            False,
            f"Stripped from nlt-build profile: {', '.join(sorted(missing))}",
            "Remove from disabled_tools or widen enabled_tools in .tapps-mcp.yaml",
        )

    return CheckResult(
        "Call graph tools",
        True,
        "tapps_call_graph and tapps_diff_impact registered on nlt-build",
    )


def check_call_graph_index_cache(root: Path, *, quick: bool = False) -> CheckResult:
    """Epic 114: informational call-graph cache status (never fails on missing cache)."""
    from tapps_mcp.project.call_graph_cache import (
        load_call_graph_index,
        summarize_call_graph_cache,
    )
    from tapps_mcp.project.call_graph_types import CALL_GRAPH_CACHE_REL

    cache_path = root / CALL_GRAPH_CACHE_REL
    if not cache_path.is_file():
        return CheckResult(
            "Call graph index",
            True,
            "No cache yet (normal until first tapps_call_graph or tapps_diff_impact call)",
        )

    cached = load_call_graph_index(root)
    if cached is None:
        return CheckResult(
            "Call graph index",
            True,
            "Cache file unreadable — will rebuild on next graph tool call",
            str(cache_path),
        )

    summary = summarize_call_graph_cache(root)
    parts = [
        f"Cache present ({len(cached.symbols)} symbols, {len(cached.edges)} edges)",
    ]
    if summary is not None:
        if summary.get("reason") == "index_version_mismatch":
            parts.append(
                "schema mismatch "
                f"v{summary.get('cached_version')} → v{summary.get('current_version')}"
            )
        elif summary.get("stale"):
            parts.append("stale — rebuild via tapps_call_graph(force_rebuild=true)")
        else:
            parts.append("fresh")
        gap_count = int(summary.get("resolution_gaps", 0))
        if gap_count:
            gap_reasons = summary.get("gap_reasons")
            if isinstance(gap_reasons, dict) and gap_reasons:
                reason_bits = ", ".join(f"{k}={v}" for k, v in gap_reasons.items())
                parts.append(f"{gap_count} resolution gaps ({reason_bits})")
            else:
                parts.append(f"{gap_count} resolution gaps")
        parse_failures = int(summary.get("parse_failures", 0))
        if parse_failures:
            parts.append(f"{parse_failures} parse failure(s)")

    return CheckResult(
        "Call graph index",
        True,
        "; ".join(parts),
        str(cache_path),
    )


def _collect_project_mcp_servers(root: Path) -> dict[str, dict[str, object]]:
    """Load enabled MCP server entries from project-scoped config files."""
    from tapps_mcp.distribution.setup_generator import (
        _get_config_path,
        _get_servers_key,
        _load_mcp_config_json,
    )

    merged: dict[str, dict[str, object]] = {}
    for host in ("claude-code", "cursor", "vscode"):
        path = _get_config_path(host, root)
        if not path.exists():
            continue
        data = _load_mcp_config_json(path)
        servers_key = _get_servers_key(host)
        servers = data.get(servers_key)
        if not isinstance(servers, dict):
            continue
        for name, entry in servers.items():
            if isinstance(entry, dict):
                merged[str(name)] = entry
    return merged


def _nlt_partial_enablement_remediation() -> str:
    """Actionable doctor hint when too many nlt-* servers are enabled (EPIC-112)."""
    from tapps_mcp.distribution.nlt_mcp_config import enabled_servers_for_bundle

    developer = ", ".join(enabled_servers_for_bundle("developer"))
    minimal = ", ".join(enabled_servers_for_bundle("minimal"))
    return (
        f"Enable only the recommended bundle in your IDE MCP settings. "
        f"Developer bundle ({developer}) stays within the ≤3-server budget; "
        f"use minimal ({minimal}) for build-only sessions. "
        "Run: tapps-mcp init --host cursor --force --allow-package-init --no-uv "
        "to regenerate mcp.json with commented opt-in servers. "
        "See docs/architecture/nlt-mcp-plugin-spec.yaml."
    )


def check_nlt_partial_enablement(root: Path) -> CheckResult:
    """Epic 109.5: WARN when too many ``nlt-*`` MCP servers or combined eager tools.

    Reads ``.mcp.json``, ``.cursor/mcp.json``, and ``.vscode/mcp.json`` when
    present. Targets partial enablement: ≤3 servers and ≤20 combined eager tools.
    """
    from tapps_mcp.distribution.nlt_mcp_config import (
        NLT_MAX_COMBINED_EAGER,
        NLT_MAX_ENABLED_SERVERS,
        NLT_SERVER_ORDER,
        enabled_servers_for_bundle,
        list_nlt_server_ids_in_config,
        nlt_eager_count,
        nlt_total_tool_count,
    )

    servers = _collect_project_mcp_servers(root)
    nlt_ids = list_nlt_server_ids_in_config(servers)
    if not nlt_ids:
        return CheckResult(
            "NLT partial enablement",
            True,
            "No nlt-* MCP servers configured (legacy monolith or not bootstrapped)",
        )

    lines: list[str] = []
    combined_eager = 0
    for server_id in nlt_ids:
        eager = nlt_eager_count(server_id)
        if eager is None:
            detected = _detect_server_tool_count(server_id, servers[server_id])
            eager = detected if detected is not None else 0
        total = nlt_total_tool_count(server_id)
        combined_eager += eager
        total_label = str(total) if total is not None else "?"
        lines.append(f"{server_id}: {eager} eager / {total_label} total")

    summary = (
        f"{len(nlt_ids)} server(s); combined eager={combined_eager}; "
        + "; ".join(lines)
    )
    if set(nlt_ids) == set(NLT_SERVER_ORDER):
        bundle = _resolved_mcp_bundle(root)
        if bundle == "full":
            return CheckResult(
                "NLT partial enablement",
                True,
                (
                    f"Intentional full bundle (mcp_bundle=full): all six nlt-* servers "
                    f"enabled. {summary}"
                ),
            )
        return CheckResult(
            "NLT partial enablement",
            False,
            (
                f"WARN: all six nlt-* servers enabled in MCP config. "
                f"Recommended active: {', '.join(enabled_servers_for_bundle('developer'))}. "
                f"{summary}"
            ),
            _nlt_partial_enablement_remediation(),
        )

    warnings: list[str] = []
    if len(nlt_ids) > NLT_MAX_ENABLED_SERVERS:
        warnings.append(
            f"{len(nlt_ids)} nlt-* servers enabled (recommended ≤{NLT_MAX_ENABLED_SERVERS})"
        )
    if combined_eager > NLT_MAX_COMBINED_EAGER:
        warnings.append(
            f"{combined_eager} combined eager tools (recommended ≤{NLT_MAX_COMBINED_EAGER})"
        )

    if warnings:
        return CheckResult(
            "NLT partial enablement",
            False,
            f"WARN: {'; '.join(warnings)}. {summary}",
            _nlt_partial_enablement_remediation(),
        )
    return CheckResult(
        "NLT partial enablement",
        True,
        f"Within partial-enablement targets. {summary}",
    )


def _read_tool_budget(root: Path) -> int:
    """Read ``doctor_tool_budget_limit`` from ``.tapps-mcp.yaml`` (default 20)."""
    import yaml  # pyyaml — always available

    config_path = root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return _DEFAULT_TOOL_BUDGET
    try:
        with config_path.open(encoding="utf-8") as fh:
            cfg: dict[str, object] = yaml.safe_load(fh) or {}
        raw = cfg.get("doctor_tool_budget_limit", _DEFAULT_TOOL_BUDGET)
        return int(raw) if isinstance(raw, (int, float, str)) else _DEFAULT_TOOL_BUDGET
    except Exception:
        return _DEFAULT_TOOL_BUDGET


def check_mcp_tool_budget(root: Path) -> CheckResult:
    """TAP-2026/TAP-1989: WARN when a known MCP server exposes more eager tools than budget.

    Reads project MCP configs (``.mcp.json``, ``.cursor/mcp.json``, ``.vscode/mcp.json``),
    computes tool counts for recognized tapps-family servers from their ``--mode`` or
    ``--profile`` flag, and compares against the ``doctor_tool_budget_limit`` in
    ``.tapps-mcp.yaml`` (default 20).

    Only tapps-mcp / docs-mcp / nlt-* servers are probed; unknown or HTTP-only servers
    are skipped (they require a live connection).
    """
    servers = _collect_project_mcp_servers(root)
    if not servers:
        return CheckResult(
            "MCP tool budget",
            True,
            "No project MCP config found — skipping tool budget check",
        )

    budget = _read_tool_budget(root)
    lines: list[str] = []
    over_budget: list[str] = []

    for server_name, server_cfg in servers.items():
        count = _detect_server_tool_count(server_name, server_cfg)
        if count is None:
            continue
        tag = "WARN" if count > budget else "OK"
        lines.append(f"{server_name}: {count} tools [{tag}]")
        if count > budget:
            over_budget.append(f"{server_name}({count})")

    if not lines:
        return CheckResult(
            "MCP tool budget",
            True,
            f"No recognized tapps-family servers in MCP config (budget={budget})",
        )

    summary = f"budget={budget}; " + ", ".join(lines)
    if over_budget:
        return CheckResult(
            "MCP tool budget",
            False,
            f"WARN: {', '.join(over_budget)} exceed eager-tool budget. {summary}",
            "Reduce tool count with --mode quality/admin, disable extra nlt-* servers, "
            "or set doctor_tool_budget_limit in .tapps-mcp.yaml.",
        )
    return CheckResult("MCP tool budget", True, f"All servers within budget. {summary}")


def check_session_sentinel(root: Path) -> CheckResult:
    """TAP-1928: report the presence and age of the tapps_session_start sentinel.

    ``.tapps-mcp/.tapps-session-id`` is written after each full bootstrap and
    read by sub-agent MCP processes to skip redundant checker / brain-health /
    memory-GC phases (≈700 ms saved per sub-agent call).  Absent is not an
    error — it will be created on the next full ``tapps_session_start``.
    """
    import time as _time

    from tapps_mcp.tools.session_start_core import SENTINEL_FILENAME, SENTINEL_TTL_S

    sentinel = root / ".tapps-mcp" / SENTINEL_FILENAME
    if not sentinel.exists():
        return CheckResult(
            "session-start sentinel",
            True,
            f"{SENTINEL_FILENAME}: absent — will be created on next full bootstrap",
        )
    try:
        age_s = int(_time.time() - sentinel.stat().st_mtime)
    except OSError as exc:
        return CheckResult(
            "session-start sentinel",
            False,
            f"{SENTINEL_FILENAME}: stat failed — {exc}",
        )
    if age_s < SENTINEL_TTL_S:
        remaining = SENTINEL_TTL_S - age_s
        return CheckResult(
            "session-start sentinel",
            True,
            f"{SENTINEL_FILENAME}: fresh (age {age_s}s, {remaining}s until expiry)",
        )
    return CheckResult(
        "session-start sentinel",
        True,
        f"{SENTINEL_FILENAME}: stale (age {age_s}s > TTL {SENTINEL_TTL_S}s) — will refresh on next bootstrap",
    )


def check_memory_pipeline_config(root: Path) -> CheckResult:
    """Echo effective memory-related settings (informational; always passes).

    Surfaces flags for expert auto-save, recurring quick_check memory,
    architectural supersede, impact enrichment, and memory hooks so
    ``tapps-mcp doctor`` matches shipped defaults and project overrides.
    """
    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings(project_root=root)
        m = settings.memory
        mh = settings.memory_hooks
        msg = (
            f"memory.enabled={m.enabled} auto_save_quality={m.auto_save_quality} "
            f"track_recurring_quick_check={m.track_recurring_quick_check} "
            f"auto_supersede_architectural={m.auto_supersede_architectural} "
            f"enrich_impact_analysis={m.enrich_impact_analysis}; "
            f"hooks auto_recall={mh.auto_recall.enabled} "
            f"auto_capture={mh.auto_capture.enabled}"
        )
        return CheckResult(
            "Memory pipeline (effective config)",
            True,
            msg,
            "Override under `memory:` and `memory_hooks:` in .tapps-mcp.yaml. "
            "See docs/MEMORY_REFERENCE.md.",
        )
    except Exception as exc:
        return CheckResult(
            "Memory pipeline (effective config)",
            True,
            f"Could not load settings ({exc})",
            "See docs/MEMORY_REFERENCE.md",
        )


def check_memory_cli_http_mode(root: Path) -> CheckResult:
    """Advise HTTP-only consumers which ``tapps-mcp memory`` subcommands need a local DSN.

    ``save``, ``get``, ``recall``, and ``search`` route through BrainBridge when
    ``memory.brain_http_url`` is set. ``list``, ``delete``, ``import-file``,
    ``export-file``, and ``reseed`` still open a local :class:`MemoryStore` and
    require ``TAPPS_BRAIN_DATABASE_URL`` (ADR-007).
    """
    import os

    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            "Memory CLI (HTTP mode)",
            True,
            "Not in HTTP-only mode (brain_http_url unset)",
            "",
        )

    dsn = os.environ.get("TAPPS_BRAIN_DATABASE_URL", "").strip()
    if not dsn:
        try:
            from tapps_core.config.settings import load_settings

            settings = load_settings(project_root=root)
            raw_dsn = getattr(settings.memory, "database_url", "")
            dsn = str(raw_dsn or "").strip()
        except Exception:
            dsn = ""

    if dsn:
        return CheckResult(
            "Memory CLI (HTTP mode)",
            True,
            "Brain HTTP + local DSN — all memory CLI subcommands available",
            "",
        )

    return CheckResult(
        "Memory CLI (HTTP mode)",
        True,
        "Brain HTTP without local DSN — save/get/recall/search use BrainBridge",
        "list/delete/import/export/reseed still require TAPPS_BRAIN_DATABASE_URL. "
        "Cross-session handoff: use `memory save/get/recall/search` or "
        "`/tapps-handoff-session` + `/tapps-continue-session`.",
    )


def check_dual_memory_server(root: Path) -> CheckResult:
    """Fail when a direct tapps-brain MCP server is configured (split-brain risk).

    Delegates to :func:`check_brain_mcp_entry` for project MCP JSON files and
    also scans Claude ``settings.json`` hosts for legacy brain server entries.
    """
    primary = check_brain_mcp_entry(root)
    if not primary.ok:
        return CheckResult(
            "Dual memory server",
            False,
            primary.message,
            primary.detail,
        )

    settings_paths = [
        root / ".claude" / "settings.json",
        root / ".claude" / "settings.local.json",
        Path.home() / ".claude" / "settings.json",
    ]
    for cfg in settings_paths:
        if not cfg.exists():
            continue
        try:
            data = json.loads(cfg.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        servers = data.get("mcpServers", {})
        if not isinstance(servers, dict):
            continue
        found = sorted(k for k in servers if k in _BRAIN_MCP_SERVER_NAMES)
        if found:
            return CheckResult(
                "Dual memory server",
                False,
                f"Direct tapps-brain server in {cfg.name}: {', '.join(found)}",
                "Remove the entry — memory goes through tapps-mcp BrainBridge "
                f"(see {_ADR_0001_REF}).",
            )

    return CheckResult(
        "Dual memory server",
        True,
        "No direct tapps-brain MCP server detected",
    )


def _build_combined_install_hint(missing_tools: list[str]) -> str:
    """Build a combined ``uv tool install --with`` command for all missing tools.

    Tries to read ``uv-receipt.toml`` to determine the original install source
    so the suggestion is accurate for editable/local installs.
    """
    import shutil

    source = "tapps-mcp"

    # Try to find the original install source from uv-receipt.toml
    tapps_bin = shutil.which("tapps-mcp")
    if tapps_bin:
        receipt = Path(tapps_bin).resolve().parent.parent / "uv-receipt.toml"
        if receipt.exists():
            try:
                content = receipt.read_text()
                for line in content.splitlines():
                    if "editable" in line.lower() or "path" in line.lower():
                        # Extract the path value
                        if "=" in line:
                            val = line.split("=", 1)[1].strip().strip("'\"")
                            if val and Path(val).exists():
                                source = f"--editable {val}"
                                break
            except Exception:
                pass

    with_flags = " ".join(f"--with {t}" for t in missing_tools)
    return f"uv tool install {source} {with_flags} --force"


def check_quality_tools() -> list[CheckResult]:
    """Check for installed quality tools (ruff, mypy, bandit, radon)."""
    from tapps_mcp.tools.tool_detection import detect_installed_tools

    results: list[CheckResult] = []
    missing_names: list[str] = []
    tools = detect_installed_tools(force_refresh=True)
    for tool in tools:
        if tool.available:
            results.append(
                CheckResult(
                    f"Tool: {tool.name}",
                    True,
                    f"{tool.name} {tool.version or '(version unknown)'}",
                )
            )
        else:
            missing_names.append(tool.name)
            results.append(
                CheckResult(
                    f"Tool: {tool.name}",
                    False,
                    f"{tool.name} not found",
                    tool.install_hint or "",
                )
            )

    # Add a combined install hint when multiple tools are missing
    if len(missing_names) >= 2:
        combined = _build_combined_install_hint(missing_names)
        results.append(
            CheckResult(
                "Quality tools",
                False,
                f"{len(missing_names)} checker tools missing",
                f"Install all at once: {combined}",
            )
        )

    return results


# ---------------------------------------------------------------------------
# Consumer requirements mapping (Epic 50)
# ---------------------------------------------------------------------------

_NUM_REQUIREMENTS = 7

# Check name -> requirement number mapping
_REQ_CHECK_MAP: dict[int, list[str]] = {
    2: [
        "Claude Code (project) config",
        "Claude Code (user) config",
        "Cursor config",
        "VS Code config",
        "MCP client config",
    ],
    3: [".claude/settings.json"],
    4: ["AGENTS.md", "Hooks", "Claude hook scripts", "CLAUDE.md rules", "Cursor rules"],
    5: [
        "Tool: ruff",
        "Tool: mypy",
        "Tool: bandit",
        "Tool: radon",
        "Quality tools",
    ],
    6: ["tapps-mcp binary"],
}

_REQ_NAMES: dict[int, str] = {
    1: "Server available",
    2: "MCP config",
    3: "Tool permissions",
    4: "Bootstrap (init)",
    5: "Python scoring tools",
    6: "CLI fallback",
    7: "Verification table",
}


def _build_requirements_summary(
    checks: list[CheckResult],
) -> list[dict[str, Any]]:
    """Map doctor check results to the 7 consumer requirements.

    Returns a list of dicts with keys: requirement, name, status, checks.
    """
    check_by_name: dict[str, bool] = {c.name: c.ok for c in checks}

    summary: list[dict[str, Any]] = []

    for req_num in range(1, _NUM_REQUIREMENTS + 1):
        name = _REQ_NAMES[req_num]

        if req_num == 1:
            summary.append(
                {
                    "requirement": req_num,
                    "name": name,
                    "status": "verify_in_session",
                    "checks": [],
                }
            )
            continue

        if req_num == _NUM_REQUIREMENTS:
            summary.append(
                {
                    "requirement": req_num,
                    "name": name,
                    "status": "see_docs",
                    "checks": [],
                }
            )
            continue

        mapped_checks = _REQ_CHECK_MAP.get(req_num, [])
        found_any = False
        any_pass = False
        for cname in mapped_checks:
            if cname in check_by_name:
                found_any = True
                if check_by_name[cname]:
                    any_pass = True

        if not found_any:
            status = "n/a"
        elif any_pass:
            status = "pass"
        else:
            status = "fail"

        summary.append(
            {
                "requirement": req_num,
                "name": name,
                "status": status,
                "checks": [c for c in mapped_checks if c in check_by_name],
            }
        )

    return summary


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def check_uv_path_mismatch(project_root: Path) -> CheckResult:
    """Warn when MCP config uses bare ``tapps-mcp`` but project is uv-managed (Issue #77).

    If the project has ``uv.lock`` or a pyproject.toml extra that references
    ``tapps-mcp``, the MCP config should use ``uv run`` to ensure the server
    can start without ``tapps-mcp`` on global PATH.
    """
    from tapps_mcp.distribution.setup_generator import _detect_uv_context

    ctx = _detect_uv_context(project_root)
    if ctx is None or not ctx.get("tapps_mcp_extra"):
        return CheckResult(
            "uv PATH check",
            True,
            "Not a uv consumer project (check skipped)",
        )

    # Scan MCP configs for bare tapps-mcp command.
    candidates: list[tuple[Path, str]] = [
        (project_root / ".mcp.json", "mcpServers"),
        (project_root / ".cursor" / "mcp.json", "mcpServers"),
        (project_root / ".vscode" / "mcp.json", "servers"),
    ]
    warnings: list[str] = []
    for path, servers_key in candidates:
        if not path.exists():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else {}
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        servers = data.get(servers_key) or {}
        if not isinstance(servers, dict):
            continue
        entry = servers.get("tapps-mcp")
        if isinstance(entry, dict) and entry.get("command") == "tapps-mcp":
            warnings.append(path.name)

    if not warnings:
        return CheckResult(
            "uv PATH check",
            True,
            "MCP configs use uv-compatible launch (or no tapps-mcp entry found)",
        )
    extra = ctx["tapps_mcp_extra"]
    return CheckResult(
        "uv PATH check",
        False,
        f"MCP config(s) use bare 'tapps-mcp' command but project has "
        f"tapps-mcp in uv extra '{extra}': {', '.join(warnings)}",
        f"Re-run: tapps-mcp init --force (auto-detects uv) or use --uv --uv-extra {extra}",
    )


def check_plaintext_secrets(project_root: Path) -> CheckResult:
    """Warn when ``.mcp.json`` stores secrets (API keys/tokens) in plaintext (Issue #80.3)."""
    from tapps_mcp.distribution.setup_generator import _collect_plaintext_secrets

    candidates: list[Path] = [
        project_root / ".mcp.json",
        project_root / ".cursor" / "mcp.json",
        project_root / ".vscode" / "mcp.json",
    ]
    findings: list[str] = []
    for path in candidates:
        if not path.exists():
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else {}
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        for servers_key in ("mcpServers", "servers"):
            servers = data.get(servers_key) or {}
            if not isinstance(servers, dict):
                continue
            for server_name, entry in servers.items():
                if isinstance(entry, dict):
                    secrets = _collect_plaintext_secrets(entry)
                    if secrets:
                        findings.append(f"{path.name} ({server_name}): {', '.join(secrets)}")
    if not findings:
        return CheckResult(
            "MCP secrets",
            True,
            "No plaintext secrets detected in MCP configs",
        )
    return CheckResult(
        "MCP secrets",
        False,
        "Plaintext secret(s) detected in MCP config: " + "; ".join(findings),
        "Use ${VAR} env-var interpolation (Claude Code/Cursor support it) "
        "and add the config file to .gitignore.",
    )


def check_report_studio(project_root: Path) -> CheckResult:
    """Report whether nlt-report-studio is pinned in pyproject.toml."""
    try:
        from tapps_mcp.pipeline.report_studio.installer import check_report_studio

        probe = check_report_studio(project_root)
        if not probe.get("installed"):
            return CheckResult(
                "report_studio",
                True,
                "Not installed (run tapps_init with with_report_studio=True)",
            )
        count = probe.get("report_count", 0)
        from tapps_core.config.settings import load_settings
        from tapps_mcp.pipeline.document_judges import summarise_configured_judges

        settings = load_settings(project_root=project_root)
        judge_summary = summarise_configured_judges(settings.validate_changed.judges)
        if judge_summary["configured"]:
            detail = (
                f"Pinned in pyproject.toml ({count} report(s)); "
                f"judges configured ({judge_summary['blocking']} blocking, "
                f"{judge_summary['advisory']} advisory)"
            )
        else:
            detail = (
                f"Pinned in pyproject.toml ({count} report(s)); "
                "judges missing — run tapps_init/tapps_upgrade or add validate_changed.judges"
            )
        return CheckResult("report_studio", True, detail)
    except Exception as exc:
        return CheckResult("report_studio", False, f"Check failed: {exc}")


def check_linear_sdlc(project_root: Path) -> CheckResult:
    """Report whether Linear SDLC templates are absent, current, or stale."""
    from tapps_mcp.pipeline.linear_sdlc.renderer import TEMPLATE_PATHS

    primary = project_root / TEMPLATE_PATHS[0]
    if not primary.exists():
        return CheckResult(
            "linear_sdlc",
            True,
            "Not installed (run tapps_init with linear_sdlc=True to enable)",
        )
    try:
        from tapps_mcp.pipeline.linear_sdlc.installer import refresh_linear_sdlc

        probe = refresh_linear_sdlc(project_root, dry_run=True)
        if probe.get("errors"):
            return CheckResult(
                "linear_sdlc",
                False,
                f"Check error: {probe['errors'][0]}",
            )
        stale = probe.get("refreshed", [])
        if stale:
            preview = ", ".join(stale[:3])
            return CheckResult(
                "linear_sdlc",
                False,
                f"Stale ({len(stale)} file(s)): {preview}",
                "Run tapps_upgrade to refresh to the latest templates.",
            )
        return CheckResult(
            "linear_sdlc",
            True,
            "All Linear SDLC templates are current",
        )
    except Exception as exc:
        return CheckResult(
            "linear_sdlc",
            False,
            f"Check failed: {exc}",
        )


def check_legacy_doc_cache(root: Path) -> CheckResult:
    """ADR-0014: fail when per-repo doc cache subtrees remain after brain cutover."""
    from tapps_core.config.settings import load_settings
    from tapps_core.knowledge.brain_docs import docs_via_brain_enabled
    from tapps_core.knowledge.cache import KBCache

    try:
        settings = load_settings(project_root=root)
    except Exception:
        return CheckResult(
            "legacy_doc_cache",
            True,
            "Skipped (could not load settings)",
        )

    if not docs_via_brain_enabled(settings):
        return CheckResult(
            "legacy_doc_cache",
            True,
            "Skipped (docs_via_brain disabled)",
        )

    cache_dir = root / ".tapps-mcp-cache"
    count = KBCache(cache_dir).doc_library_dir_count()
    if count == 0:
        return CheckResult(
            "legacy_doc_cache",
            True,
            "No legacy doc library subtrees under .tapps-mcp-cache/",
        )
    return CheckResult(
        "legacy_doc_cache",
        False,
        f"{count} legacy doc library dir(s) under .tapps-mcp-cache/",
        "Run tapps-brain docs import-dir .tapps-mcp-cache then remove doc subtrees.",
    )


def _mcp_configs_set_context7(root: Path) -> list[str]:
    """Return MCP config paths that still set TAPPS_MCP_CONTEXT7_API_KEY."""
    hits: list[str] = []
    candidates = (
        root / ".mcp.json",
        root / ".cursor" / "mcp.json",
        root / ".vscode" / "mcp.json",
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        servers = data.get("mcpServers") or data.get("servers") or {}
        if not isinstance(servers, dict):
            continue
        for spec in servers.values():
            if not isinstance(spec, dict):
                continue
            env = spec.get("env") or {}
            if isinstance(env, dict) and env.get("TAPPS_MCP_CONTEXT7_API_KEY"):
                hits.append(str(path.relative_to(root)))
                break
    return hits


def _env_file_sets_key(path: Path, key: str) -> bool:
    """Return True when *path* defines *key* with a non-empty, non-placeholder value."""
    if not path.is_file():
        return False
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() != key:
                continue
            val = value.strip().strip("'\"")
            if val and not _is_unsubstituted_placeholder(val):
                return True
    except OSError:
        return False
    return False


def _operator_secret_available(key: str, *, project_root: Path) -> bool:
    """True when *key* is set in the current process or operator/project env files."""
    import os

    raw = os.environ.get(key, "").strip()
    if raw and not _is_unsubstituted_placeholder(raw):
        return True
    operator_env = Path.home() / ".tapps-operator.env"
    if _env_file_sets_key(operator_env, key):
        return True
    return _env_file_sets_key(project_root / ".env", key)


def _mcp_configs_reference_brain_auth(root: Path) -> bool:
    """Return True when any MCP config env block references brain bearer tokens."""
    candidates = (
        root / ".mcp.json",
        root / ".cursor" / "mcp.json",
        root / ".vscode" / "mcp.json",
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        servers = data.get("mcpServers") or data.get("servers") or {}
        if not isinstance(servers, dict):
            continue
        for spec in servers.values():
            if not isinstance(spec, dict):
                continue
            env = spec.get("env") or {}
            if isinstance(env, dict) and (
                env.get("TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN")
                or env.get("TAPPS_BRAIN_AUTH_TOKEN")
            ):
                return True
    return False


def check_mcp_operator_secrets(root: Path) -> CheckResult:
    """Warn when MCP configs reference operator secrets that GUI subprocesses cannot resolve.

    Cursor GUI launches often do not expand ``${VAR}`` in ``mcp.json``. Serve wrappers
    source ``~/.tapps-operator.env`` then project ``.env`` (TAP-3255). This check fails
    when configs still reference Context7 or brain auth but none of process env, operator
    env, or project ``.env`` provides the value.
    """
    from tapps_core.config.settings import load_settings
    from tapps_core.knowledge.brain_docs import docs_via_brain_enabled

    try:
        settings = load_settings(project_root=root)
    except Exception:
        return CheckResult(
            "mcp_operator_secrets",
            True,
            "Skipped (could not load settings)",
        )

    missing: list[str] = []
    if _mcp_configs_set_context7(root) and not docs_via_brain_enabled(settings):
        if not _operator_secret_available("TAPPS_MCP_CONTEXT7_API_KEY", project_root=root):
            if not _operator_secret_available("CONTEXT7_API_KEY", project_root=root):
                missing.append("TAPPS_MCP_CONTEXT7_API_KEY")

    brain_configured = bool(_brain_http_url_for_checks(root)) or _mcp_configs_reference_brain_auth(
        root
    )
    if brain_configured:
        if not _operator_secret_available("TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN", project_root=root):
            if not _operator_secret_available("TAPPS_BRAIN_AUTH_TOKEN", project_root=root):
                missing.append("TAPPS_BRAIN_AUTH_TOKEN")

    if not missing:
        operator_env = Path.home() / ".tapps-operator.env"
        if operator_env.is_file():
            msg = "Operator secrets available (~/.tapps-operator.env or project .env)"
        else:
            msg = "Operator secrets available (shell env or project .env)"
        return CheckResult("mcp_operator_secrets", True, msg)

    keys = ", ".join(missing)
    return CheckResult(
        "mcp_operator_secrets",
        False,
        f"MCP configs reference {keys} but GUI subprocess cannot resolve them",
        "Create ~/.tapps-operator.env (see docs/operations/OPERATOR-SECRETS.md), "
        "re-run tapps-mcp upgrade --host cursor --force, reload MCP.",
    )


def _run_docs_tools_probe(http_url: str, settings: Any) -> dict[str, Any] | None:
    """Run a synchronous ``docs_lookup`` probe for ADR-0014 doctor checks."""
    try:
        from tapps_core.brain_bridge import BRAIN_PROFILE_SERVER, HttpBrainBridge
    except Exception:
        return None
    try:
        headers = _doctor_brain_headers(settings)
        headers.setdefault("X-Brain-Profile", BRAIN_PROFILE_SERVER)
        bridge = HttpBrainBridge(http_url, headers)
        result = bridge.docs_tools_probe()
    except Exception:
        return None
    return result if isinstance(result, dict) else None


def check_brain_docs_tools(root: Path) -> CheckResult:
    """ADR-0014: verify brain exposes ``docs_lookup`` when ``docs_via_brain`` is on."""
    from tapps_core.config.settings import load_settings
    from tapps_core.knowledge.brain_docs import docs_via_brain_enabled

    try:
        settings = load_settings(project_root=root)
    except Exception:
        return CheckResult(
            "brain_docs_tools",
            True,
            "Skipped (could not load settings)",
        )

    if not docs_via_brain_enabled(settings):
        return CheckResult(
            "brain_docs_tools",
            True,
            "Skipped (docs_via_brain disabled)",
        )

    http_url = _brain_http_url_for_checks(root)
    if not http_url:
        return CheckResult(
            "brain_docs_tools",
            False,
            "docs_via_brain requires HTTP brain (memory.brain_http_url unset)",
            "Set memory.brain_http_url in .tapps-mcp.yaml and deploy brain 3.24.0+ "
            "with docs_lookup (ADR-0015).",
        )

    probe = _run_docs_tools_probe(http_url, settings)
    if probe is None:
        return CheckResult(
            "brain_docs_tools",
            False,
            "Could not probe brain docs_lookup",
            "Check brain reachability and TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN.",
        )

    if probe.get("ok"):
        return CheckResult(
            "brain_docs_tools",
            True,
            f"brain docs_lookup probe ok ({http_url})",
        )

    if probe.get("gated"):
        tool = probe.get("tool") or "docs_lookup"
        profile = probe.get("profile") or "<unset>"
        suggested = probe.get("suggested_profile")
        hint = (
            f"Set memory.brain_profile to {suggested!r} (or TAPPS_BRAIN_PROFILE)."
            if suggested
            else "Use brain profile ``full`` so docs_lookup is exposed."
        )
        return CheckResult(
            "brain_docs_tools",
            False,
            f"Profile {profile!r} hides {tool!r}",
            hint,
        )

    detail = probe.get("detail") or probe.get("error") or "probe failed"
    return CheckResult(
        "brain_docs_tools",
        False,
        f"brain docs_lookup unavailable: {detail}",
        "Upgrade tapps-brain to 3.24.0+ with docs_lookup (ADR-0015); see "
        "docs/operations/brain-doc-rag-cutover-runbook.md.",
    )


def check_consumer_context7_env(root: Path) -> CheckResult:
    """ADR-0014: warn when consumer MCP configs still carry Context7 after cutover."""
    from tapps_core.config.settings import load_settings
    from tapps_core.knowledge.brain_docs import docs_via_brain_enabled

    try:
        settings = load_settings(project_root=root)
    except Exception:
        return CheckResult(
            "consumer_context7_env",
            True,
            "Skipped (could not load settings)",
        )

    if not docs_via_brain_enabled(settings):
        return CheckResult(
            "consumer_context7_env",
            True,
            "Skipped (docs_via_brain disabled)",
        )

    hits = _mcp_configs_set_context7(root)
    if not hits:
        return CheckResult(
            "consumer_context7_env",
            True,
            "No consumer TAPPS_MCP_CONTEXT7_API_KEY in MCP configs",
        )
    preview = ", ".join(hits[:3])
    return CheckResult(
        "consumer_context7_env",
        True,
        f"Context7 still in MCP env ({preview}) — remove after brain cutover",
        "Re-run tapps-mcp init --force or upgrade-fleet --strip-context7-env.",
    )


def _collect_checks(root: Path, *, quick: bool = False) -> list[CheckResult]:
    """Collect all diagnostic checks for the given project root.

    Args:
        root: Project root directory.
        quick: When True, skip quality tool version checks for faster results.
    """
    checks: list[CheckResult] = []
    checks.append(check_binary_on_path())
    checks.append(check_binary_version_mismatch())
    checks.append(check_docsmcp_binary_version_mismatch())
    checks.append(check_blue_green_deploy())
    checks.append(check_global_local_install())
    checks.append(check_claude_code_user(project_root=root))
    checks.append(check_claude_code_project(root))
    checks.append(check_cursor_config(root))
    checks.append(check_vscode_config(root))
    checks.append(check_mcp_client_config(root))
    checks.append(check_mcp_tool_budget(root))
    checks.append(check_call_graph_tools_profile(root))
    checks.append(check_call_graph_index_cache(root, quick=quick))
    checks.append(check_nlt_partial_enablement(root))
    checks.append(check_mcp_config_unresolved_project_root(root))
    checks.append(check_brain_mcp_entry(root))
    checks.append(check_scope_recommendation(root))
    checks.append(check_claude_md(root))
    checks.append(check_claude_md_stamp(root))
    checks.append(check_cursor_rules(root))
    checks.append(check_linear_standards_rule(root))
    checks.append(check_autonomy_rule(root))
    # TAP-978: scoped quality rules — report presence + gate status.
    checks.append(check_security_rule(root))
    checks.append(check_test_quality_rule(root))
    checks.append(check_config_files_rule(root))
    checks.append(check_linear_issue_skill_current(root))
    checks.append(check_finish_task_skill(root))
    checks.append(check_deprecated_wrapper_skills(root))
    checks.append(check_tapps_memory_skill(root))
    checks.append(check_session_handoff_skills(root))
    checks.append(check_session_handoff_schema(root))
    checks.append(check_cache_gate_block_hint(root))
    checks.append(check_install_git_hooks_hint(root))
    checks.append(check_pipeline_enforce_recommendations(root))
    checks.append(check_cursor_loop_metrics_telemetry(root))
    checks.append(check_cursor_stop_completion_gate(root))
    checks.append(check_continuous_learning_v2_skill(root))
    checks.append(check_pretooluse_matchers(root))
    checks.append(check_agents_md(root))
    checks.append(check_karpathy_guidelines(root))
    checks.append(check_tapps_mcp_yaml(root))
    checks.append(check_claude_settings(root))
    checks.append(check_claude_hook_scripts(root))
    checks.append(check_hooks(root))
    checks.append(check_cursor_mcp_zombie_cleanup(root))
    checks.append(check_stale_exe_backups())
    checks.append(check_tapps_brain())
    checks.append(check_brain_http_auth(root))
    checks.append(check_brain_profile(root))
    checks.append(check_brain_probe_latency(root))
    checks.append(check_brain_health(root))
    checks.append(check_brain_version_floor(root))
    checks.append(check_brain_version_delta(root))
    checks.append(check_session_sentinel(root))
    checks.append(check_memory_pipeline_config(root))
    checks.append(check_memory_cli_http_mode(root))
    checks.append(check_dual_memory_server(root))
    checks.append(check_plaintext_secrets(root))
    checks.append(check_uv_path_mismatch(root))
    checks.append(check_linear_sdlc(root))
    checks.append(check_report_studio(root))
    checks.append(check_legacy_doc_cache(root))
    checks.append(check_brain_docs_tools(root))
    checks.append(check_mcp_operator_secrets(root))
    checks.append(check_consumer_context7_env(root))
    if quick:
        checks.append(
            CheckResult(
                "Quality tools",
                True,
                "Skipped (quick mode)",
                "Run without --quick for full tool version checks",
            )
        )
    else:
        checks.extend(check_quality_tools())
    return checks


def _read_engagement_level(project_root: Path) -> str | None:
    """Read llm_engagement_level from project_root/.tapps-mcp.yaml if present."""
    config_path = project_root / ".tapps-mcp.yaml"
    if not config_path.exists():
        return None
    try:
        import yaml

        raw = config_path.read_text(encoding="utf-8-sig")
        data = yaml.safe_load(raw) if raw.strip() else {}
        level = (data or {}).get("llm_engagement_level")
        if level in ("high", "medium", "low"):
            return str(level)
    except Exception:
        return None
    return None


def run_doctor_structured(*, project_root: str = ".", quick: bool = False) -> dict[str, Any]:
    """Run all diagnostic checks and return structured results.

    Returns a dict with ``checks``, ``pass_count``, ``fail_count``,
    ``all_passed``, and ``quick_mode`` for programmatic consumption (MCP tool).

    Args:
        project_root: Project root path.
        quick: When True, skip quality tool version checks.
    """
    root = Path(project_root).resolve()
    log.info("doctor_structured", project_root=str(root))

    checks = _collect_checks(root, quick=quick)

    results: list[dict[str, str | bool]] = []
    pass_count = 0
    fail_count = 0
    for check in checks:
        entry: dict[str, str | bool] = {
            "name": check.name,
            "ok": check.ok,
            "message": check.message,
        }
        if check.detail:
            entry["detail"] = check.detail
        results.append(entry)
        if check.ok:
            pass_count += 1
        else:
            fail_count += 1

    out: dict[str, Any] = {
        "checks": results,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "all_passed": fail_count == 0,
        "quick_mode": quick,
    }

    # Consumer requirements summary (Epic 50)
    out["requirements_summary"] = _build_requirements_summary(checks)

    # Report engagement level when configured (Epic 18.8)
    engagement = _read_engagement_level(root)
    if engagement is not None:
        out["llm_engagement_level"] = engagement
    return out


def run_doctor(*, project_root: str = ".", quick: bool = False) -> bool:
    """Run all diagnostic checks and print a summary.

    Returns ``True`` if all checks pass, ``False`` otherwise.

    Args:
        project_root: Project root path.
        quick: When True, skip quality tool version checks.
    """
    root = Path(project_root).resolve()
    log.info("doctor_command", project_root=str(root))

    checks = _collect_checks(root, quick=quick)

    # Print report
    click.echo("")
    click.echo(click.style("=== TappsMCP Doctor Report ===", bold=True))
    if quick:
        click.echo(click.style("  (Quick mode — tool version checks skipped)", fg="cyan"))
    click.echo("")

    pass_count = 0
    fail_count = 0
    for check in checks:
        if check.ok:
            click.echo(click.style(f"  PASS  {check.name}: {check.message}", fg="green"))
            pass_count += 1
        else:
            click.echo(click.style(f"  FAIL  {check.name}: {check.message}", fg="red"))
            if check.detail:
                click.echo(f"        {check.detail}")
            fail_count += 1

    engagement = _read_engagement_level(root)
    if engagement is not None:
        click.echo(click.style(f"  Config  llm_engagement_level: {engagement}", fg="cyan"))

    click.echo("")
    click.echo(f"Results: {pass_count} passed, {fail_count} failed")

    if fail_count == 0:
        click.echo(click.style("All checks passed!", fg="green"))
    else:
        click.echo(
            click.style(
                f"{fail_count} issue(s) found. Run the suggested commands to fix.",
                fg="yellow",
            )
        )

    # Consumer requirements summary (Epic 50)
    click.echo("")
    click.echo(click.style("=== Consumer Requirements Summary ===", bold=True))
    req_summary = _build_requirements_summary(checks)
    for req in req_summary:
        status = req["status"]
        if status == "pass":
            styled = click.style("PASS", fg="green")
        elif status == "fail":
            styled = click.style("FAIL", fg="red")
        elif status == "n/a":
            styled = click.style("N/A", fg="cyan")
        else:
            styled = click.style("INFO", fg="cyan")
        click.echo(f"  {req['requirement']}. {req['name']:24s} {styled}")
    click.echo("")
    click.echo("For the full consumer requirements checklist, see docs/TAPPS_MCP_REQUIREMENTS.md")

    return fail_count == 0
