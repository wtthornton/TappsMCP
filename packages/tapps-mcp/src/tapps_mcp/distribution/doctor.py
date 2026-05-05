"""TappsMCP doctor: diagnose configuration, rules, and connectivity."""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

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


def check_binary_version_mismatch() -> CheckResult:
    """Warn when the global ``tapps-mcp`` binary is a different version than this server.

    A stale global binary (e.g. from ``uv tool install``) can cause opaque
    import errors when the server code references modules that no longer exist.
    """
    import subprocess

    from tapps_mcp import __version__

    tapps_bin = shutil.which("tapps-mcp")
    if not tapps_bin:
        return CheckResult(
            "Binary version",
            True,
            "tapps-mcp not on PATH (version check skipped)",
        )

    try:
        result = subprocess.run(
            [tapps_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return CheckResult(
                "Binary version",
                True,
                "Could not determine binary version (check skipped)",
            )
        # Output format varies; extract version-like string
        bin_version = result.stdout.strip().split()[-1]
    except Exception:
        return CheckResult(
            "Binary version",
            True,
            "Version check failed (skipped)",
        )

    if bin_version == __version__:
        return CheckResult(
            "Binary version",
            True,
            f"Binary and server versions match: {__version__}",
        )
    return CheckResult(
        "Binary version",
        False,
        f"Version mismatch: binary={bin_version}, server={__version__}",
        f"Reinstall: uv tool install --force --editable <tapps-mcp-path> "
        f"or: pip install --force-reinstall tapps-mcp=={__version__}",
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
    args = entry.get("args", [])
    return (
        f"Unexpected command: '{command}' (expected 'tapps-mcp', 'uv run tapps-mcp serve',"
        " or path to tapps-mcp.exe)"
        if not _is_valid_tapps_command(command, args if isinstance(args, list) else None)
        else None
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


def check_linear_issue_skill_current(project_root: Path) -> CheckResult:
    """Check the ``linear-issue`` skill is deployed and includes the save_issue tool.

    The updated skill (TAP-980 Phase A) grants `mcp__plugin_linear_linear__save_issue`
    so agents can invoke the full create-and-push flow through the skill rather
    than calling save_issue directly. Old versions of the skill lacked this tool
    in ``allowed-tools``, which forced agents to bypass the skill for writes.
    """
    skill_path = project_root / ".claude" / "skills" / "linear-issue" / "SKILL.md"
    if not skill_path.exists():
        return CheckResult(
            "linear-issue skill",
            False,
            ".claude/skills/linear-issue/SKILL.md not found",
            "Run: tapps-mcp upgrade",
        )
    content = skill_path.read_text(encoding="utf-8")
    if "mcp__plugin_linear_linear__save_issue" not in content:
        return CheckResult(
            "linear-issue skill",
            False,
            "linear-issue skill missing save_issue in allowed-tools (stale version)",
            "Run: tapps-mcp upgrade --force",
        )
    return CheckResult(
        "linear-issue skill",
        True,
        "linear-issue skill includes docs-mcp generators + save_issue",
    )


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


def check_finish_task_skill(project_root: Path) -> CheckResult:
    """Check the ``tapps-finish-task`` composite skill is deployed (TAP-977).

    The skill bundles validate_changed -> checklist -> optional memory.save as
    one invocation so agents don't drop steps of the closing sequence.
    """
    skill_path = project_root / ".claude" / "skills" / "tapps-finish-task" / "SKILL.md"
    if not skill_path.exists():
        return CheckResult(
            "tapps-finish-task skill",
            False,
            ".claude/skills/tapps-finish-task/SKILL.md not found",
            "Run: tapps-mcp upgrade",
        )
    return CheckResult(
        "tapps-finish-task skill",
        True,
        f"Present: {skill_path}",
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

    # Validate cursor hooks config if present
    if "Cursor" in found:
        cursor_result = _check_cursor_hooks_config(project_root, found)
        if cursor_result is not None:
            return cursor_result

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


def check_brain_http_auth(root: Path) -> CheckResult:
    """Verify that HTTP-bridge auth config is complete when HTTP mode is active.

    When ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` is set, the client must also have
    ``memory.brain_auth_token`` (env: ``TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN``) and
    ``memory.brain_project_id``. Missing either silently sends unauthenticated
    (or partially authenticated) requests and every memory/hive call returns
    401 or 403 — but ``memory_status.degraded`` looked OK until we fixed it
    because the old probe only hit ``/health`` (unauthenticated).

    A common mistake is setting ``TAPPS_BRAIN_AUTH_TOKEN`` (tapps-brain's
    server-side token env) instead of ``TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN``
    (the client-side token tapps-mcp reads).
    """
    import os

    http_url = os.environ.get("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "").strip()
    if not http_url:
        return CheckResult(
            "tapps-brain HTTP auth",
            True,
            "Not in HTTP mode (TAPPS_MCP_MEMORY_BRAIN_HTTP_URL unset)",
        )

    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings(project_root=root)
        token_present = settings.memory.brain_auth_token is not None
        project_id_present = bool(settings.memory.brain_project_id)
    except Exception as exc:
        return CheckResult(
            "tapps-brain HTTP auth",
            False,
            f"Could not load settings: {exc}",
            "Fix .tapps-mcp.yaml or env vars and re-run doctor.",
        )

    if token_present and project_id_present:
        return CheckResult(
            "tapps-brain HTTP auth",
            True,
            f"HTTP mode configured with bearer token + project id ({http_url})",
        )

    missing: list[str] = []
    hints: list[str] = []
    if not token_present:
        missing.append("brain_auth_token")
        wrong = os.environ.get("TAPPS_BRAIN_AUTH_TOKEN", "")
        if wrong:
            hints.append(
                "Detected TAPPS_BRAIN_AUTH_TOKEN in env — that is tapps-brain's "
                "server-side token. The client reads TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN."
            )
        else:
            hints.append(
                "Set TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN (client bearer token for "
                "authenticated tapps-brain HTTP calls)."
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


def check_dual_memory_server(root: Path) -> CheckResult:
    """Warn if tapps-brain-mcp is configured alongside TappsMCP (split-brain risk).

    Scans common MCP config locations for a ``tapps-brain-mcp`` or
    ``tapps-brain`` server entry.  Running both memory servers against the
    same project causes two processes accessing the same SQLite database.
    """
    config_paths = [
        root / ".claude" / "settings.json",
        root / ".claude" / "settings.local.json",
        root / ".cursor" / "mcp.json",
        root / ".vscode" / "mcp.json",
        Path.home() / ".claude" / "settings.json",
    ]
    for cfg in config_paths:
        if not cfg.exists():
            continue
        try:
            text = cfg.read_text(encoding="utf-8-sig")
            if "tapps-brain-mcp" in text or "tapps-brain" in text.lower():
                # Exclude our own doctor check reference — look for server config patterns
                if any(
                    marker in text
                    for marker in ['"tapps-brain-mcp"', "'tapps-brain-mcp'", "tapps-brain-mcp"]
                ):
                    return CheckResult(
                        "Dual memory server",
                        True,
                        f"tapps-brain-mcp may be configured alongside TappsMCP in {cfg.name}",
                        "Running both causes split-brain risk. Use tapps_memory for all memory "
                        "operations. Remove the tapps-brain-mcp server entry if using TappsMCP.",
                    )
        except Exception:
            continue

    return CheckResult(
        "Dual memory server",
        True,
        "No dual memory server detected",
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


def _collect_checks(root: Path, *, quick: bool = False) -> list[CheckResult]:
    """Collect all diagnostic checks for the given project root.

    Args:
        root: Project root directory.
        quick: When True, skip quality tool version checks for faster results.
    """
    checks: list[CheckResult] = []
    checks.append(check_binary_on_path())
    checks.append(check_binary_version_mismatch())
    checks.append(check_claude_code_user(project_root=root))
    checks.append(check_claude_code_project(root))
    checks.append(check_cursor_config(root))
    checks.append(check_vscode_config(root))
    checks.append(check_mcp_client_config(root))
    checks.append(check_scope_recommendation(root))
    checks.append(check_claude_md(root))
    checks.append(check_cursor_rules(root))
    checks.append(check_linear_standards_rule(root))
    checks.append(check_autonomy_rule(root))
    # TAP-978: scoped quality rules — report presence + gate status.
    checks.append(check_security_rule(root))
    checks.append(check_test_quality_rule(root))
    checks.append(check_config_files_rule(root))
    checks.append(check_linear_issue_skill_current(root))
    checks.append(check_finish_task_skill(root))
    checks.append(check_pretooluse_matchers(root))
    checks.append(check_agents_md(root))
    checks.append(check_karpathy_guidelines(root))
    checks.append(check_claude_settings(root))
    checks.append(check_claude_hook_scripts(root))
    checks.append(check_hooks(root))
    checks.append(check_stale_exe_backups())
    checks.append(check_tapps_brain())
    checks.append(check_brain_http_auth(root))
    checks.append(check_memory_pipeline_config(root))
    checks.append(check_dual_memory_server(root))
    checks.append(check_plaintext_secrets(root))
    checks.append(check_uv_path_mismatch(root))
    checks.append(check_linear_sdlc(root))
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
