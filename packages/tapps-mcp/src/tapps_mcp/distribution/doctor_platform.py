"""Doctor checks for platform scaffolding: hooks, stamps, and scoped rules (TAP-5606 split).

Covers Claude hook-script existence, retired-hook detection, CLAUDE.md /
AGENTS.md version stamps, Cursor rules, path-scoped ``.claude/rules/*``
(security / test-quality / config-files), the ``linear-issue`` skill
freshness check, and the informational PreToolUse matcher report.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

from tapps_core.common.logging import get_logger
from tapps_mcp.distribution.doctor_pipeline import (
    _count_cache_gate_violations_24h,
    _count_session_start_gate_violations_24h,
    _detect_cache_gate_mode,
    _detect_session_start_gate_mode,
    _tapps_skill_bases,
)
from tapps_mcp.distribution.doctor_result import CheckResult

log = get_logger(__name__)


def _upgrade_skip_tokens(project_root: Path) -> frozenset[str]:
    """Return configured ``upgrade_skip_files`` tokens for *project_root*."""
    try:
        from tapps_core.config.settings import load_settings

        return frozenset(load_settings(project_root=project_root).upgrade_skip_files)
    except Exception:
        log.debug("upgrade_skip_tokens_load_failed", exc_info=True)
        return frozenset()


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
                out.extend(
                    m.group(1).replace("\\", "/") for m in _HOOK_SCRIPT_PATH_RE.finditer(cmd)
                )
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


# Retired hooks doctor should flag (remediated by tapps_upgrade). Keys are the
# script basenames; values are the human-readable reason.
_RETIRED_HOOK_REASONS: dict[str, str] = {
    "tapps-pre-tooluse.sh": "fail-open destructive guard — superseded by fail-closed tapps-pre-bash.sh (TAP-1785)",
    "tapps-memory-capture.sh": "no-op session-capture hook — brain-native since TAP-1999",
}


def check_retired_hooks(project_root: Path) -> CheckResult:
    """Flag retired hooks still wired (or, for tapps-pre-tooluse, present).

    The memory-capture hook ships inert via canonical generation, so it is only
    a problem when *wired* into Stop; tapps-pre-tooluse is no longer shipped at
    all, so its mere presence is drift. Both are fixed by ``tapps_upgrade``.
    """
    findings: list[str] = []
    for name in ("settings.json", "settings.local.json"):
        sf = project_root / ".claude" / name
        if not sf.exists():
            continue
        try:
            raw = sf.read_text(encoding="utf-8-sig")
            data = json.loads(raw) if raw.strip() else {}
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        for rel in _hook_paths_from_claude_settings(cast("dict[str, object]", data)):
            base = Path(rel).name
            if base in _RETIRED_HOOK_REASONS:
                findings.append(f"{base} wired via {name} ({_RETIRED_HOOK_REASONS[base]})")
    pre_tooluse = project_root / ".claude" / "hooks" / "tapps-pre-tooluse.sh"
    if pre_tooluse.is_file():
        findings.append(
            f"tapps-pre-tooluse.sh present in .claude/hooks ({_RETIRED_HOOK_REASONS['tapps-pre-tooluse.sh']})"
        )
    if findings:
        return CheckResult(
            "Retired hooks",
            False,
            "; ".join(sorted(set(findings))),
            "Run: tapps-mcp upgrade --host claude-code --force",
        )
    return CheckResult("Retired hooks", True, "No retired hooks wired or present")


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


def _linear_routing_gate_status(matchers: list[str]) -> str:
    linear_matcher = "mcp__plugin_linear_linear__save_issue"
    if linear_matcher in matchers:
        return "Linear routing gate: active"
    return "Linear routing gate: NOT enabled (set linear_enforce_gate: true in .tapps-mcp.yaml)"


def _linear_cache_gate_status(project_root: Path, matchers: list[str]) -> str:
    """Describe Linear cache-gate health, distinguishing blind vs quiet (TAP-5453)."""
    from tapps_mcp.pipeline.linear_mcp_names import matcher_covers_linear_leaf
    from tapps_mcp.server_linear_tools_cache import count_linear_snapshot_files

    cache_mode = _detect_cache_gate_mode(project_root)
    enabled = matcher_covers_linear_leaf(matchers, "list_issues") or cache_mode in (
        "warn",
        "block",
    )
    if not enabled:
        return (
            "Linear cache-first read gate: NOT enabled "
            "(set linear_enforce_cache_gate: warn|block in .tapps-mcp.yaml)"
        )
    viol_24h = _count_cache_gate_violations_24h(project_root)
    if cache_mode in ("warn", "block") and viol_24h == 0:
        if count_linear_snapshot_files(project_root) == 0:
            return (
                f"Linear cache-first read gate: {cache_mode} BLIND "
                "(0 violations in last 24h, empty snapshot cache — gate appears "
                "unmeasured). Remediation: verify PreToolUse matcher covers "
                "Linear list_issues across host server ids "
                "(mcp__…__list_issues; likely hook-matcher mismatch — "
                "run tapps-mcp upgrade --force)"
            )
    return f"Linear cache-first read gate: {cache_mode} ({viol_24h} violations in last 24h)"


def _session_start_gate_status(project_root: Path) -> str:
    session_gate_mode = _detect_session_start_gate_mode(project_root)
    if session_gate_mode not in ("warn", "block"):
        return "Session-start gate: NOT enabled (set session_start_gate: warn|block in .tapps-mcp.yaml)"
    session_viol_24h = _count_session_start_gate_violations_24h(project_root)
    return f"Session-start gate: {session_gate_mode} ({session_viol_24h} violations in last 24h)"


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

    # TAP-1224: cache-first read gate state + violation count. Session-start
    # gate is detected from the baked MODE in the installed pre-gate script
    # rather than the matcher list, since its matcher is a regex over the
    # TappsMCP tool family.
    linear_status = _linear_routing_gate_status(matchers)
    cache_status = _linear_cache_gate_status(project_root, matchers)
    session_status = _session_start_gate_status(project_root)

    if not matchers:
        return CheckResult(
            "PreToolUse matchers",
            True,
            f"no PreToolUse matchers wired (no opt-in gates enabled). "
            f"{linear_status}. {cache_status}. {session_status}",
        )
    return CheckResult(
        "PreToolUse matchers",
        True,
        f"wired: {', '.join(matchers)}. {linear_status}. {cache_status}. {session_status}",
    )


def check_upgrade_skip_tokens(project_root: Path) -> CheckResult:
    """Report ``upgrade_skip_files`` entries outside the fixed vocabulary (TAP-6499).

    An unrecognized entry protects nothing — upgrade rewrites the artifact the
    operator believed was pinned. The failure is silent by construction, so
    doctor is the only place a project learns about it before the overwrite.
    """
    from tapps_mcp.pipeline.upgrade_skip_tokens import (
        describe_unknown_skip_tokens,
        unknown_skip_tokens,
    )

    configured = _upgrade_skip_tokens(project_root)
    if not configured:
        return CheckResult("upgrade_skip_files", True, "no skip tokens configured")

    unknown = unknown_skip_tokens(configured)
    if not unknown:
        return CheckResult(
            "upgrade_skip_files",
            True,
            f"all {len(configured)} token(s) recognized: {', '.join(sorted(configured))}",
        )
    return CheckResult(
        "upgrade_skip_files",
        False,
        f"{len(unknown)} entry/entries protect nothing: {', '.join(unknown)}",
        " ".join(describe_unknown_skip_tokens(unknown)),
        severity="fail",
    )
