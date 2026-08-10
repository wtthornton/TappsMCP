"""Server verification, checker installation, and cache warming.

Split out of :mod:`~tapps_mcp.pipeline.init` (TAP-5733).

``_verify_server`` deliberately stays in ``init`` rather than moving here:
tests patch ``tapps_mcp.pipeline.init._run_server_verification``, which only
takes effect if the calling function resolves that name from ``init``'s own
module globals.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.pipeline.init_state import BootstrapConfig, _BootstrapState

# Allowlist of packages that _run_server_verification may pip-install.
# install_hints come from hardcoded CHECKER_SPECS in tool_detection.py;
# this allowlist is defence-in-depth against unexpected hint values.
_ALLOWED_CHECKER_PACKAGES = {
    "ruff",
    "mypy",
    "bandit",
    "radon",
    "vulture",
    "pip-audit",
    "pylint",
    "perflint",
}


def _warm_caches(cfg: BootstrapConfig, state: _BootstrapState) -> None:
    """Warm Context7 cache and expert RAG indices."""
    if cfg.warm_cache_from_tech_stack and state.profile is not None:
        cache_result = _run_cache_warming(
            state.project_root,
            state.profile.tech_stack.context7_priority,
        )
        state.result["cache_warming"] = cache_result
        if cache_result.get("skipped") == "no_api_key":
            warning = (
                "Cache warming skipped: CONTEXT7_API_KEY not set. "
                "Add it to your MCP server env config for documentation lookup."
            )
            cache_result["warning"] = warning
            state.warnings.append(warning)
        if cache_result.get("error"):
            state.errors.append(f"Cache warming failed: {cache_result['error']}")
    else:
        state.result["cache_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": "disabled" if not cfg.warm_cache_from_tech_stack else "profile_failed",
            "libraries": [],
        }

    if cfg.warm_expert_rag_from_tech_stack and state.profile is not None:
        rag_result = _run_expert_rag_warming()
        state.result["expert_rag_warming"] = rag_result
        failed = rag_result.get("failed_domains") or []
        if failed:
            state.errors.append(f"Expert RAG failed for domains: {', '.join(failed)}")
    else:
        state.result["expert_rag_warming"] = {
            "warmed": 0,
            "attempted": 0,
            "skipped": "disabled" if not cfg.warm_expert_rag_from_tech_stack else "profile_failed",
            "domains": [],
        }


def _extract_pip_package(hint: str) -> str | None:
    """Extract package name from a 'pip install X' hint, or None if not allowed."""
    if not hint or not hint.startswith("pip install "):
        return None
    pkg = hint.replace("pip install ", "").strip()
    if pkg not in _ALLOWED_CHECKER_PACKAGES:
        return None
    return pkg


def _install_missing_checkers(
    install_hints: list[str],
    project_root: Path,
) -> None:
    """Attempt to pip-install allowed missing checker packages."""
    import contextlib
    import subprocess
    import sys

    for hint in install_hints:
        pkg = _extract_pip_package(hint)
        if pkg is not None:
            with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError, OSError):
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", pkg],
                    capture_output=True,
                    timeout=60,
                    check=False,
                    cwd=project_root,
                )


def _build_verification_result(installed: list[Any]) -> dict[str, Any]:
    """Build verification result dict from tool detection output."""
    missing = [t for t in installed if not t.available]
    return {
        "ok": len(missing) == 0,
        "missing_checkers": [t.name for t in missing],
        "installed": [t.name for t in installed if t.available],
        "install_hints": [t.install_hint for t in missing if t.install_hint],
        "checker_install_attempted": False,
    }


def _run_server_verification(
    project_root: Path,
    *,
    install_missing: bool = False,
) -> dict[str, Any]:
    """Verify server info and optionally install missing checkers."""
    from tapps_mcp.tools.tool_detection import detect_installed_tools

    installed = detect_installed_tools()
    result = _build_verification_result(installed)

    if install_missing and result["missing_checkers"]:
        result["checker_install_attempted"] = True
        _install_missing_checkers(result["install_hints"], project_root)

        # Reset cache so re-detection actually probes for newly installed tools
        from tapps_mcp.tools.tool_detection import _reset_tools_cache

        _reset_tools_cache()
        installed_after = detect_installed_tools()
        result.update(_build_verification_result(installed_after))
        result["checker_install_attempted"] = True

    return result


def _run_cache_warming(
    project_root: Path,
    libraries: list[str],
) -> dict[str, Any]:
    """Run cache warming for libraries from tech stack.

    Normally called from a worker thread (via ``asyncio.to_thread`` in
    ``tapps_init``), so ``asyncio.run()`` is safe.  The ``RuntimeError``
    guard handles the edge case where this is called from an already-
    running event loop.
    """
    import asyncio

    import structlog

    from tapps_core.config.settings import load_settings
    from tapps_core.knowledge.cache import KBCache
    from tapps_core.knowledge.warming import warm_cache

    logger = structlog.get_logger(__name__)

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
    cache = KBCache(cache_dir, max_mb=settings.cache_max_mb)

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
    except RuntimeError as exc:
        # asyncio.run() raises RuntimeError when called from an already-
        # running event loop.  This should not happen when the caller uses
        # asyncio.to_thread(), but guard defensively and log a warning.
        warmed = 0
        error = f"RuntimeError: {exc}"
        logger.warning(
            "cache_warming_event_loop_conflict",
            error=str(exc),
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


def _run_expert_rag_warming() -> dict[str, Any]:
    """Expert RAG removed (EPIC-94). Returns empty result."""
    return {"status": "removed", "note": "Expert RAG warming removed (EPIC-94)"}
