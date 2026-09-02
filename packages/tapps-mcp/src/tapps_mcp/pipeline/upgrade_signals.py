"""Project-shape detection for the upgrade pipeline.

Extracted from :mod:`tapps_mcp.pipeline.upgrade` (TAP-6913). These are the
read-only probes that decide *which* artifacts an upgrade is allowed to touch:
does the repo look like Python, does it carry infra config, has the consumer
already opted in to TappsMCP, which host(s) are installed.
"""

from __future__ import annotations

import os
from pathlib import Path

from tapps_core.common.logging import get_logger

log = get_logger(__name__)

AGENTS_MD_OPT_OUT_SENTINEL = "<!-- tapps:agents-md-disabled -->"

CONSENT_HOSTS = ("claude-code", "cursor")

# Directories a language probe must not descend into: vendored deps, build
# output, and caches. Walking them costs seconds on a monorepo and never
# changes the verdict.
_SIGNAL_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "env",
        "node_modules",
        ".git",
        "__pycache__",
        "dist",
        "build",
        ".tox",
        ".pytest_cache",
        ".eggs",
        "htmlcov",
        ".mypy_cache",
        "site-packages",
        ".tapps-mcp-cache",
    }
)

# Upper bound on files inspected by the ``*.py`` fallback scan, so a
# pathologically-nested tree can't hang the session.
_SIGNAL_FILE_BUDGET = 2000


def _has_python_marker_file(project_root: Path) -> bool:
    """True when a packaging marker proves the repo is Python without a walk."""
    for marker in ("pyproject.toml", "setup.py", "setup.cfg"):
        if (project_root / marker).exists():
            return True
    try:
        return any(project_root.glob("requirements*.txt"))
    except OSError:
        return False


def has_python_signals(project_root: Path) -> bool:
    """Shallow check: does this project look like Python?

    Returns True if any marker file exists (``pyproject.toml``, ``setup.py``,
    ``setup.cfg``, ``requirements*.txt``) or the first ``*.py`` outside
    well-known virtualenv/build dirs is found. Stops at the first hit.
    """
    if _has_python_marker_file(project_root):
        return True

    # TAP-686: prune skip_dirs in-place (rglob doesn't — it walks everything
    # and filters in Python, so monorepos with large vendor trees waste time
    # even though the loop short-circuits). Also budget the scan.
    budget = _SIGNAL_FILE_BUDGET
    try:
        for _dirpath, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if d not in _SIGNAL_SKIP_DIRS]
            for name in files:
                if name.endswith(".py"):
                    return True
                budget -= 1
                if budget <= 0:
                    return False
    except OSError as exc:
        log.warning("python_signals_walk_failed", project_root=str(project_root), error=str(exc))
        return False
    return False


def has_infra_signals(project_root: Path) -> bool:
    """True if the repo has Dockerfile or docker-compose files.

    Used to gate ``tapps-pipeline.md`` on non-Python projects: the rule's path
    scope includes ``Dockerfile*`` and ``docker-compose*.yml``, so infra-heavy
    bash repos may still want it even without Python code.
    """
    if any(project_root.glob("Dockerfile*")):
        return True
    if any(project_root.glob("docker-compose*.yml")):
        return True
    return any(project_root.glob("docker-compose*.yaml"))


def _host_has_tapps_entry(host: str, project_root: Path) -> bool:
    """True when *host*'s MCP config already lists a tapps-mcp or nlt-* server."""
    import json

    from tapps_mcp.distribution.setup_generator import (
        _get_config_path,
        _get_servers_key,
        _strip_jsonc_comments,
    )

    path = _get_config_path(host, project_root)
    if not path.exists():
        return False
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(_strip_jsonc_comments(raw))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    servers = data.get(_get_servers_key(host)) or {}
    if not isinstance(servers, dict):
        return False
    if "tapps-mcp" in servers:
        return True
    from tapps_mcp.distribution.nlt_mcp_config import list_nlt_server_ids_in_config

    return bool(list_nlt_server_ids_in_config(servers))


def mcp_json_has_tapps_entry(project_root: Path) -> bool:
    """True if the user has previously opted in to TappsMCP on *any* host.

    Consent is about intent to use TappsMCP, not about a specific host.
    A user who added tapps-mcp to Cursor and is now running a Claude Code
    upgrade should be treated as opted in — checking a single host would
    refuse to regenerate the Claude Code config even though they clearly want
    it.  We accept an entry on any configured host as proof of consent.

    Upgrade never implicitly opts a consumer *in* to TappsMCP. We only
    regenerate the config when the user has previously opted in (entry exists
    but is broken). For greenfield, ``tapps_init`` is the right entry point.
    """
    return any(_host_has_tapps_entry(h, project_root) for h in CONSENT_HOSTS)


def agents_md_opt_out(project_root: Path, *, create_flag: bool) -> str | None:
    """Return a human reason to skip AGENTS.md creation, or ``None`` to proceed.

    Checked only when AGENTS.md does *not* yet exist; existing files are
    always merged.
    """
    if not create_flag:
        return "upgrade_create_agents_md=false"
    claude_md = project_root / "CLAUDE.md"
    if claude_md.exists():
        try:
            if AGENTS_MD_OPT_OUT_SENTINEL in claude_md.read_text(encoding="utf-8"):
                return f"CLAUDE.md contains {AGENTS_MD_OPT_OUT_SENTINEL}"
        except OSError:
            pass
    return None


def detect_platform(project_root: Path) -> str:
    """Detect the platform from existing config files."""
    has_claude = (project_root / ".claude").is_dir() or (project_root / "CLAUDE.md").exists()
    has_cursor = (project_root / ".cursor").is_dir()

    if has_claude and has_cursor:
        return "both"
    if has_claude:
        return "claude"
    if has_cursor:
        return "cursor"
    return ""


def hosts_for_platform(detected: str) -> list[str]:
    """Map a detected platform string onto the concrete host ids to upgrade."""
    hosts: list[str] = []
    if detected in {"claude", "both"}:
        hosts.append("claude-code")
    if detected in {"cursor", "both"}:
        hosts.append("cursor")
    return hosts
