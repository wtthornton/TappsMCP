"""Helper functions for DocsMCP server — response builders and singleton caches."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from docs_mcp.config.settings import DocsMCPSettings


# ---------------------------------------------------------------------------
# Filename slugification (TAP-1413).
# ---------------------------------------------------------------------------


def safe_slug(text: str, *, max_length: int = 60) -> str:
    """Return a filesystem-safe slug for ``text``.

    Strips diacritics, lowercases, replaces every non ``[a-z0-9-]`` character
    with ``-``, collapses runs of ``-``, trims leading/trailing ``-`` and caps
    length at ``max_length``. Guarantees the result is a single path segment
    (no ``/``, ``:``, ``;``, ``.``, etc.) safe to embed in a filename.
    """
    normalised = unicodedata.normalize("NFKD", text)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    replaced = re.sub(r"[^a-z0-9-]+", "-", lowered)
    collapsed = re.sub(r"-+", "-", replaced).strip("-")
    if max_length > 0:
        collapsed = collapsed[:max_length].rstrip("-")
    return collapsed

if TYPE_CHECKING:
    from docs_mcp.validators.style import StyleChecker


# ---------------------------------------------------------------------------
# Settings singleton — avoids re-loading on every tool call.
# ---------------------------------------------------------------------------

_settings: DocsMCPSettings | None = None


def _get_settings() -> DocsMCPSettings:
    """Return a lazily-initialized :class:`DocsMCPSettings` singleton."""
    global _settings
    if _settings is None:
        from docs_mcp.config.settings import load_docs_settings

        _settings = load_docs_settings()
    return _settings


def _reset_settings_cache() -> None:
    """Reset the cached :class:`DocsMCPSettings` singleton (for testing)."""
    global _settings
    _settings = None


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def error_response(
    tool_name: str,
    code: str,
    message: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standard error response envelope.

    Args:
        tool_name: Name of the tool that produced the error.
        code: Machine-readable error code (e.g. ``"NO_FILES_FOUND"``).
        message: Human-readable error description.
        extra: Optional structured metadata merged into the error object.
    """
    error: dict[str, Any] = {"code": code, "message": message}
    if extra:
        error.update(extra)
    return {
        "tool": tool_name,
        "success": False,
        "elapsed_ms": 0,
        "error": error,
    }


_SENTINEL = object()


def success_response(
    tool_name: str,
    elapsed_ms: int,
    data: dict[str, Any],
    *,
    degraded: bool | object = _SENTINEL,
    next_steps: list[str] | None = None,
) -> dict[str, Any]:
    """Build a standard success response envelope.

    When *degraded* is explicitly passed (even as False), the key is included
    in the response.  When omitted, the key is absent.

    When *next_steps* is non-empty, it is included in ``data`` so the LLM
    sees actionable guidance.
    """
    if next_steps:
        data["next_steps"] = next_steps

    result: dict[str, Any] = {
        "tool": tool_name,
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": data,
    }
    if degraded is not _SENTINEL:
        result["degraded"] = degraded
    return result


# ---------------------------------------------------------------------------
# Content-return mode helpers (Epic 87)
# ---------------------------------------------------------------------------


def can_write_to_project(root: Path) -> bool:
    """Whether generators should write files directly.

    Returns ``False`` in content-return mode (Docker / read-only filesystem),
    meaning generators should skip file writes and let the AI client apply
    the content from the response.
    """
    from tapps_core.common.file_operations import WriteMode, detect_write_mode

    return detect_write_mode(root) == WriteMode.DIRECT_WRITE


def build_generator_manifest(
    tool_name: str,
    content: str,
    output_path: str,
    *,
    description: str = "",
) -> dict[str, Any]:
    """Build a ``file_manifest`` dict for a generator in content-return mode.

    Generators embed this in their ``data`` dict so the AI client knows
    exactly where and how to write the file.
    """
    from tapps_core.common.file_operations import (
        AgentInstructions,
        FileManifest,
        FileOperation,
    )

    # Tool-specific personas
    personas: dict[str, str] = {
        "docs_generate_readme": "Technical writer creating project README.",
        "docs_generate_changelog": "Release manager updating changelog.",
        "docs_generate_release_notes": "Release manager preparing release notes.",
        "docs_generate_api": "API documentation specialist.",
        "docs_generate_adr": "Architecture decision recorder.",
        "docs_generate_onboarding": "Onboarding guide author.",
        "docs_generate_contributing": "Contributing guide author.",
        "docs_generate_prd": "Product requirements author.",
        "docs_generate_diagram": "Diagram generator.",
        "docs_generate_architecture": "Architecture documentation specialist.",
        "docs_generate_epic": "Project planning specialist creating epics.",
        "docs_generate_story": "Project planning specialist creating stories.",
        "docs_generate_prompt": "Prompt template author.",
    }
    persona = personas.get(
        tool_name,
        "Documentation generator writing files for the project.",
    )

    manifest = FileManifest(
        summary=f"{tool_name}: 1 file to write",
        source_version=_get_docsmcp_version(),
        files=[
            FileOperation(
                path=output_path,
                content=content,
                mode="create",
                description=description or f"Generated by {tool_name}.",
                priority=5,
            ),
        ],
        agent_instructions=AgentInstructions(
            persona=(
                f"You are a {persona}  Write the file exactly as "
                "provided — do not modify content, add comments, or reformat."
            ),
            tool_preference=(
                "Use the Write tool to create the file.  Create parent directories as needed."
            ),
            verification_steps=[
                f"Verify the file was written to {output_path}.",
                "Run 'git status' to show the user what changed.",
            ],
            warnings=[],
        ),
    )
    return manifest.to_full_response_data()


def _get_docsmcp_version() -> str:
    """Return DocsMCP version string."""
    try:
        from docs_mcp import __version__

        return __version__
    except (ImportError, AttributeError):
        return "unknown"


# ---------------------------------------------------------------------------
# Three-tier output helper (write-first / inline / manifest)
# ---------------------------------------------------------------------------

_INLINE_THRESHOLD = 20_000  # 20K chars


def _count_sections(content: str) -> int:
    """Count markdown heading sections in content."""
    count = 0
    if content.startswith("# "):
        count += 1
    count += content.count("\n# ")
    count += content.count("\n## ")
    return count


async def finalize_output(
    tool_name: str,
    content: str,
    output_path: str,
    root: Path,
    *,
    description: str = "",
    write_to_disk: bool = True,
) -> dict[str, Any]:
    """Three-tier output handler for generator tools.

    **Tier 1 — write-first** (writable filesystem and ``write_to_disk=True``):
    write to disk, return summary only (path, size, section_count). Never
    includes ``content``.

    **Tier 2 — inline** (read-only or ``write_to_disk=False``, content
    < 20 K chars): return content directly in the response.

    **Tier 3 — manifest** (read-only or ``write_to_disk=False``,
    content >= 20 K chars): return a ``FileManifest`` so the AI client can
    apply the file.

    Returns a dict fragment to **merge** into the tool's ``data`` dict.
    If a write error occurs the returned dict is a full ``error_response``
    (has ``"success": False``).
    """
    fragment: dict[str, Any] = {
        "output_path": output_path,
        "content_length": len(content),
    }

    # Section count is meaningful for markdown, not HTML
    if not output_path.endswith((".html", ".htm", ".txt")):
        fragment["section_count"] = _count_sections(content)

    if write_to_disk and can_write_to_project(root):
        # Tier 1: write to disk, return metadata only
        try:
            from tapps_core.security.path_validator import PathValidator

            validator = PathValidator(root)
            write_path = validator.validate_write_path(output_path)
            write_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
            # Use validator.project_root (always resolved) rather than the
            # raw root parameter (which may be a relative Path). TAP-1079:
            # passing a relative root crashes Path.relative_to() with
            # "is not in the subpath of '.'".
            fragment["written_to"] = str(
                write_path.relative_to(validator.project_root)
            ).replace("\\", "/")
        except (ValueError, FileNotFoundError, OSError) as exc:
            return error_response(tool_name, "WRITE_ERROR", f"Failed to write: {exc}")
    elif len(content) < _INLINE_THRESHOLD:
        # Tier 2: small content, inline it
        fragment["content"] = content
    else:
        # Tier 3: large content, use FileManifest
        fragment["content_return"] = True
        fragment["file_manifest"] = build_generator_manifest(
            tool_name,
            content,
            output_path,
            description=description,
        )

    return fragment


def build_custom_terms_for_style(
    project_root: Path,
    settings: DocsMCPSettings,
    *,
    extra_terms: list[str] | None = None,
) -> list[str]:
    """Merge manual terms, ``.docsmcp-terms.txt``, and optional auto-detected identifiers.

    Order: *extra_terms* (e.g. tool param), ``settings.style_custom_terms``, terms file,
    then :func:`~docs_mcp.validators.identifier_terms.collect_identifier_terms` when
    ``style_auto_detect_terms`` is True. Case-insensitive de-duplication preserves the
    first spelling.
    """
    terms_list: list[str] = []
    seen_lower: set[str] = set()

    def _push(raw: str) -> None:
        t = raw.strip()
        if not t:
            return
        k = t.lower()
        if k in seen_lower:
            return
        seen_lower.add(k)
        terms_list.append(t)

    if extra_terms:
        for t in extra_terms:
            _push(t)
    raw_custom = getattr(settings, "style_custom_terms", None) or []
    if not isinstance(raw_custom, list):
        raw_custom = []
    for t in raw_custom:
        _push(str(t))

    terms_file = project_root / ".docsmcp-terms.txt"
    if terms_file.is_file():
        try:
            for line in terms_file.read_text(encoding="utf-8").splitlines():
                term = line.strip()
                if term and not term.startswith("#"):
                    _push(term)
        except OSError:
            pass

    # Use ``is True`` so MagicMock defaults do not accidentally enable scanning.
    if getattr(settings, "style_auto_detect_terms", False) is True:
        from docs_mcp.validators.identifier_terms import collect_identifier_terms

        mf_raw = getattr(settings, "style_auto_detect_max_files", 120)
        mt_raw = getattr(settings, "style_auto_detect_max_terms", 80)
        mf = int(mf_raw) if isinstance(mf_raw, int) else 120
        mt = int(mt_raw) if isinstance(mt_raw, int) else 80
        mf = max(1, min(mf, 500))
        mt = max(1, min(mt, 200))
        for t in collect_identifier_terms(project_root, max_files=mf, max_terms=mt):
            _push(t)

    return terms_list


def build_style_checker_for_project(
    project_root: Path,
    settings: DocsMCPSettings,
) -> StyleChecker:
    """Build a :class:`~docs_mcp.validators.style.StyleChecker` from project settings."""
    from docs_mcp.validators.style import StyleChecker, StyleConfig

    terms_list = build_custom_terms_for_style(project_root, settings)

    config = StyleConfig(
        enabled_rules=list(settings.style_enabled_rules),
        heading_style=settings.style_heading,
        max_sentence_words=settings.style_max_sentence_words,
        custom_terms=terms_list,
        jargon_terms=list(settings.style_jargon_terms),
    )
    return StyleChecker(config)
