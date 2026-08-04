"""Doctor checks for AGENTS.md, Karpathy guidelines, yaml, and config scope (TAP-5606 split).

Covers ``AGENTS.md`` freshness, the Karpathy guidelines single-home check,
``.tapps-mcp.yaml`` parse validation, and the user-vs-project config scope
recommendation. Claude settings and Cursor hook-wiring checks live in
:mod:`tapps_mcp.distribution.doctor_hooks_cursor`.
"""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.distribution.doctor_result import CheckResult


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


def _karpathy_home_sha_summary(
    existing: dict[str, dict[str, str | None]], preferred: str
) -> tuple[str, list[str]]:
    """Return ``(homes_summary, stale_secondaries)`` for the Karpathy block reports."""
    home_sha_parts: list[str] = []
    stale_secondaries: list[str] = []
    for rel in ("AGENTS.md", "CLAUDE.md"):
        report = existing.get(rel)
        if report is None or report["state"] not in ("ok", "stale"):
            continue
        sha = report["current_sha"] or "unknown"
        short = sha[:7] if sha != "unknown" else sha
        part = f"{rel}@{short}"
        home_sha_parts.append(part)
        if rel != preferred and report["state"] == "stale":
            stale_secondaries.append(part)
    homes_summary = ", ".join(home_sha_parts) if home_sha_parts else preferred
    return homes_summary, stale_secondaries


def _karpathy_cursor_rule_result(
    cursor: dict[str, str | None], msg: str, expected_short: str
) -> CheckResult | None:
    """Return a failing :class:`CheckResult` for a bad Cursor-rule state, else ``None``."""
    cursor_state = cursor["state"]
    if cursor_state in ("ok", "skipped_no_cursor"):
        return None
    if cursor_state == "missing":
        return CheckResult(
            "Karpathy guidelines",
            False,
            f"{msg}; Cursor rule missing",
            "Run: tapps_upgrade (or tapps_init with include_karpathy=True)",
        )
    current = cursor["current_sha"] or "unknown"
    return CheckResult(
        "Karpathy guidelines",
        False,
        f"{msg}; Cursor rule stale (@{current}; expected {expected_short})",
        "Run: tapps_upgrade (or tapps_init with include_karpathy=True)",
    )


def _karpathy_preferred_home_failure(
    pref: dict[str, str | None], preferred: str, homes_summary: str, expected_short: str
) -> CheckResult | None:
    """Return a failing result when the preferred home is missing or stale, else ``None``."""
    pref_state = pref["state"]
    if pref_state == "missing":
        return CheckResult(
            "Karpathy guidelines",
            False,
            f"missing in preferred home: {preferred}",
            "Run: tapps_upgrade (or tapps_init with include_karpathy=True)",
        )
    if pref_state == "stale":
        current = pref["current_sha"] or "unknown"
        return CheckResult(
            "Karpathy guidelines",
            False,
            f"stale ({preferred}@{current}; expected {expected_short}"
            f"; homes: {homes_summary})",
            "Run: tapps_upgrade (or tapps_init with include_karpathy=True)",
        )
    return None


def check_karpathy_guidelines(project_root: Path) -> CheckResult:
    """Check the Karpathy guidelines block (ADR-0031 single-home).

    Preferred home is ``AGENTS.md`` when present, otherwise ``CLAUDE.md``.
    The secondary file may omit the block (upgrade ``--force`` strips dual
    installs). Dual presence is reported by ``check_karpathy_dual_install``.

    TAP-5361: every home that contains a block is reported with its pinned
    SHA. A stale secondary copy warns (does not pass) so a current preferred
    home cannot hide conflicting guidance loaded into the same session.

    When ``.cursor/rules/`` exists, also requires
    ``karpathy-guidelines.mdc`` pinned to the vendored SHA.

    - Passes when the preferred home is current, no secondary is stale, and
      the Cursor rule is ok / not applicable.
    - Warns when the preferred home is current but a secondary home is stale.
    - Fails when neither file exists, or the preferred home is missing/stale,
      or the Cursor rule is missing/stale while ``.cursor/rules/`` exists.
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

    preferred = "AGENTS.md" if "AGENTS.md" in existing else "CLAUDE.md"
    pref = existing[preferred]

    # Report SHA for every home that actually contains a block (ok or stale).
    homes_summary, stale_secondaries = _karpathy_home_sha_summary(existing, preferred)
    cursor = karpathy_block.check_cursor_rule(project_root)

    pref_failure = _karpathy_preferred_home_failure(pref, preferred, homes_summary, expected_short)
    if pref_failure is not None:
        return pref_failure

    # preferred is ok
    msg = (
        f"Karpathy guidelines homes: {homes_summary}; "
        f"expected {expected_short} (preferred home: {preferred})"
    )
    if cursor["state"] == "ok":
        msg += f"; Cursor rule ok ({karpathy_block.KARPATHY_CURSOR_RULE_REL})"
    else:
        cursor_failure = _karpathy_cursor_rule_result(cursor, msg, expected_short)
        if cursor_failure is not None:
            return cursor_failure

    if stale_secondaries:
        return CheckResult(
            "Karpathy guidelines",
            False,
            f"WARN: {msg}; stale secondary: {', '.join(stale_secondaries)}",
            "Run: tapps-mcp upgrade --force to strip the secondary copy "
            "(non-force upgrade refreshes the preferred home but retains dual-home).",
            severity="warn",
        )
    return CheckResult("Karpathy guidelines", True, msg)


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
