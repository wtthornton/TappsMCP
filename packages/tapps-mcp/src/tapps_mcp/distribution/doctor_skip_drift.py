"""Doctor check: content drift on ``upgrade_skip_files`` entries (TAP-6600).

Split out of :mod:`tapps_mcp.distribution.doctor_platform` — that module owns
skip-*vocabulary* validity (:func:`~tapps_mcp.distribution.doctor_platform.check_upgrade_skip_tokens`,
TAP-6499), a different and already-large concern; this one owns
skip-*content* drift.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tapps_mcp.distribution.doctor_platform import _upgrade_skip_tokens
from tapps_mcp.distribution.doctor_result import CheckResult

# Recognized-token -> generator function name for the single-file ``.claude/rules/*.md``
# artifacts. Each generator writes exactly one file, taking either only
# ``project_root`` or ``project_root, engagement_level=...``, which is also
# the reason this drift check is scoped to just these ten tokens: a
# directory token (``claude_skills``, ``claude_hooks``, ...) or a generator
# with other required inputs (``agents_md``, ``tech_stack_md``,
# ``mcp_config``, ...) has no single honest "shadow render" to diff against
# without dragging in that generator's whole call graph. Those report
# ``unsupported`` below rather than a guessed verdict.
_DRIFT_CHECKABLE_RULE_GENERATORS: dict[str, str] = {
    "python_quality_rule": "generate_claude_python_quality_rule",
    "agent_scope_rule": "generate_claude_agent_scope_rule",
    "agent_to_agent_rule": "generate_claude_agent_to_agent_rule",
    "autonomy_rule": "generate_claude_autonomy_rule",
    "linear_standards_rule": "generate_claude_linear_standards_rule",
    "integration_hygiene_rule": "generate_claude_integration_hygiene_rule",
    "pipeline_rule": "generate_claude_pipeline_rule",
    "security_rule": "generate_claude_security_rule",
    "test_quality_rule": "generate_claude_test_quality_rule",
    "config_files_rule": "generate_claude_config_files_rule",
}


def _shadow_render_skip_key(skip_key: str, rel_path: str, engagement_level: str) -> str | None:
    """Render *skip_key*'s canonical content into a scratch dir; return it, or None.

    Calls the real generator — the same code ``tapps_upgrade`` would run — so
    this can never drift from the mechanism it is checking. Writes only
    inside a throwaway ``TemporaryDirectory``; the project tree is never
    touched.
    """
    fn_name = _DRIFT_CHECKABLE_RULE_GENERATORS.get(skip_key)
    if fn_name is None:
        return None
    from tapps_mcp.pipeline import platform_bundles

    generate = getattr(platform_bundles, fn_name)
    with tempfile.TemporaryDirectory() as tmp_dir:
        scratch = Path(tmp_dir)
        if skip_key == "python_quality_rule":
            generate(scratch, engagement_level=engagement_level)
        else:
            generate(scratch)
        rendered_path = scratch / rel_path
        if not rendered_path.exists():
            return None
        return rendered_path.read_text(encoding="utf-8")


def check_upgrade_skip_token_drift(project_root: Path) -> CheckResult:
    """Report identical/diverged/missing/unsupported for each applied skip token.

    ``upgrade_skip_files`` protects local edits from ``tapps_upgrade`` — and,
    silently and permanently, also stops that path from ever receiving
    upstream improvements. Only the first half was visible before this check.
    A skip entry might be a complete no-op (byte-identical to what would
    ship, so removing it costs nothing) or genuinely diverged; nothing said
    which. This check never writes to the project and never blocks — drift
    is reported (``severity="warn"``), not enforced, matching the epic's
    explicit non-goal of silently overwriting a deliberately frozen file.
    """
    from tapps_mcp.distribution.doctor_telemetry import _read_engagement_level
    from tapps_mcp.pipeline.upgrade_skip_tokens import SKIP_TOKENS, applied_skip_tokens

    configured = _upgrade_skip_tokens(project_root)
    applied = applied_skip_tokens(configured)
    if not applied:
        return CheckResult("upgrade_skip_files drift", True, "no recognized skip tokens configured")

    engagement_level = _read_engagement_level(project_root) or "medium"

    # applied_skip_tokens returns the matched *paths* (SKIP_TOKENS' values),
    # not its keys — invert once to recover which token/generator owns each.
    path_to_token = {path: t for t, paths in SKIP_TOKENS.items() for path in paths}

    identical: list[str] = []
    diverged: list[str] = []
    missing: list[str] = []
    unsupported: list[str] = []

    for rel_path in sorted(applied):
        skip_key = path_to_token.get(rel_path)
        target = project_root / rel_path
        if not target.exists():
            missing.append(rel_path)
            continue
        if target.is_dir() or skip_key not in _DRIFT_CHECKABLE_RULE_GENERATORS:
            unsupported.append(rel_path)
            continue
        rendered = _shadow_render_skip_key(skip_key, rel_path, engagement_level)
        if rendered is None:
            unsupported.append(rel_path)
            continue
        if target.read_text(encoding="utf-8") == rendered:
            identical.append(rel_path)
        else:
            diverged.append(rel_path)

    parts = []
    if identical:
        parts.append(
            f"{len(identical)} identical (skip is a no-op, safe to remove): {', '.join(identical)}"
        )
    if diverged:
        parts.append(f"{len(diverged)} diverged from what would ship: {', '.join(diverged)}")
    if missing:
        parts.append(
            f"{len(missing)} entry/entries point at a path that no longer exists: {', '.join(missing)}"
        )
    if unsupported:
        parts.append(
            f"{len(unsupported)} not yet drift-checkable (directory or multi-input token): "
            f"{', '.join(unsupported)}"
        )

    problem = bool(diverged or missing)
    return CheckResult(
        "upgrade_skip_files drift",
        not problem,
        "; ".join(parts) if parts else "no per-file skip entries to check",
        "" if not problem else "Review the diverged/missing entries above; nothing was changed.",
        severity="warn" if problem else "pass",
    )


__all__ = ["check_upgrade_skip_token_drift"]
