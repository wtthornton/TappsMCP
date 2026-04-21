"""Upgrade pipeline for refreshing TappsMCP-generated files.

Provides :func:`upgrade_pipeline` which is called by the
``tapps_upgrade`` MCP tool. Reuses existing generators but operates
in ``upgrade_mode`` so custom command paths are never overwritten.

Design notes — merge over skip
==============================

The upgrade pipeline defaults to *merging* into files that may contain user
content, not overwriting or skipping them. Coverage:

- ``AGENTS.md`` — section-aware smart merge (:mod:`~tapps_mcp.pipeline.agents_md`)
- ``CLAUDE.md`` — H1-section replace (preserves user's non-TAPPS sections)
- ``.mcp.json`` — ``upgrade_mode=True`` preserves custom command paths
- ``.claude/settings.json`` — permissions are merged, not replaced
- Karpathy block — BEGIN/END markers, content-idempotent

Files that are 100% tapps-owned (``.claude/rules/*``, hook scripts, tapps-*
agents and skills) are full overwrites, but are gated per-project so we don't
drop them into repos that don't need them (e.g. Python rules on a bash-only
repo).

Opt-outs — config-first, skip as last resort
============================================

Preferred knobs (in ``.tapps-mcp.yaml``):

- ``upgrade_create_agents_md: false`` — don't create ``AGENTS.md`` if missing;
  existing files still get merged. The HTML comment
  ``<!-- tapps:agents-md-disabled -->`` inside ``CLAUDE.md`` does the same.
- ``include_karpathy_guidelines: false`` — don't install the Karpathy block.
  Already-installed blocks are still refreshed (no silent removal).
- ``force_python_quality_rule: true`` — install the Python rule files even on
  projects with no detected Python signals (override the language gate).

For an MCP-server-only install, call ``tapps_upgrade(mcp_only=True)``.

``upgrade_skip_files`` is the emergency escape hatch — per-artifact tokens
(``AGENTS.md``, ``CLAUDE.md``, ``.mcp.json``,
``.claude/rules/python-quality.md``, ``.claude/rules/agent-scope.md``,
``.claude/rules/tapps-pipeline.md``, ``.claude/settings.json``,
``.claude/hooks``, ``.claude/agents``, ``.claude/skills``, ``karpathy``).
Each token now skips *only* its artifact; in particular ``CLAUDE.md`` no
longer gates hooks/agents/skills/rules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from tapps_core.common.file_operations import (
    AgentInstructions,
    FileManifest,
    FileOperation,
    WriteMode,
    detect_write_mode,
)
from tapps_core.common.logging import get_logger

log = get_logger(__name__)


# Per-artifact skip tokens. Kept as a mapping so we can add short aliases later
# without changing call sites.
_SKIP_TOKENS: dict[str, frozenset[str]] = {
    "agents_md": frozenset({"AGENTS.md"}),
    "claude_md": frozenset({"CLAUDE.md"}),
    "claude_settings": frozenset({".claude/settings.json"}),
    "claude_hooks": frozenset({".claude/hooks"}),
    "claude_agents": frozenset({".claude/agents"}),
    "claude_skills": frozenset({".claude/skills"}),
    "python_quality_rule": frozenset({".claude/rules/python-quality.md"}),
    "agent_scope_rule": frozenset({".claude/rules/agent-scope.md"}),
    "pipeline_rule": frozenset({".claude/rules/tapps-pipeline.md"}),
    "mcp_config": frozenset({".mcp.json"}),
    "karpathy": frozenset({"karpathy"}),
}

_ALL_SKIP_TOKENS: frozenset[str] = frozenset().union(*_SKIP_TOKENS.values())

_AGENTS_MD_OPT_OUT_SENTINEL = "<!-- tapps:agents-md-disabled -->"


def _skipped(artifact: str, skip: set[str]) -> bool:
    return bool(_SKIP_TOKENS.get(artifact, frozenset()) & skip)


def _has_python_signals(project_root: Path) -> bool:
    """Shallow check: does this project look like Python?

    Returns True if any marker file exists (``pyproject.toml``, ``setup.py``,
    ``setup.cfg``, ``requirements*.txt``) or the first ``*.py`` outside
    well-known virtualenv/build dirs is found. Stops at the first hit.
    """
    for marker in ("pyproject.toml", "setup.py", "setup.cfg"):
        if (project_root / marker).exists():
            return True
    try:
        if any(project_root.glob("requirements*.txt")):
            return True
    except OSError:
        pass

    skip_dirs = {".venv", "venv", "node_modules", ".git", "__pycache__", "dist", "build"}
    try:
        for path in project_root.rglob("*.py"):
            if any(part in skip_dirs for part in path.parts):
                continue
            return True
    except OSError:
        return False
    return False


def _has_infra_signals(project_root: Path) -> bool:
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


_CONSENT_HOSTS = ("claude-code", "cursor")


def _mcp_json_has_tapps_entry(project_root: Path, host: str) -> bool:
    """True if the user has previously opted in to TappsMCP on *any* host.

    Consent is about intent to use TappsMCP, not about a specific host.
    A user who added tapps-mcp to Cursor and is now running a Claude Code
    upgrade should be treated as opted in — checking only ``host`` would
    refuse to regenerate the Claude Code config even though they clearly want
    it.  We accept an entry on any configured host as proof of consent.

    Upgrade never implicitly opts a consumer *in* to TappsMCP. We only
    regenerate the config when the user has previously opted in (entry exists
    but is broken). For greenfield, ``tapps_init`` is the right entry point.
    """
    import json

    from tapps_mcp.distribution.setup_generator import _get_config_path, _get_servers_key

    def _has_entry(h: str) -> bool:
        path = _get_config_path(h, project_root)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        servers = data.get(_get_servers_key(h)) or {}
        return isinstance(servers, dict) and "tapps-mcp" in servers

    return any(_has_entry(h) for h in _CONSENT_HOSTS)


def _agents_md_opt_out(project_root: Path, *, create_flag: bool) -> str | None:
    """Return a human reason to skip AGENTS.md creation, or ``None`` to proceed.

    Checked only when AGENTS.md does *not* yet exist; existing files are
    always merged.
    """
    if not create_flag:
        return "upgrade_create_agents_md=false"
    claude_md = project_root / "CLAUDE.md"
    if claude_md.exists():
        try:
            if _AGENTS_MD_OPT_OUT_SENTINEL in claude_md.read_text(encoding="utf-8"):
                return f"CLAUDE.md contains {_AGENTS_MD_OPT_OUT_SENTINEL}"
        except OSError:
            pass
    return None


def _upgrade_agents_md(
    project_root: Path,
    *,
    dry_run: bool = False,
    create_agents_md: bool = True,
) -> dict[str, Any]:
    """Validate and update AGENTS.md to the latest template.

    If ``AGENTS.md`` does not exist, creation is gated:
    - ``create_agents_md=False`` skips creation entirely.
    - A ``<!-- tapps:agents-md-disabled -->`` sentinel inside ``CLAUDE.md``
      also skips creation (for repos where CLAUDE.md is the single source of
      truth).

    Existing ``AGENTS.md`` files always get the section-aware smart merge —
    opting out of creation does not regress upgrades for users who already
    have the file.

    Returns a result dict with ``action`` and optional ``detail``.
    """
    from tapps_mcp.pipeline.agents_md import AgentsValidation, update_agents_md
    from tapps_mcp.prompts.prompt_loader import load_agents_template

    agents_path = project_root / "AGENTS.md"
    template_content = load_agents_template()

    if not agents_path.exists():
        reason = _agents_md_opt_out(project_root, create_flag=create_agents_md)
        if reason is not None:
            return {"action": "skipped", "detail": reason}
        if not dry_run:
            _tmp = agents_path.with_name(agents_path.name + ".tmp")
            try:
                _tmp.write_text(template_content, encoding="utf-8")
                _tmp.replace(agents_path)
            except BaseException:
                _tmp.unlink(missing_ok=True)
                raise
        return {"action": "created"}

    validation = AgentsValidation(agents_path.read_text(encoding="utf-8"))
    if validation.is_up_to_date:
        return {"action": "up-to-date"}

    issues: list[str] = []
    if validation.sections_missing:
        issues.append(f"missing sections: {', '.join(validation.sections_missing)}")
    if validation.tools_missing:
        issues.append(f"missing tools: {', '.join(validation.tools_missing)}")
    detail = "; ".join(issues) or "version mismatch"

    if dry_run:
        return {"action": "needs-update", "detail": detail}
    action, merge_detail = update_agents_md(agents_path, template_content)
    return {"action": action, "detail": merge_detail or detail}


def _refresh_karpathy_blocks(
    project_root: Path,
    *,
    dry_run: bool = False,
    include_karpathy: bool = True,
    skip_files: set[str] | None = None,
) -> dict[str, Any]:
    """Install or refresh the Karpathy guidelines block in AGENTS.md and CLAUDE.md.

    Appends between BEGIN/END markers, preserving content outside them.
    Files that don't exist are skipped (they aren't owned by this upgrade
    step; ``tapps_init`` creates them).

    When ``include_karpathy=False`` (or ``karpathy`` appears in ``skip_files``),
    we skip *installing* the block into files that don't already have it but
    still refresh files that do — opting out must never silently strip user
    content that prior runs added.
    """
    from tapps_mcp.pipeline import karpathy_block

    skip = skip_files or set()
    opted_out = (not include_karpathy) or _skipped("karpathy", skip)

    per_file: dict[str, str] = {}
    for rel in ("AGENTS.md", "CLAUDE.md"):
        target = project_root / rel
        if not target.exists():
            per_file[rel] = "skipped_file_missing"
            continue
        try:
            if opted_out:
                # Only act if already present; never install new blocks.
                existing = target.read_text(encoding="utf-8")
                if karpathy_block._find_block_span(existing) is None:
                    per_file[rel] = "skipped (opt-out)"
                    continue
            per_file[rel] = karpathy_block.install_or_refresh(target, dry_run=dry_run)
        except (OSError, ValueError) as exc:
            log.exception("karpathy_block_failed", file=rel)
            per_file[rel] = f"error: {exc}"

    return {
        "source_sha": karpathy_block.KARPATHY_GUIDELINES_SOURCE_SHA,
        "files": per_file,
        "opted_out": opted_out,
    }


def _upgrade_mcp_config(
    host: str,
    project_root: Path,
    result: dict[str, Any],
    *,
    force: bool,
    dry_run: bool,
    skip: set[str],
) -> None:
    """Populate result["components"]["mcp_config"] for one host.

    Consent gate: only regenerates ``.mcp.json`` when the user has previously
    opted in (entry exists) or ``force=True``.  Missing entries are not
    treated as broken — greenfield projects should go through ``tapps_init``.
    """
    from tapps_mcp.distribution.setup_generator import (
        _generate_config,
        _get_config_path,
        _get_servers_key,
        _validate_config_file,
    )

    config_path = _get_config_path(host, project_root)
    servers_key = _get_servers_key(host)
    error = _validate_config_file(config_path, servers_key)
    already_opted_in = _mcp_json_has_tapps_entry(project_root, host)
    if error is None:
        result["components"]["mcp_config"] = "ok"
    elif not already_opted_in and not force:
        result["components"]["mcp_config"] = {
            "action": "skipped (no existing tapps-mcp entry)",
            "hint": (
                "Run `tapps_init` or pass force=True to create "
                f"{config_path.name} with the tapps-mcp server entry."
            ),
        }
    elif not dry_run:
        _generate_config(host, project_root, force=True, upgrade_mode=True)
        result["components"]["mcp_config"] = "regenerated"
    else:
        result["components"]["mcp_config"] = f"needs-fix: {error}"


def _upgrade_claude_code_dry_run(
    result: dict[str, Any],
    *,
    force: bool,
    python_ok: bool,
    infra_ok: bool,
) -> None:
    """Populate dry-run component hints for the claude-code host."""
    result["components"]["claude_md"] = "would-refresh" if force else "check-needed"
    result["components"]["settings"] = "check-needed"
    result["components"]["hooks"] = "would-regenerate"
    result["components"]["agents"] = "would-regenerate"
    result["components"]["skills"] = "would-regenerate"
    result["components"]["python_quality_rule"] = (
        "would-regenerate" if python_ok else "skipped (no python detected)"
    )
    result["components"]["agent_scope_rule"] = "would-regenerate"
    result["components"]["pipeline_rule"] = (
        "would-regenerate"
        if (python_ok or infra_ok)
        else "skipped (no python or infra detected)"
    )


def _upgrade_claude_code_live(
    project_root: Path,
    result: dict[str, Any],
    *,
    force: bool,
    engagement_level: str,
    skip: set[str],
    python_ok: bool,
    infra_ok: bool,
) -> None:
    """Run live (non-dry-run) artifact upgrades for the claude-code host."""
    from tapps_mcp.pipeline.init import _bootstrap_claude, _bootstrap_claude_settings
    from tapps_mcp.pipeline.platform_bundles import generate_claude_pipeline_rule
    from tapps_mcp.pipeline.platform_generators import (
        generate_claude_agent_scope_rule,
        generate_claude_hooks,
        generate_claude_python_quality_rule,
        generate_skills,
        generate_subagent_definitions,
    )

    # CLAUDE.md — merges into user content via _replace_tapps_section.
    if _skipped("claude_md", skip):
        result["components"]["claude_md"] = "skipped (upgrade_skip_files)"
    else:
        result["components"]["claude_md"] = _bootstrap_claude(project_root, overwrite=force)

    if _skipped("claude_settings", skip):
        result["components"]["settings"] = "skipped (upgrade_skip_files)"
    else:
        result["components"]["settings"] = _bootstrap_claude_settings(
            project_root, engagement_level=engagement_level
        )

    if _skipped("claude_hooks", skip):
        result["components"]["hooks"] = "skipped (upgrade_skip_files)"
    else:
        hooks_result = generate_claude_hooks(project_root)
        result["components"]["hooks"] = {
            "scripts_created": hooks_result.get("scripts_created", []),
            "hooks_added": hooks_result.get("hooks_added", 0),
        }

    if _skipped("claude_agents", skip):
        result["components"]["agents"] = "skipped (upgrade_skip_files)"
    else:
        result["components"]["agents"] = generate_subagent_definitions(
            project_root, "claude", overwrite=True
        )

    if _skipped("claude_skills", skip):
        result["components"]["skills"] = "skipped (upgrade_skip_files)"
    else:
        result["components"]["skills"] = generate_skills(project_root, "claude", overwrite=True)

    if _skipped("python_quality_rule", skip):
        result["components"]["python_quality_rule"] = "skipped (upgrade_skip_files)"
    elif not python_ok:
        result["components"]["python_quality_rule"] = {
            "action": "skipped (no python detected)",
            "hint": (
                "Set force_python_quality_rule=true in .tapps-mcp.yaml "
                "to install on non-Python repos."
            ),
        }
    else:
        result["components"]["python_quality_rule"] = generate_claude_python_quality_rule(
            project_root, engagement_level=engagement_level
        )

    # agent-scope.md is universal — applies to any deployed agent regardless of language.
    if _skipped("agent_scope_rule", skip):
        result["components"]["agent_scope_rule"] = "skipped (upgrade_skip_files)"
    else:
        result["components"]["agent_scope_rule"] = generate_claude_agent_scope_rule(project_root)

    if _skipped("pipeline_rule", skip):
        result["components"]["pipeline_rule"] = "skipped (upgrade_skip_files)"
    elif not (python_ok or infra_ok):
        result["components"]["pipeline_rule"] = {
            "action": "skipped (no python or infra detected)",
            "hint": (
                "Set force_python_quality_rule=true, or add a "
                "Dockerfile/docker-compose file, to install."
            ),
        }
    else:
        result["components"]["pipeline_rule"] = generate_claude_pipeline_rule(project_root)


def _upgrade_cursor_live(
    project_root: Path,
    result: dict[str, Any],
    *,
    force: bool,
) -> None:
    """Run live (non-dry-run) artifact upgrades for the cursor host."""
    from tapps_mcp.pipeline.init import _bootstrap_cursor
    from tapps_mcp.pipeline.platform_generators import (
        generate_cursor_hooks,
        generate_cursor_rules,
        generate_skills,
        generate_subagent_definitions,
    )

    result["components"]["cursor_rules"] = _bootstrap_cursor(project_root, overwrite=force)
    hooks_result = generate_cursor_hooks(project_root)
    result["components"]["hooks"] = {
        "scripts_created": hooks_result.get("scripts_created", []),
        "hooks_added": hooks_result.get("hooks_added", 0),
    }
    result["components"]["agents"] = generate_subagent_definitions(
        project_root, "cursor", overwrite=True
    )
    result["components"]["skills"] = generate_skills(project_root, "cursor", overwrite=True)
    result["components"]["cursor_rule_types"] = generate_cursor_rules(project_root)


def _upgrade_platform(
    host: str,
    project_root: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    engagement_level: str = "medium",
    skip_files: set[str] | None = None,
    mcp_only: bool = False,
    force_python_rule: bool = False,
) -> dict[str, Any]:
    """Upgrade platform-specific files for a single host.

    Parameters
    ----------
    mcp_only:
        When True, only the ``.mcp.json`` (when already opted in) and
        ``.claude/settings.json`` permissions merge run.
    force_python_rule:
        When True, skip the Python-language gate and always generate
        ``python-quality.md`` / ``tapps-pipeline.md``.

    Per-artifact skip tokens (via ``skip_files``) are honored independently —
    skipping ``CLAUDE.md`` no longer gates hooks/agents/skills/rules.
    """
    from tapps_mcp.pipeline.init import _bootstrap_claude_settings

    result: dict[str, Any] = {"host": host, "components": {}}
    _skip = skip_files or set()
    python_ok = force_python_rule or _has_python_signals(project_root)
    infra_ok = _has_infra_signals(project_root)

    if _skipped("mcp_config", _skip):
        result["components"]["mcp_config"] = "skipped (upgrade_skip_files)"
    else:
        _upgrade_mcp_config(host, project_root, result, force=force, dry_run=dry_run, skip=_skip)

    if mcp_only:
        # Still run settings merge — it's the other half of the "just wire the MCP server in".
        if host == "claude-code" and not dry_run and not _skipped("claude_settings", _skip):
            result["components"]["settings"] = _bootstrap_claude_settings(
                project_root, engagement_level=engagement_level
            )
        result["components"]["mcp_only_skipped"] = {
            "reason": "mcp_only=True",
            "skipped": [
                "claude_md", "hooks", "agents", "skills",
                "python_quality_rule", "agent_scope_rule", "pipeline_rule", "cursor_rules",
            ],
        }
        return result

    if host == "claude-code":
        if dry_run:
            _upgrade_claude_code_dry_run(
                result, force=force, python_ok=python_ok, infra_ok=infra_ok
            )
        else:
            _upgrade_claude_code_live(
                project_root, result,
                force=force, engagement_level=engagement_level,
                skip=_skip, python_ok=python_ok, infra_ok=infra_ok,
            )
    elif host == "cursor":
        if dry_run:
            result["components"]["cursor_rules"] = "would-refresh" if force else "check-needed"
            result["components"]["hooks"] = "would-regenerate"
            result["components"]["agents"] = "would-regenerate"
            result["components"]["skills"] = "would-regenerate"
        else:
            _upgrade_cursor_live(project_root, result, force=force)
    elif host == "vscode":
        result["components"]["note"] = "no platform rules to upgrade"

    return result


def _upgrade_agents_md_content_return(
    project_root: Path,
) -> tuple[FileOperation, dict[str, Any]]:
    """Generate a FileOperation for AGENTS.md upgrade in content-return mode.

    Returns ``(file_op, result_dict)`` with the appropriate mode
    (``"create"`` or ``"merge"``) depending on whether AGENTS.md exists.
    """
    from tapps_mcp.pipeline.agents_md import AgentsValidation, merge_agents_md
    from tapps_mcp.prompts.prompt_loader import load_agents_template

    agents_path = project_root / "AGENTS.md"
    template_content = load_agents_template()

    if not agents_path.exists():
        op = FileOperation(
            path="AGENTS.md",
            content=template_content,
            mode="create",
            description="AGENTS.md — AI assistant workflow and tool reference.",
            priority=1,
        )
        return op, {"action": "created"}

    existing = agents_path.read_text(encoding="utf-8")
    validation = AgentsValidation(existing)

    if validation.is_up_to_date:
        # Still return the file op so the agent has full context
        op = FileOperation(
            path="AGENTS.md",
            content=existing,
            mode="overwrite",
            description="AGENTS.md is already up-to-date (no changes needed).",
            priority=1,
        )
        return op, {"action": "up-to-date"}

    # Smart merge — produce merged content for the agent to write
    merged, changes = merge_agents_md(existing, template_content)
    op = FileOperation(
        path="AGENTS.md",
        content=merged,
        mode="merge",
        description=(
            "AGENTS.md — merged with latest template. "
            "User customizations are preserved; only managed sections updated."
        ),
        priority=1,
    )
    issues: list[str] = []
    if validation.sections_missing:
        issues.append(f"missing sections: {', '.join(validation.sections_missing)}")
    if validation.tools_missing:
        issues.append(f"missing tools: {', '.join(validation.tools_missing)}")
    detail = "; ".join(issues) or "version mismatch"
    return op, {"action": "merged", "detail": detail, "changes": changes}


def _upgrade_platform_content_return(
    host: str,
    project_root: Path,
    *,
    force: bool = False,
    engagement_level: str = "medium",
) -> tuple[list[FileOperation], dict[str, Any]]:
    """Generate FileOperations for platform upgrade in content-return mode.

    Returns ``(file_ops, result_dict)`` with platform-specific file operations.
    """
    from tapps_mcp.prompts.prompt_loader import load_platform_rules

    ops: list[FileOperation] = []
    result: dict[str, Any] = {"host": host, "components": {}}

    if host == "claude-code":
        content = load_platform_rules("claude", engagement_level=engagement_level)
        claude_md_path = project_root / "CLAUDE.md"
        mode = "overwrite" if (claude_md_path.exists() or force) else "create"
        ops.append(
            FileOperation(
                path="CLAUDE.md",
                content=content,
                mode=mode,
                description="Claude Code platform rules with TappsMCP pipeline.",
                priority=2,
            )
        )
        result["components"]["claude_md"] = "content_return"

    elif host == "cursor":
        content = load_platform_rules("cursor", engagement_level=engagement_level)
        cursor_path = project_root / ".cursor" / "rules" / "tapps-pipeline.md"
        mode = "overwrite" if (cursor_path.exists() or force) else "create"
        ops.append(
            FileOperation(
                path=".cursor/rules/tapps-pipeline.md",
                content=content,
                mode=mode,
                description="Cursor platform rules with TappsMCP pipeline.",
                priority=2,
            )
        )
        result["components"]["cursor_rules"] = "content_return"

    elif host == "vscode":
        result["components"]["note"] = "no platform rules to upgrade"

    # Hooks, skills, agents, CI are skipped in content-return mode
    result["components"]["generators_skipped"] = {
        "reason": "content_return",
        "skipped": ["hooks", "skills", "agents", "mcp_config", "settings"],
        "hint": "Run 'tapps_upgrade' locally to generate these components.",
    }

    return ops, result


def _build_upgrade_manifest(
    file_ops: list[FileOperation],
    version: str,
) -> FileManifest:
    """Build a :class:`FileManifest` for the upgrade pipeline."""
    return FileManifest(
        summary=(f"TappsMCP upgrade v{version}: {len(file_ops)} file(s) to write"),
        source_version=version,
        files=file_ops,
        agent_instructions=AgentInstructions(
            persona=(
                "You are a project upgrade assistant updating TappsMCP "
                "scaffolding to the latest version.  Write each file "
                "exactly as provided — do not modify content, add "
                "comments, or reformat."
            ),
            tool_preference=(
                "Use Write for files with mode 'create' or 'overwrite'.  "
                "For files with mode 'merge', read the existing file first, "
                "then replace the entire content with the merged version "
                "provided (merge has already been computed)."
            ),
            verification_steps=[
                "After writing all files, run 'git diff' to review changes.",
                "Verify AGENTS.md exists and has the expected sections.",
                "Check that no user customizations were lost in merged files.",
                "Run 'git status' to show the user what changed.",
            ],
            warnings=[
                "Backup your project before applying (git stash or git commit).",
                "AGENTS.md merge preserves user customizations — review the diff.",
                "Hooks, skills, and agents are not included — run "
                "'tapps_upgrade' locally to generate those.",
            ],
        ),
    )


def _upgrade_content_return(
    project_root: Path,
    *,
    platform: str = "",
    force: bool = False,
) -> dict[str, Any]:
    """Run upgrade pipeline in content-return mode (Epic 87.3).

    Instead of writing files, accumulates :class:`FileOperation` objects
    and returns a :class:`FileManifest` the AI client can apply.
    """
    from tapps_core.config.settings import load_settings
    from tapps_mcp import __version__

    file_ops: list[FileOperation] = []
    result: dict[str, Any] = {
        "version": __version__,
        "dry_run": False,
        "content_return": True,
        "components": {},
        "errors": [],
    }

    # AGENTS.md
    try:
        agents_op, agents_result = _upgrade_agents_md_content_return(project_root)
        file_ops.append(agents_op)
        result["components"]["agents_md"] = agents_result
    except Exception as exc:
        result["errors"].append(f"AGENTS.md: {exc}")
        result["components"]["agents_md"] = {"action": "error", "detail": str(exc)}

    # Detect platform
    detected = platform or _detect_platform(project_root)
    result["detected_platform"] = detected

    hosts: list[str] = []
    if detected in ("claude", "both"):
        hosts.append("claude-code")
    if detected in ("cursor", "both"):
        hosts.append("cursor")

    settings = load_settings(project_root=project_root)
    engagement_level = settings.llm_engagement_level

    # Per-host platform files
    platform_results: list[dict[str, Any]] = []
    for host in hosts:
        try:
            host_ops, host_result = _upgrade_platform_content_return(
                host,
                project_root,
                force=force,
                engagement_level=engagement_level,
            )
            file_ops.extend(host_ops)
            platform_results.append(host_result)
        except Exception as exc:
            result["errors"].append(f"{host}: {exc}")
            platform_results.append({"host": host, "error": str(exc)})

    result["components"]["platforms"] = platform_results

    # GitHub artifacts skipped in content-return mode
    for component in ("ci_workflows", "github_copilot", "github_templates", "governance"):
        result["components"][component] = {"action": "skipped", "reason": "content_return"}

    # Build manifest
    manifest = _build_upgrade_manifest(file_ops, __version__)
    result["file_manifest"] = manifest.to_full_response_data()
    result["success"] = len(result["errors"]) == 0

    return result


def _detect_platform(project_root: Path) -> str:
    """Detect the platform from existing config files."""
    claude_dir = project_root / ".claude"
    cursor_dir = project_root / ".cursor"

    # Check for Claude Code config indicators
    has_claude = claude_dir.is_dir() or (project_root / "CLAUDE.md").exists()
    has_cursor = cursor_dir.is_dir()

    if has_claude and has_cursor:
        return "both"
    if has_claude:
        return "claude"
    if has_cursor:
        return "cursor"
    return ""


def _run_github_artifacts(project_root: Path, result: dict[str, Any]) -> None:
    """Run GitHub-hosted artifact generators (CI, Copilot, templates, governance).

    Each generator is called independently; failures are recorded in
    ``result["errors"]`` rather than aborting the whole upgrade.
    """
    try:
        from tapps_mcp.pipeline.github_ci import generate_all_ci_workflows

        result["components"]["ci_workflows"] = generate_all_ci_workflows(project_root)
    except (OSError, ValueError) as exc:
        log.exception("ci_workflows_failed")
        result["errors"].append(f"CI workflows: {exc}")

    try:
        from tapps_mcp.pipeline.github_copilot import generate_all_copilot_config

        result["components"]["github_copilot"] = generate_all_copilot_config(project_root)
    except (OSError, ValueError) as exc:
        log.exception("copilot_config_failed")
        result["errors"].append(f"Copilot config: {exc}")

    try:
        from tapps_mcp.pipeline.github_templates import generate_all_github_templates

        result["components"]["github_templates"] = generate_all_github_templates(project_root)
    except (OSError, ValueError) as exc:
        log.exception("github_templates_failed")
        result["errors"].append(f"GitHub templates: {exc}")

    try:
        from tapps_mcp.pipeline.github_governance import generate_all_governance

        result["components"]["governance"] = generate_all_governance(project_root)
    except (OSError, ValueError) as exc:
        log.exception("governance_failed")
        result["errors"].append(f"Governance: {exc}")


def _collect_upgrade_targets(project_root: Path) -> list[Path]:
    """Collect files that upgrade_pipeline will overwrite."""
    targets: list[Path] = []
    candidates = [
        project_root / "AGENTS.md",
        project_root / "CLAUDE.md",
        project_root / ".claude" / "settings.json",
        project_root / ".cursor" / "rules" / "tapps-pipeline.md",
        # Docker-related config files (Epic 46)
        project_root / ".tapps-mcp.yaml",
    ]
    # Hook scripts
    hooks_dir = project_root / ".claude" / "hooks"
    if hooks_dir.is_dir():
        for f in hooks_dir.iterdir():
            if f.name.startswith("tapps-"):
                targets.append(f)
    # Skills
    skills_dir = project_root / ".claude" / "skills"
    if skills_dir.is_dir():
        for f in skills_dir.iterdir():
            if f.is_dir() and f.name.startswith("tapps-"):
                skill_file = f / "SKILL.md"
                if skill_file.exists():
                    targets.append(skill_file)
    # Agents
    agents_dir = project_root / ".claude" / "agents"
    if agents_dir.is_dir():
        for f in agents_dir.iterdir():
            if f.name.startswith("tapps-"):
                targets.append(f)
    for c in candidates:
        if c.exists():
            targets.append(c)
    return targets


def upgrade_pipeline(
    project_root: Path,
    *,
    platform: str = "",
    force: bool = False,
    dry_run: bool = False,
    mcp_only: bool = False,
) -> dict[str, Any]:
    """Upgrade all TappsMCP-generated files in a project.

    This is the core function called by the ``tapps_upgrade`` MCP tool.
    It uses ``upgrade_mode=True`` internally so custom command paths
    (e.g. PyInstaller exe) are never overwritten.

    Args:
        project_root: Project root directory.
        platform: ``"claude"``, ``"cursor"``, ``"both"``, or ``""`` for
            auto-detection.
        force: If ``True``, overwrite all generated files.
        dry_run: If ``True``, report what would change without writing.
        mcp_only: If ``True``, perform a narrow install — only the
            ``.mcp.json`` merge (when already opted in) and
            ``.claude/settings.json`` permissions merge. Every other
            artifact (CLAUDE.md, AGENTS.md, hooks, rules, agents, skills,
            Karpathy block, GitHub workflows, governance) is skipped.
            Intended for publisher/non-greenfield consumers who just want
            the MCP server wired in.

    Returns:
        Structured dict with per-component upgrade results.
    """
    from tapps_mcp import __version__

    log.info(
        "upgrade_pipeline",
        project_root=str(project_root),
        platform=platform,
        force=force,
        dry_run=dry_run,
        mcp_only=mcp_only,
    )

    # Epic 87: Detect write mode (content-return for Docker/read-only)
    write_mode = WriteMode.DIRECT_WRITE if dry_run else detect_write_mode(project_root)
    content_return = write_mode == WriteMode.CONTENT_RETURN

    if content_return:
        log.info(
            "content_return_mode",
            project_root=str(project_root),
            reason="read-only filesystem or TAPPS_WRITE_MODE=content",
        )
        return _upgrade_content_return(
            project_root,
            platform=platform,
            force=force,
        )

    result: dict[str, Any] = {
        "version": __version__,
        "dry_run": dry_run,
        "components": {},
        "errors": [],
    }

    # Pre-upgrade backup (skip in dry-run mode)
    if not dry_run:
        try:
            from tapps_mcp.distribution.rollback import BackupManager

            mgr = BackupManager(project_root)
            backup_targets = _collect_upgrade_targets(project_root)
            if backup_targets:
                backup_dir = mgr.create_backup(
                    backup_targets,
                    reason="pre-upgrade backup",
                    version=__version__,
                )
                result["backup"] = str(backup_dir)
                mgr.cleanup_old_backups(keep=5)
            else:
                result["backup"] = "skipped (no targets)"
        except Exception as exc:
            log.error("backup_failed", error=str(exc))
            result["backup"] = f"failed: {exc}"
            result["errors"].append(
                f"Upgrade aborted: backup failed ({exc}). "
                "Fix the backup issue or run with dry_run=True to preview changes."
            )
            return result

    # Resolve engagement level and Docker config from settings. Pass the
    # target project_root explicitly so the per-project ``.tapps-mcp.yaml``
    # (not this process's CWD) is what drives upgrade knobs like
    # ``upgrade_skip_files``.
    from tapps_core.config.settings import load_settings

    settings = load_settings(project_root=project_root)

    # Load skip list from settings (Issue #86)
    skip_files: set[str] = set(settings.upgrade_skip_files)
    if skip_files:
        result["skipped_files"] = sorted(skip_files)
        unknown = sorted(skip_files - _ALL_SKIP_TOKENS)
        if unknown:
            result["unknown_skip_tokens"] = unknown

    # AGENTS.md (platform-independent) — merge-first, with sentinel / config
    # opt-out for greenfield creation only.
    if mcp_only:
        result["components"]["agents_md"] = {"action": "skipped (mcp_only)"}
    elif _skipped("agents_md", skip_files):
        result["components"]["agents_md"] = {"action": "skipped (upgrade_skip_files)"}
    else:
        try:
            agents_result = _upgrade_agents_md(
                project_root,
                dry_run=dry_run,
                create_agents_md=settings.upgrade_create_agents_md,
            )
            result["components"]["agents_md"] = agents_result
        except Exception as exc:
            result["errors"].append(f"AGENTS.md: {exc}")
            result["components"]["agents_md"] = {"action": "error", "detail": str(exc)}

    # Detect platform if not specified
    detected = platform or _detect_platform(project_root)
    result["detected_platform"] = detected

    hosts: list[str] = []
    if detected in ("claude", "both"):
        hosts.append("claude-code")
    if detected in ("cursor", "both"):
        hosts.append("cursor")

    engagement_level = settings.llm_engagement_level

    # Per-host upgrades
    platform_results: list[dict[str, Any]] = []
    for host in hosts:
        try:
            host_result = _upgrade_platform(
                host,
                project_root,
                force=force,
                dry_run=dry_run,
                engagement_level=engagement_level,
                skip_files=skip_files,
                mcp_only=mcp_only,
                force_python_rule=settings.force_python_quality_rule,
            )
            platform_results.append(host_result)
        except Exception as exc:
            result["errors"].append(f"{host}: {exc}")
            platform_results.append(
                {
                    "host": host,
                    "error": str(exc),
                }
            )

    result["components"]["platforms"] = platform_results

    # Karpathy guidelines block — refresh in AGENTS.md and CLAUDE.md after
    # per-host upgrades have potentially created/updated CLAUDE.md. Opt-out
    # never strips existing blocks.
    if mcp_only:
        result["components"]["karpathy_guidelines"] = {"action": "skipped (mcp_only)"}
    else:
        try:
            result["components"]["karpathy_guidelines"] = _refresh_karpathy_blocks(
                project_root,
                dry_run=dry_run,
                include_karpathy=settings.include_karpathy_guidelines,
                skip_files=skip_files,
            )
        except Exception as exc:
            result["errors"].append(f"Karpathy guidelines: {exc}")
            result["components"]["karpathy_guidelines"] = {"action": "error", "detail": str(exc)}

    # GitHub templates, CI, Copilot, governance, and issue/PR templates (platform-agnostic)
    if mcp_only:
        for component in ("ci_workflows", "github_copilot", "github_templates", "governance"):
            result["components"][component] = {"action": "skipped (mcp_only)"}
    elif not dry_run:
        _run_github_artifacts(project_root, result)
    else:
        result["components"]["ci_workflows"] = {"action": "would-regenerate"}
        result["components"]["github_copilot"] = {"action": "would-regenerate"}
        result["components"]["github_templates"] = {"action": "would-regenerate"}
        result["components"]["governance"] = {"action": "would-regenerate"}

    result["success"] = len(result["errors"]) == 0
    result["consumer_requirements"] = "docs/TAPPS_MCP_REQUIREMENTS.md"

    return result
