"""Doctor checks for the memory pipeline, session sentinel, and quality tools (TAP-5606 split).

Covers the session-start sentinel freshness check, effective memory-config
echo, ``memory.profile`` resolvability, HTTP-only memory CLI mode guidance,
the dual-memory-server guard (split-brain risk), and the installed-quality-tools
scan (``ruff``/``mypy``/``bandit``/``radon``). Split out of ``doctor_nlt`` to
keep both modules within the maintainability budget.
"""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.distribution.doctor_mcp import (
    _ADR_0001_REF,
    _BRAIN_MCP_SERVER_NAMES,
    _brain_http_url_for_checks,
    check_brain_mcp_entry,
)
from tapps_mcp.distribution.doctor_result import CheckResult


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


def check_memory_profile_resolvable(root: Path) -> CheckResult:
    """Warn when ``memory.profile`` names a profile the brain cannot load (TAP-4810)."""
    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings(project_root=root)
        profile_name = str(getattr(settings.memory, "profile", "") or "").strip()
    except Exception as exc:
        return CheckResult(
            "Memory profile resolvable",
            True,
            f"Could not load settings ({exc})",
            "",
        )

    if not profile_name:
        return CheckResult(
            "Memory profile resolvable",
            True,
            "memory.profile unset (brain default applies)",
            "",
        )

    if profile_name == "document-builder":
        return CheckResult(
            "Memory profile resolvable",
            False,
            "memory.profile is 'document-builder' which is not a tapps-brain builtin",
            "Remove memory.profile or set it to a real builtin (e.g. repo-brain). "
            "TAP-4810: init/upgrade no longer write document-builder.",
        )

    try:
        from tapps_brain.profile import get_builtin_profile, list_builtin_profiles

        available = set(list_builtin_profiles())
        if profile_name not in available:
            return CheckResult(
                "Memory profile resolvable",
                False,
                f"memory.profile={profile_name!r} is not a known builtin "
                f"(available: {', '.join(sorted(available))})",
                "Set memory.profile to a tapps-brain builtin (e.g. repo-brain) or remove it.",
            )
        get_builtin_profile(profile_name)
        return CheckResult(
            "Memory profile resolvable",
            True,
            f"memory.profile={profile_name!r} resolves",
            "",
        )
    except ImportError:
        # Offline / brain not importable — only flag known-bad names above.
        return CheckResult(
            "Memory profile resolvable",
            True,
            f"memory.profile={profile_name!r} (brain profile module unavailable to verify)",
            "",
        )
    except Exception as exc:
        return CheckResult(
            "Memory profile resolvable",
            False,
            f"memory.profile={profile_name!r} does not resolve: {exc}",
            "Set memory.profile to a tapps-brain builtin (e.g. repo-brain) or remove it.",
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
                    if ("editable" in line.lower() or "path" in line.lower()) and "=" in line:
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
