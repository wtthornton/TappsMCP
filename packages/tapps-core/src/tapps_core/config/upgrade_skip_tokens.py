"""Fixed vocabulary for ``upgrade_skip_files`` and validation of configured entries.

``upgrade_skip_files`` is **not** a path glob. Each entry must match one of the
tokens in :data:`SKIP_TOKENS` exactly; anything else is silently inert — the
artifact it looked like it protected gets rewritten on the next
``tapps_upgrade``. TAP-6499: a consumer configured four full file paths
(``.claude/skills/<name>/SKILL.md`` and friends), none of which are tokens, and
two upgrades overwrote a customized skill without a word.

This module is the leaf that owns the vocabulary. It lives in tapps-core
(rather than tapps-mcp, where the upgrade pipeline lives) because
:mod:`tapps_core.config.settings` renders the token list into a
``Field(description=...)`` sentence and tapps-core cannot import tapps-mcp
(TAP-7429). :mod:`tapps_mcp.pipeline.upgrade_skip_tokens` re-exports this
module unchanged so existing importers (the upgrade pipeline, the doctor
check) need no path changes. It imports nothing from the rest of either
package on purpose — doctor must not drag the upgrade module in to answer a
config question.
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
    # TAP-7054: Cursor mirrors of the three Claude directory tokens above —
    # written by generate_cursor_hooks() (platform_hooks.py) and the Cursor
    # agent/skill generators (platform_subagents.py, platform_skills.py).
    "cursor_hooks": frozenset({".cursor/hooks"}),
    "cursor_agents": frozenset({".cursor/agents"}),
    "cursor_skills": frozenset({".cursor/skills"}),
    # TAP-7054: same file-path granularity already given to CLAUDE.md/AGENTS.md.
    "copilot_instructions": frozenset({".github/copilot-instructions.md"}),
    "python_quality_rule": frozenset({".claude/rules/python-quality.md"}),
    "agent_scope_rule": frozenset({".claude/rules/agent-scope.md"}),
    "agent_to_agent_rule": frozenset({".claude/rules/agent-to-agent.md"}),
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
    # TAP-6884: project-root scaffolded scripts, not under .claude/.
    "measure_script": frozenset({"scripts/measure.py"}),
    "gitfacts_script": frozenset({"scripts/gitfacts.sh"}),
    "start_program_script": frozenset({"scripts/start-program.sh"}),
    # TAP-7078 box 6: the two check scripts Output step 7 invokes by name.
    "check_prompt_shape_script": frozenset({"scripts/check-prompt-shape.js"}),
    "check_learnings_size_script": frozenset({"scripts/check-learnings-size.js"}),
    # TAP-7425: docs-automation skills are not a single file/dir, so the token
    # names the component rather than a path (matches the "karpathy" pattern).
    "docs_automation": frozenset({"docs_automation"}),
    # TAP-7423: project-root scaffolded templates, not under .claude/ or .cursor/.
    "templates": frozenset({"docs/templates"}),
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
    ".cursor/hooks",
    ".cursor/agents",
    ".cursor/skills",
    "docs/templates",
)


def unknown_skip_tokens(configured: object) -> list[str]:
    """Return the sorted ``upgrade_skip_files`` entries outside the vocabulary."""
    if not isinstance(configured, (list, tuple, set, frozenset)):
        return []
    return sorted({str(entry) for entry in configured} - ALL_SKIP_TOKENS)


def applied_skip_tokens(configured: object) -> list[str]:
    """Return the sorted ``upgrade_skip_files`` entries that matched the vocabulary.

    Companion to :func:`unknown_skip_tokens` (TAP-6891): without this, a
    working entry and an unconfigured project produce identical (silent)
    output — "applied" and "not configured" were indistinguishable.
    """
    if not isinstance(configured, (list, tuple, set, frozenset)):
        return []
    return sorted({str(entry) for entry in configured} & ALL_SKIP_TOKENS)


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


def skip_tokens_field_description() -> str:
    """Render the ``upgrade_skip_files`` Field description from the live vocabulary.

    Used by :mod:`tapps_core.config.settings` so the enumerated token list can
    never drift from :data:`ALL_SKIP_TOKENS` (TAP-7429) — the sentence is
    built here, once, rather than hand-restated in the Field description.
    """
    token_list = ", ".join(repr(token) for token in sorted(ALL_SKIP_TOKENS))
    return (
        "Per-artifact tokens to skip during tapps_upgrade. MATCHING IS EXACT "
        "AGAINST A FIXED TOKEN VOCABULARY — not path globbing, not prefix "
        "matching. An entry that is not one of the tokens below protects "
        "NOTHING: upgrade rewrites the artifact anyway. Such entries are "
        "reported as 'unknown_skip_tokens' plus a WARNING line in upgrade "
        "output and a failing 'upgrade_skip_files' doctor check (TAP-6499); "
        "before that they were silently inert. "
        "GRANULARITY IS PER-ARTIFACT, AND DIRECTORY TOKENS COVER THE WHOLE "
        "DIRECTORY: '.claude/skills' pins every skill, and there is no way to "
        "pin one skill or one file inside it — "
        "'.claude/skills/my-skill/SKILL.md' is an invalid entry, not a "
        "narrower one. "
        f"Valid tokens: {token_list}. "
        "Example: ['CLAUDE.md', '.claude/rules/tapps-pipeline.md']. "
        "DURABLE ALTERNATIVE — prefer folding the customization upstream "
        "(into the platform template that generates the file) over pinning: a "
        "pinned artifact stops receiving every later fix and drifts further "
        "from the template with each release. Scaffolded skill files carry "
        "managed-block markers, so customizations written outside the markers "
        "survive upgrade with no skip token at all. "
        "To protect custom files outside this token set, rely on the "
        "dry-run's 'preserved_files' list — upgrade only writes managed "
        "(typically tapps-*) filenames by default. "
        "When AGENTS.md or CLAUDE.md is listed, upgrade still bumps the "
        "version stamp to match the installed package."
    )


__all__ = [
    "ALL_SKIP_TOKENS",
    "SKIP_TOKENS",
    "applied_skip_tokens",
    "describe_unknown_skip_token",
    "describe_unknown_skip_tokens",
    "nearest_token",
    "skip_tokens_field_description",
    "unknown_skip_tokens",
]
