"""Doctor checks for operator secrets, brain-docs, and Context7 (TAP-5606 split).

Covers operator-secret resolvability (Context7 + brain auth env/dotenv
lookups), the brain ``docs_lookup`` probe (ADR-0014/0015), the legacy
Context7-env-in-MCP-config warning, and the live Context7 reachability
check. Split out of ``doctor_consumer`` to keep both modules within the
maintainability budget.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tapps_mcp.distribution.doctor_mcp import (
    _brain_http_url_for_checks,
    _doctor_brain_headers,
    _is_unsubstituted_placeholder,
)
from tapps_mcp.distribution.doctor_result import CheckResult


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


def _env_file_get_value(path: Path, key: str) -> str | None:
    """Return the value for *key* from a dotenv-style file, or None."""
    if not path.is_file():
        return None
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
                return val
    except OSError:
        return None
    return None


def _env_file_sets_key(path: Path, key: str) -> bool:
    """Return True when *path* defines *key* with a non-empty, non-placeholder value."""
    return _env_file_get_value(path, key) is not None


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
                env.get("TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN") or env.get("TAPPS_BRAIN_AUTH_TOKEN")
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
    if (
        _mcp_configs_set_context7(root)
        and not docs_via_brain_enabled(settings)
        and not _operator_secret_available("TAPPS_MCP_CONTEXT7_API_KEY", project_root=root)
        and not _operator_secret_available("CONTEXT7_API_KEY", project_root=root)
    ):
        missing.append("TAPPS_MCP_CONTEXT7_API_KEY")

    brain_configured = bool(_brain_http_url_for_checks(root)) or _mcp_configs_reference_brain_auth(
        root
    )
    if (
        brain_configured
        and not _operator_secret_available("TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN", project_root=root)
        and not _operator_secret_available("TAPPS_BRAIN_AUTH_TOKEN", project_root=root)
    ):
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


def check_context7_configured_without_key(root: Path) -> CheckResult:
    """TAP-6443: flag a repo where Context7 is the active docs route but no
    key is resolvable anywhere ``_operator_secret_available`` looks.

    ``check_context7_live``'s ``no_key`` branch treats this as informational
    (``ok=True``) since the llms.txt fallback means lookups still work --
    but it never raises the failure signal for the fleet-audit case this
    check closes: a repo configured for Context7 (not ``docs_via_brain``)
    whose key silently stopped resolving.
    """
    from tapps_core.config.settings import load_settings
    from tapps_core.knowledge.brain_docs import docs_via_brain_enabled

    try:
        settings = load_settings(project_root=root)
    except Exception:
        return CheckResult(
            "context7_configured_without_key",
            True,
            "Skipped (could not load settings)",
        )

    if docs_via_brain_enabled(settings):
        return CheckResult(
            "context7_configured_without_key",
            True,
            "Skipped (docs_via_brain enabled — Context7 not used)",
        )

    if _operator_secret_available("TAPPS_MCP_CONTEXT7_API_KEY", project_root=root):
        return CheckResult(
            "context7_configured_without_key",
            True,
            "Context7 API key resolvable",
        )

    return CheckResult(
        "context7_configured_without_key",
        False,
        "Context7 is the active docs route but no API key is resolvable "
        "(tapps_lookup_docs will fall back to llms.txt or fail)",
        "Set TAPPS_MCP_CONTEXT7_API_KEY (shell env, ~/.tapps-operator.env, "
        "or project .env), or enable docs_via_brain if a tapps-brain "
        "fallback is reachable.",
    )


def check_context7_live(root: Path, *, quick: bool = False) -> CheckResult:
    """Live Context7 liveness probe (TAP — lookup-docs discipline).

    Replaces key-presence guessing with a real round-trip verdict. Warn-only:
    the llms.txt fallback means a dead Context7 degrades, it does not break.
    Skipped in quick mode (network) and when docs route through tapps-brain.
    """
    from tapps_core.config.settings import load_settings
    from tapps_core.knowledge.brain_docs import docs_via_brain_enabled
    from tapps_mcp.diagnostics import probe_context7

    if quick:
        return CheckResult(
            "context7_live",
            True,
            "Skipped (quick mode — run without --quick for a live probe)",
        )

    try:
        settings = load_settings(project_root=root)
    except Exception:
        return CheckResult("context7_live", True, "Skipped (could not load settings)")

    if docs_via_brain_enabled(settings):
        return CheckResult(
            "context7_live",
            True,
            "Skipped (docs_via_brain enabled — Context7 not used)",
        )

    diag = probe_context7(root, settings.context7_api_key, force=True)
    latency = f"{diag.latency_ms:.0f}ms" if diag.latency_ms is not None else "n/a"

    if diag.status == "no_key":
        return CheckResult(
            "context7_live",
            True,
            "No Context7 API key — using llms.txt fallback (set TAPPS_MCP_CONTEXT7_API_KEY for richer docs)",
        )
    if diag.status == "available":
        return CheckResult("context7_live", True, f"Context7 reachable ({latency})")
    if diag.status == "unauthorized":
        return CheckResult(
            "context7_live",
            False,
            "Context7 rejected the API key (expired/revoked/invalid)",
            "Rotate TAPPS_MCP_CONTEXT7_API_KEY — get a key at https://context7.com.",
        )
    if diag.status == "unreachable":
        return CheckResult(
            "context7_live",
            False,
            f"Context7 unreachable ({diag.detail or 'network error'})",
            "Transient — llms.txt fallback is active; re-run doctor once connectivity is restored.",
        )
    return CheckResult("context7_live", True, f"Context7 status: {diag.status}")
