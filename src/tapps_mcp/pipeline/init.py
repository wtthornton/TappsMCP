"""Bootstrap TAPPS pipeline files in a consuming project."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from tapps_mcp import __version__
from tapps_mcp.project.models import ProjectProfile, TechStack

if TYPE_CHECKING:
    from pathlib import Path

from tapps_mcp.prompts.prompt_loader import (
    load_agents_template,
    load_handoff_template,
    load_platform_rules,
    load_runlog_template,
)


class _SafeWriter(Protocol):
    def __call__(self, rel_path: str, content: str) -> None: ...


def bootstrap_pipeline(
    project_root: Path,
    *,
    create_handoff: bool = True,
    create_runlog: bool = True,
    create_agents_md: bool = True,
    create_tech_stack_md: bool = True,
    platform: str = "",
    verify_server: bool = True,
    install_missing_checkers: bool = False,
    warm_cache_from_tech_stack: bool = True,
    warm_expert_rag_from_tech_stack: bool = True,
    overwrite_platform_rules: bool = False,
    overwrite_agents_md: bool = False,
) -> dict[str, Any]:
    """Create pipeline template files in the project.

    Returns a summary dict with ``created``, ``skipped``, ``errors``, and
    subsystem result dicts (``server_verification``, ``agents_md``,
    ``tech_stack_md``, ``cache_warming``).

    All file writes are validated to stay within *project_root*.
    """
    created: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    result: dict[str, Any] = {}

    project_root = project_root.resolve()

    def _safe_write(rel_path: str, content: str) -> None:
        """Write *content* to *rel_path* under project_root, safely."""
        target = (project_root / rel_path).resolve()
        # Security: ensure target is within project root
        try:
            target.relative_to(project_root)
        except ValueError:
            errors.append(f"{rel_path}: path escapes project root")
            return

        if target.exists():
            skipped.append(rel_path)
            return

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created.append(rel_path)

    def _safe_write_or_overwrite(rel_path: str, content: str) -> str:
        """Write or overwrite content. Returns 'created', 'updated', or 'skipped'."""
        target = (project_root / rel_path).resolve()
        try:
            target.relative_to(project_root)
        except ValueError:
            errors.append(f"{rel_path}: path escapes project root")
            return "skipped"

        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        if existed:
            return "updated"
        created.append(rel_path)
        return "created"

    # Server verification and optional checker installation
    if verify_server or install_missing_checkers:
        result["server_verification"] = _run_server_verification(
            project_root,
            install_missing=install_missing_checkers,
        )
    else:
        result["server_verification"] = {"ok": True, "skipped": True}

    # Project profile (needed for TECH_STACK and cache warming)
    profile = None
    if create_tech_stack_md or warm_cache_from_tech_stack:
        try:
            from tapps_mcp.project.profiler import detect_project_profile

            profile = detect_project_profile(project_root)
        except Exception as exc:
            errors.append(f"Project profile detection failed: {exc}")

    if create_handoff:
        _safe_write("docs/TAPPS_HANDOFF.md", load_handoff_template())

    if create_runlog:
        _safe_write("docs/TAPPS_RUNLOG.md", load_runlog_template())

    # AGENTS.md: create if missing, validate+update if exists
    if create_agents_md:
        agents_path = project_root / "AGENTS.md"
        template_content = load_agents_template()
        if agents_path.exists():
            from tapps_mcp.pipeline.agents_md import update_agents_md

            try:
                action, detail = update_agents_md(
                    agents_path,
                    template_content,
                    overwrite=overwrite_agents_md,
                )
                result["agents_md"] = {"action": action, **detail}
                if action == "validated":
                    skipped.append("AGENTS.md")
            except Exception as exc:
                errors.append(f"AGENTS.md update failed: {exc}")
                result["agents_md"] = {"action": "error", "reason": str(exc)}
        else:
            _safe_write("AGENTS.md", template_content)
            result["agents_md"] = {"action": "created", "version": __version__}
    else:
        result["agents_md"] = {"action": "skipped", "reason": "disabled"}

    # TECH_STACK.md: create or overwrite from project profile
    if create_tech_stack_md and profile is not None:
        tech_stack_content = _render_tech_stack_md(profile)
        action = _safe_write_or_overwrite("TECH_STACK.md", tech_stack_content)
        result["tech_stack_md"] = {"action": action}
    elif create_tech_stack_md and profile is None:
        result["tech_stack_md"] = {"action": "skipped", "reason": "profile_failed"}
        errors.append("Could not create TECH_STACK.md: project profile detection failed")
    else:
        result["tech_stack_md"] = {"action": "skipped", "reason": "disabled"}

    if platform:
        platform_action: str | None = None
        if platform == "claude":
            platform_action = _bootstrap_claude(project_root, overwrite_platform_rules)
            if platform_action == "created":
                created.append("CLAUDE.md")
        elif platform == "cursor":
            platform_action = _bootstrap_cursor(project_root, overwrite_platform_rules)
            if platform_action in {"created", "updated"}:
                created.append(".cursor/rules/tapps-pipeline.md")
            elif platform_action == "skipped":
                skipped.append(".cursor/rules/tapps-pipeline.md")
        else:
            errors.append(f"Unknown platform: {platform!r}. Use 'claude' or 'cursor'.")

        result["platform_rules"] = {
            "platform": platform,
            "action": platform_action or "skipped",
        }

    # Cache warming from tech stack
    if warm_cache_from_tech_stack and profile is not None:
        cache_result = _run_cache_warming(
            project_root,
            profile.tech_stack.context7_priority,
        )
        result["cache_warming"] = cache_result
        if cache_result.get("error"):
            errors.append(f"Cache warming failed: {cache_result['error']}")
    else:
        result["cache_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": "disabled" if not warm_cache_from_tech_stack else "profile_failed",
            "libraries": [],
        }

    # Expert RAG index warming from tech stack
    if warm_expert_rag_from_tech_stack and profile is not None:
        result["expert_rag_warming"] = _run_expert_rag_warming(
            project_root,
            profile.tech_stack,
        )
    else:
        result["expert_rag_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": (
                "disabled" if not warm_expert_rag_from_tech_stack else "profile_failed"
            ),
            "domains": [],
        }

    result["created"] = created
    result["skipped"] = skipped
    result["errors"] = errors
    result["success"] = len(errors) == 0
    return result


def _run_server_verification(
    project_root: Path,
    *,
    install_missing: bool = False,
) -> dict[str, Any]:
    """Verify server info and optionally install missing checkers."""
    from tapps_mcp.tools.tool_detection import detect_installed_tools

    installed = detect_installed_tools()
    missing = [t for t in installed if not t.available]
    missing_names = [t.name for t in missing]
    install_hints = [t.install_hint for t in missing if t.install_hint]

    result: dict[str, Any] = {
        "ok": len(missing) == 0,
        "missing_checkers": missing_names,
        "installed": [t.name for t in installed if t.available],
        "install_hints": install_hints,
        "checker_install_attempted": False,
    }

    if install_missing and missing:
        result["checker_install_attempted"] = True
        import subprocess
        import sys

        import contextlib

        for hint in install_hints:
            if hint and hint.startswith("pip install "):
                pkg = hint.replace("pip install ", "").strip()
                with contextlib.suppress(
                    subprocess.TimeoutExpired, FileNotFoundError, OSError
                ):
                    subprocess.run(
                        [sys.executable, "-m", "pip", "install", pkg],
                        capture_output=True,
                        timeout=60,
                        check=False,
                        cwd=project_root,
                    )

        # Re-detect after install
        installed_after = detect_installed_tools()
        result["ok"] = all(t.available for t in installed_after)
        result["installed"] = [t.name for t in installed_after if t.available]
        result["missing_checkers"] = [t.name for t in installed_after if not t.available]

    return result


def _render_tech_stack_md(profile: ProjectProfile) -> str:
    """Render TECH_STACK.md content from project profile."""
    ts = profile.tech_stack
    lines = [
        "# Tech Stack",
        "",
        "## Project Type",
        f"- **Type:** {profile.project_type or 'unknown'}",
        f"- **Confidence:** {profile.project_type_confidence:.2f}",
        f"- **Reason:** {profile.project_type_reason or 'N/A'}",
        "",
        "## Languages",
    ]
    for lang in ts.languages or ["(none detected)"]:
        lines.append(f"- {lang}")
    lines.extend(["", "## Frameworks"])
    for fw in ts.frameworks or ["(none detected)"]:
        lines.append(f"- {fw}")
    lines.extend(["", "## Libraries"])
    for lib in ts.libraries or ["(none detected)"]:
        lines.append(f"- {lib}")
    lines.extend(["", "## Domains"])
    for d in ts.domains or ["(none detected)"]:
        lines.append(f"- {d}")
    lines.extend(["", "## Context7 Priority (for doc lookups)"])
    for p in ts.context7_priority or []:
        lines.append(f"- {p}")
    ci_str = (
        "Yes (" + ", ".join(profile.ci_systems) + ")"
        if profile.has_ci
        else "No"
    )
    tests_str = (
        "Yes (" + ", ".join(profile.test_frameworks) + ")"
        if profile.has_tests
        else "No"
    )
    lines.extend([
        "",
        "## Infrastructure",
        f"- **CI:** {ci_str}",
        f"- **Docker:** {'Yes' if profile.has_docker else 'No'}",
        f"- **Tests:** {tests_str}",
        f"- **Package managers:** {', '.join(profile.package_managers) or 'N/A'}",
        "",
        "## Recommendations",
    ])
    for rec in profile.quality_recommendations or ["(none)"]:
        lines.append(f"- {rec}")
    lines.append("")
    return "\n".join(lines)


def _run_cache_warming(
    project_root: Path,
    libraries: list[str],
) -> dict[str, Any]:
    """Run cache warming for libraries from tech stack."""
    import asyncio

    from tapps_mcp.config.settings import load_settings
    from tapps_mcp.knowledge.cache import KBCache
    from tapps_mcp.knowledge.warming import warm_cache

    settings = load_settings()
    api_key = settings.context7_api_key

    if not api_key or not api_key.get_secret_value():
        return {
            "warmed": 0,
            "attempted": 0,
            "skipped": "no_api_key",
            "libraries": libraries[:20],
        }

    if not libraries:
        return {
            "warmed": 0,
            "attempted": 0,
            "skipped": "no_libraries",
            "libraries": [],
        }

    cache_dir = project_root / ".tapps-mcp-cache"
    cache = KBCache(cache_dir)

    error: str | None = None
    try:
        warmed = asyncio.run(
            warm_cache(
                project_root,
                cache,
                api_key=api_key,
                libraries=libraries[:20],
                max_libraries=20,
            )
        )
    except Exception as exc:  # pragma: no cover - defensive guardrail
        warmed = 0
        error = f"{type(exc).__name__}: {exc}"

    return {
        "warmed": warmed,
        "attempted": min(len(libraries), 20),
        "skipped": None,
        "error": error,
        "libraries": libraries[:20],
    }


def _run_expert_rag_warming(
    project_root: Path,
    tech_stack: TechStack,
) -> dict[str, Any]:
    """Pre-build expert RAG indices for domains relevant to tech stack."""
    from tapps_mcp.experts.rag_warming import warm_expert_rag_indices

    index_base = project_root / ".tapps-mcp" / "rag_index"
    return warm_expert_rag_indices(
        tech_stack,
        max_domains=10,
        index_base_dir=index_base,
    )


def _bootstrap_claude(
    project_root: Path,
    overwrite: bool = False,
) -> str:
    """Create or update CLAUDE.md with TAPPS pipeline reference.

    Returns ``'created'``, ``'updated'``, or ``'skipped'``.
    """
    claude_md = project_root / "CLAUDE.md"
    content = load_platform_rules("claude")

    if claude_md.exists():
        existing = claude_md.read_text(encoding="utf-8")
        if "TAPPS" in existing and not overwrite:
            # Already has TAPPS reference
            return "skipped"
        # Append to existing file (or refresh content when overwrite=True)
        if overwrite:
            new_content = existing.rstrip() + "\n\n" + content
        else:
            new_content = existing.rstrip() + "\n\n" + content
        claude_md.write_text(new_content, encoding="utf-8")
        return "updated"

    claude_md.write_text(content, encoding="utf-8")
    return "created"


def _bootstrap_cursor(
    project_root: Path,
    overwrite: bool = False,
) -> str:
    """Create or update Cursor pipeline rule file.

    Returns ``'created'``, ``'updated'``, or ``'skipped'``.
    """
    content = load_platform_rules("cursor")
    rules_path = project_root / ".cursor" / "rules" / "tapps-pipeline.md"
    rules_path.parent.mkdir(parents=True, exist_ok=True)

    if rules_path.exists() and not overwrite:
        return "skipped"

    action = "updated" if rules_path.exists() else "created"
    rules_path.write_text(content, encoding="utf-8")
    return action
