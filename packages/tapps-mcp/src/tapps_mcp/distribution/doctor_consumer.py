"""Doctor checks for consumer-facing requirements and config secrets (TAP-5606 split).

Covers the 7-requirement consumer summary mapping, uv PATH / plaintext-secret
scans, report-studio and Linear SDLC template freshness, and ADR-0014 legacy
doc cache cleanup. Operator-secret resolvability, brain-docs, and Context7
checks live in :mod:`tapps_mcp.distribution.doctor_context7`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tapps_mcp.distribution.doctor_result import CheckResult

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
    check_by_name: dict[str, bool] = {
        # Treat advisory WARNs as non-blocking for the requirements roll-up.
        c.name: c.severity != "fail"
        for c in checks
    }

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


