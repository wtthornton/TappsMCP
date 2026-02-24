"""TappsMCP doctor: diagnose configuration, rules, and connectivity."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import click

from tapps_mcp.common.logging import get_logger

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


def check_claude_md(project_root: Path) -> CheckResult:
    """Check if CLAUDE.md exists and contains TAPPS reference."""
    claude_md = project_root / "CLAUDE.md"
    if not claude_md.exists():
        return CheckResult(
            "CLAUDE.md rules",
            False,
            "CLAUDE.md not found in project root",
            "Run: tapps-mcp init --host claude-code --rules",
        )
    content = claude_md.read_text(encoding="utf-8")
    if "TAPPS" in content:
        return CheckResult("CLAUDE.md rules", True, "CLAUDE.md contains TAPPS pipeline rules")
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
    """Check ``.claude/settings.json`` for TappsMCP permission entries.

    Both ``mcp__tapps-mcp`` (bare server match) and ``mcp__tapps-mcp__*``
    (wildcard) are needed to work around known Claude Code permission bugs
    (issues #3107, #13077, #27139).
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
    if not missing:
        return CheckResult(
            ".claude/settings.json",
            True,
            "TappsMCP permission entries present (bare + wildcard)",
        )
    return CheckResult(
        ".claude/settings.json",
        False,
        f"Missing permission entries: {', '.join(missing)}",
        "Run: tapps-mcp upgrade --host claude-code",
    )


def check_hooks(project_root: Path) -> CheckResult:
    """Check if TappsMCP hooks directory exists with session-start hook."""
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
            "Run: tapps-mcp upgrade --force to regenerate hooks",
        )

    return CheckResult(
        "Hooks",
        True,
        f"TappsMCP hooks found for: {', '.join(found)} (including session-start)",
    )


def check_quality_tools() -> list[CheckResult]:
    """Check for installed quality tools (ruff, mypy, bandit, radon)."""
    from tapps_mcp.tools.tool_detection import detect_installed_tools

    results: list[CheckResult] = []
    tools = detect_installed_tools()
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
# Main entry point
# ---------------------------------------------------------------------------


def _collect_checks(root: Path) -> list[CheckResult]:
    """Collect all diagnostic checks for the given project root."""
    checks: list[CheckResult] = []
    checks.append(check_binary_on_path())
    checks.append(check_claude_code_user())
    checks.append(check_claude_code_project(root))
    checks.append(check_cursor_config(root))
    checks.append(check_vscode_config(root))
    checks.append(check_claude_md(root))
    checks.append(check_cursor_rules(root))
    checks.append(check_agents_md(root))
    checks.append(check_claude_settings(root))
    checks.append(check_hooks(root))
    checks.extend(check_quality_tools())
    return checks


def run_doctor_structured(*, project_root: str = ".") -> dict[str, Any]:
    """Run all diagnostic checks and return structured results.

    Returns a dict with ``checks``, ``pass_count``, ``fail_count``,
    and ``all_passed`` for programmatic consumption (MCP tool).
    """
    root = Path(project_root).resolve()
    log.info("doctor_structured", project_root=str(root))

    checks = _collect_checks(root)

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

    return {
        "checks": results,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "all_passed": fail_count == 0,
    }


def run_doctor(*, project_root: str = ".") -> bool:
    """Run all diagnostic checks and print a summary.

    Returns ``True`` if all checks pass, ``False`` otherwise.
    """
    root = Path(project_root).resolve()
    log.info("doctor_command", project_root=str(root))

    checks = _collect_checks(root)

    # Print report
    click.echo("")
    click.echo(click.style("=== TappsMCP Doctor Report ===", bold=True))
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

    return fail_count == 0
