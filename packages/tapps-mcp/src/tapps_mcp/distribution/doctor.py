"""TappsMCP doctor: diagnose configuration, rules, and connectivity."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import click

from tapps_core.common.logging import get_logger
from tapps_mcp.pipeline.platform_hook_templates import (
    SUPPORTED_CLAUDE_HOOK_KEYS,
    SUPPORTED_CURSOR_HOOK_KEYS,
)

log = get_logger(__name__)


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
    from tapps_mcp.distribution.setup_generator import _is_valid_tapps_command

    if not config_path.exists():
        return f"Not found: {config_path}"

    try:
        raw = config_path.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return f"Invalid JSON: {config_path}"

    if not isinstance(data, dict):
        return f"Invalid structure: {config_path}"

    servers = data.get(servers_key, {})
    entry = servers.get("tapps-mcp") if isinstance(servers, dict) else None
    if not isinstance(entry, dict):
        return f"tapps-mcp not in {config_path}"

    command = entry.get("command", "")
    return (
        f"Unexpected command: '{command}' (expected 'tapps-mcp' or path to tapps-mcp.exe)"
        if not _is_valid_tapps_command(command)
        else None
    )


def check_claude_code_user(home: Path | None = None) -> CheckResult:
    """Check ``~/.claude.json`` for tapps-mcp entry."""
    base = home or Path.home()
    return check_json_config(base / ".claude.json", "mcpServers", "Claude Code (user)")


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
        (base / ".claude.json", "mcpServers", "Claude Code (user)"),
        (base / ".claude" / "settings.json", "mcpServers", "Claude Code (settings)"),
    ]

    found_in: list[str] = []
    for path, servers_key, label in candidates:
        result = check_json_config(path, servers_key, label)
        if result.ok:
            found_in.append(label)

    if found_in:
        return CheckResult(
            "MCP client config",
            True,
            f"tapps-mcp registered in: {', '.join(found_in)}",
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


def check_claude_md(project_root: Path) -> CheckResult:
    """Check if CLAUDE.md exists and contains TAPPS reference.

    When Cursor rules are present (``.cursor/rules/tapps-pipeline.md``),
    a missing CLAUDE.md reference is reported as a soft pass rather than a
    failure, since the project may target Cursor rather than Claude Code.
    """
    cursor_rules_present = (
        project_root / ".cursor" / "rules" / "tapps-pipeline.md"
    ).exists()
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


def check_hooks(project_root: Path) -> CheckResult:
    """Check TappsMCP hooks: directory, session-start script, and config validity.

    For Claude Code, hook keys are validated in check_claude_settings.
    For Cursor, requires .cursor/hooks.json when scripts exist and validates
    that only supported hook event keys are present (unsupported keys can
    cause the file to be ignored).
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

    # When Cursor hook scripts exist, .cursor/hooks.json must exist (parity with Claude settings)
    cursor_hooks_json = project_root / ".cursor" / "hooks.json"
    if "Cursor" in found and not cursor_hooks_json.exists():
        return CheckResult(
            "Hooks",
            False,
            f"TappsMCP hooks found for: {', '.join(found)}, but .cursor/hooks.json missing",
            "Run: tapps-mcp upgrade --host cursor or upgrade --force",
        )

    # Validate .cursor/hooks.json format (Cursor requires version + object hooks)
    if cursor_hooks_json.exists():
        format_errors: list[str] = []
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
                invalid = [k for k in hooks_obj if k not in SUPPORTED_CURSOR_HOOK_KEYS]
                if invalid:
                    format_errors.append(
                        f"unsupported hook keys (Cursor may ignore file): {', '.join(sorted(invalid))}"
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

    return CheckResult(
        "Hooks",
        True,
        f"TappsMCP hooks found for: {', '.join(found)} (including session-start)",
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


def check_quality_tools() -> list[CheckResult]:
    """Check for installed quality tools (ruff, mypy, bandit, radon)."""
    from tapps_mcp.tools.tool_detection import detect_installed_tools

    results: list[CheckResult] = []
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
            results.append(
                CheckResult(
                    f"Tool: {tool.name}",
                    False,
                    f"{tool.name} not found",
                    tool.install_hint or "",
                )
            )
    return results


# ---------------------------------------------------------------------------
# Docker health checks (Epic 46.7)
# ---------------------------------------------------------------------------


async def _run_docker_command(*args: str) -> tuple[int, str, str]:
    """Run a Docker CLI command and return (returncode, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=15)
        return (
            proc.returncode or 0,
            stdout_bytes.decode("utf-8", errors="replace").strip(),
            stderr_bytes.decode("utf-8", errors="replace").strip(),
        )
    except FileNotFoundError:
        return (1, "", "docker not found on PATH")
    except asyncio.TimeoutError:
        return (1, "", "docker command timed out")
    except OSError as exc:
        return (1, "", str(exc))


async def check_docker_daemon() -> CheckResult:
    """Verify Docker daemon is running and accessible."""
    rc, stdout, stderr = await _run_docker_command("info", "--format", "{{.ServerVersion}}")
    if rc == 0 and stdout:
        return CheckResult(
            "Docker daemon",
            True,
            f"Docker daemon running (server {stdout})",
        )
    detail = stderr or "Docker daemon not reachable"
    return CheckResult(
        "Docker daemon",
        False,
        "Docker daemon not running or not installed",
        detail,
    )


async def check_docker_mcp_toolkit() -> CheckResult:
    """Verify Docker MCP Toolkit plugin is installed."""
    rc, stdout, stderr = await _run_docker_command("mcp", "version")
    if rc == 0 and stdout:
        return CheckResult(
            "Docker MCP Toolkit",
            True,
            f"Docker MCP Toolkit installed ({stdout.splitlines()[0]})",
        )
    return CheckResult(
        "Docker MCP Toolkit",
        False,
        "Docker MCP Toolkit not installed",
        "Install: https://github.com/docker/mcp-toolkit",
    )


async def check_docker_images(image: str, docs_image: str) -> CheckResult:
    """Verify tapps-mcp and docs-mcp images exist locally."""
    missing: list[str] = []
    for img in (image, docs_image):
        rc, _stdout, _stderr = await _run_docker_command("image", "inspect", img)
        if rc != 0:
            missing.append(img)

    if not missing:
        return CheckResult(
            "Docker images",
            True,
            f"Images present: {image}, {docs_image}",
        )
    suggestions = ", ".join(f"docker pull {m}" for m in missing)
    return CheckResult(
        "Docker images",
        False,
        f"Missing image(s): {', '.join(missing)}",
        f"Pull with: {suggestions}",
    )


async def check_docker_companions(companions: list[str]) -> CheckResult:
    """Verify recommended companion MCP servers are available as images."""
    if not companions:
        return CheckResult(
            "Docker companions",
            True,
            "No companion servers configured",
        )
    missing: list[str] = []
    found: list[str] = []
    for name in companions:
        rc, _stdout, _stderr = await _run_docker_command("image", "inspect", name)
        if rc == 0:
            found.append(name)
        else:
            missing.append(name)

    if not missing:
        return CheckResult(
            "Docker companions",
            True,
            f"All companion images present: {', '.join(found)}",
        )
    return CheckResult(
        "Docker companions",
        False,
        f"Missing companion image(s): {', '.join(missing)}",
        f"Pull with: {', '.join(f'docker pull {m}' for m in missing)}",
    )


def check_docker_mcp_config(project_root: Path, profile: str) -> CheckResult:
    """Verify MCP client config references Docker gateway when docker is enabled."""
    candidates = [
        project_root / ".mcp.json",
        project_root / ".claude.json",
    ]
    for config_path in candidates:
        if not config_path.exists():
            continue
        try:
            raw = config_path.read_text(encoding="utf-8")
            data: dict[str, Any] = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, OSError):
            continue

        servers = data.get("mcpServers", {})
        entry = servers.get("tapps-mcp") if isinstance(servers, dict) else None
        if not isinstance(entry, dict):
            continue

        command = entry.get("command", "")
        if command == "docker":
            args = entry.get("args", [])
            args_str = " ".join(str(a) for a in args) if isinstance(args, list) else ""
            if profile in args_str:
                return CheckResult(
                    "Docker MCP config",
                    True,
                    f"Config in {config_path.name} uses Docker with profile '{profile}'",
                )
            return CheckResult(
                "Docker MCP config",
                False,
                f"Config in {config_path.name} uses Docker but profile '{profile}' not found in args",
                f"Expected args to reference profile '{profile}'",
            )

    return CheckResult(
        "Docker MCP config",
        False,
        "No MCP config references Docker transport for tapps-mcp",
        "Update .mcp.json to use command: 'docker' with MCP Toolkit args",
    )


async def _collect_docker_checks(
    project_root: Path,
    image: str,
    docs_image: str,
    companions: list[str],
    profile: str,
) -> list[CheckResult]:
    """Collect all Docker-related diagnostic checks."""
    results: list[CheckResult] = []

    daemon_result = await check_docker_daemon()
    results.append(daemon_result)

    if not daemon_result.ok:
        # Skip remaining checks if daemon is not available
        return results

    toolkit_result = await check_docker_mcp_toolkit()
    results.append(toolkit_result)

    images_result = await check_docker_images(image, docs_image)
    results.append(images_result)

    companions_result = await check_docker_companions(companions)
    results.append(companions_result)

    config_result = check_docker_mcp_config(project_root, profile)
    results.append(config_result)

    return results


def _is_docker_available() -> bool:
    """Return True if Docker CLI is on PATH."""
    return shutil.which("docker") is not None


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
    4: ["AGENTS.md", "Hooks", "CLAUDE.md rules", "Cursor rules"],
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
            summary.append({
                "requirement": req_num,
                "name": name,
                "status": "verify_in_session",
                "checks": [],
            })
            continue

        if req_num == _NUM_REQUIREMENTS:
            summary.append({
                "requirement": req_num,
                "name": name,
                "status": "see_docs",
                "checks": [],
            })
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

        summary.append({
            "requirement": req_num,
            "name": name,
            "status": status,
            "checks": [c for c in mapped_checks if c in check_by_name],
        })

    return summary


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _collect_checks(root: Path, *, quick: bool = False) -> list[CheckResult]:
    """Collect all diagnostic checks for the given project root.

    Args:
        root: Project root directory.
        quick: When True, skip quality tool version checks for faster results.
    """
    checks: list[CheckResult] = []
    checks.append(check_binary_on_path())
    checks.append(check_claude_code_user())
    checks.append(check_claude_code_project(root))
    checks.append(check_cursor_config(root))
    checks.append(check_vscode_config(root))
    checks.append(check_mcp_client_config(root))
    checks.append(check_scope_recommendation(root))
    checks.append(check_claude_md(root))
    checks.append(check_cursor_rules(root))
    checks.append(check_agents_md(root))
    checks.append(check_claude_settings(root))
    checks.append(check_hooks(root))
    checks.append(check_stale_exe_backups())
    if quick:
        checks.append(CheckResult(
            "Quality tools",
            True,
            "Skipped (quick mode)",
            "Run without --quick for full tool version checks",
        ))
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
            return level
    except Exception:
        return None
    return None


def _collect_docker_checks_sync(root: Path) -> list[CheckResult]:
    """Collect Docker checks, running async checks in a new event loop if needed."""
    from tapps_core.config.settings import load_settings

    settings = load_settings()
    docker_enabled = settings.docker.enabled
    docker_on_path = _is_docker_available()

    if not docker_enabled and not docker_on_path:
        return []

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in an async context -- cannot use asyncio.run().
        # Return a placeholder; callers in async context should use
        # _collect_docker_checks directly.
        return []

    return asyncio.run(
        _collect_docker_checks(
            project_root=root,
            image=settings.docker.image,
            docs_image=settings.docker.docs_image,
            companions=settings.docker.companions,
            profile=settings.docker.profile,
        )
    )


def run_doctor_structured(
    *, project_root: str = ".", quick: bool = False
) -> dict[str, Any]:
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

    # Docker checks (Epic 46.7)
    docker_checks = _collect_docker_checks_sync(root)

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

    # Docker section
    docker_results: list[dict[str, str | bool]] = []
    docker_pass = 0
    docker_fail = 0
    for check in docker_checks:
        entry_d: dict[str, str | bool] = {
            "name": check.name,
            "ok": check.ok,
            "message": check.message,
        }
        if check.detail:
            entry_d["detail"] = check.detail
        docker_results.append(entry_d)
        if check.ok:
            docker_pass += 1
            pass_count += 1
        else:
            docker_fail += 1
            fail_count += 1

    out: dict[str, Any] = {
        "checks": results,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "all_passed": fail_count == 0,
        "quick_mode": quick,
    }

    if docker_results:
        out["docker_checks"] = {
            "checks": docker_results,
            "pass_count": docker_pass,
            "fail_count": docker_fail,
        }

    # Consumer requirements summary (Epic 50)
    all_checks = checks + docker_checks
    out["requirements_summary"] = _build_requirements_summary(all_checks)

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

    # Docker checks (Epic 46.7)
    docker_checks = _collect_docker_checks_sync(root)
    if docker_checks:
        click.echo("")
        click.echo(click.style("--- Docker Health ---", bold=True))
        click.echo("")
        for check in docker_checks:
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
    all_checks = checks + docker_checks
    click.echo("")
    click.echo(click.style("=== Consumer Requirements Summary ===", bold=True))
    req_summary = _build_requirements_summary(all_checks)
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
