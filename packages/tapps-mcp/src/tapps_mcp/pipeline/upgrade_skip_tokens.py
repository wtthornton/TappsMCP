"""Fixed vocabulary for ``upgrade_skip_files`` and validation of configured entries.

``upgrade_skip_files`` is **not** a path glob. Each entry must match one of the
tokens in :data:`SKIP_TOKENS` exactly; anything else is silently inert — the
artifact it looked like it protected gets rewritten on the next
``tapps_upgrade``. TAP-6499: a consumer configured four full file paths
(``.claude/skills/<name>/SKILL.md`` and friends), none of which are tokens, and
two upgrades overwrote a customized skill without a word.

This module is the leaf that owns the vocabulary so both the upgrade path
(:mod:`tapps_mcp.pipeline.upgrade`) and the doctor check
(:mod:`tapps_mcp.distribution.doctor_platform`) validate against one table
instead of two. It imports nothing from the rest of the pipeline on purpose —
doctor must not drag the upgrade module in to answer a config question.
"""

from __future__ import annotations

# Per-artifact skip tokens. Kept as a mapping so we can add short aliases later
# without changing call sites.
SKIP_TOKENS: dict[str, frozenset[str]] = {
    "agents_md": frozenset({"AGENTS.md"}),
    "claude_md": frozenset({"CLAUDE.md"}),
    "tech_stack_md": frozenset({"TECH_STACK.md"}),
    "claude_settings": frozenset({".claude/settings.json"}),
    "claude_hooks": frozenset({".claude/hooks"}),
    "claude_agents": frozenset({".claude/agents"}),
    "claude_skills": frozenset({".claude/skills"}),
    "python_quality_rule": frozenset({".claude/rules/python-quality.md"}),
    "agent_scope_rule": frozenset({".claude/rules/agent-scope.md"}),
    "autonomy_rule": frozenset({".claude/rules/autonomy.md"}),
    "linear_standards_rule": frozenset({".claude/rules/linear-standards.md"}),
    "integration_hygiene_rule": frozenset({".claude/rules/integration-hygiene.md"}),
    "pipeline_rule": frozenset({".claude/rules/tapps-pipeline.md"}),
    # TAP-978: scoped quality rules with same skip-token pattern.
    "security_rule": frozenset({".claude/rules/security.md"}),
    "test_quality_rule": frozenset({".claude/rules/test-quality.md"}),
    "config_files_rule": frozenset({".claude/rules/config-files.md"}),
    "mcp_config": frozenset({".mcp.json"}),
    "karpathy": frozenset({"karpathy"}),
    # TAP-6890: scaffolded Workflow scripts (val-verify.js, linear-disposition-verify.js).
    "claude_workflows": frozenset({".claude/workflows"}),
}

ALL_SKIP_TOKENS: frozenset[str] = frozenset().union(*SKIP_TOKENS.values())

# Tokens that cover a whole directory. A configured entry pointing *inside* one
# of these is the common mistake: the operator wanted per-file granularity,
# which the vocabulary does not offer.
_DIRECTORY_TOKENS: tuple[str, ...] = (
    ".claude/hooks",
    ".claude/agents",
    ".claude/skills",
    ".claude/workflows",
)


def unknown_skip_tokens(configured: object) -> list[str]:
    """Return the sorted ``upgrade_skip_files`` entries outside the vocabulary."""
    if not isinstance(configured, (list, tuple, set, frozenset)):
        return []
    return sorted({str(entry) for entry in configured} - ALL_SKIP_TOKENS)


def nearest_token(entry: str) -> str | None:
    """Return the directory token covering *entry*, when one does.

    ``.claude/skills/orchestration-prompt/SKILL.md`` → ``.claude/skills``.
    Returns ``None`` for entries that resemble no known token, so the caller
    reports "unrecognized" rather than inventing a suggestion.
    """
    normalized = entry.replace("\\", "/")
    # Strip a leading "./" only — ``lstrip("./")`` would eat the dot that makes
    # ``.claude`` a dotfile directory and never match a token again.
    if normalized.startswith("./"):
        normalized = normalized[2:]
    for token in _DIRECTORY_TOKENS:
        if normalized == token or normalized.startswith(f"{token}/"):
            return token
    return None


def describe_unknown_skip_token(entry: str) -> str:
    """Return a one-line operator-facing explanation for one bad *entry*."""
    nearest = nearest_token(entry)
    if nearest is not None:
        return (
            f"{entry!r} is not a skip token — upgrade_skip_files matches a fixed "
            f"vocabulary at directory granularity, not file paths, so nothing was "
            f"skipped for it. Use {nearest!r} to protect the whole directory, or "
            f"fold the customization upstream so upgrade regenerates it."
        )
    return (
        f"{entry!r} is not a recognized skip token — nothing was skipped for it. "
        f"Valid tokens: {', '.join(sorted(ALL_SKIP_TOKENS))}."
    )


def describe_unknown_skip_tokens(unknown: list[str]) -> list[str]:
    """Return one explanation line per entry in *unknown*."""
    return [describe_unknown_skip_token(entry) for entry in unknown]


__all__ = [
    "ALL_SKIP_TOKENS",
    "SKIP_TOKENS",
    "describe_unknown_skip_token",
    "describe_unknown_skip_tokens",
    "nearest_token",
    "unknown_skip_tokens",
]
