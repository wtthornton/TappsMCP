"""Which skills the Claude plugin bundle omits, and how the ones it ships say so.

TAP-7753. Split out of ``platform_bundles`` so the exclusion set and the
bundle-scoped note derived from it live together in one small, separately
testable place rather than as two stanzas inside an already-long bundler.
"""

from __future__ import annotations

# TAP-7753 round 2 — a filter applied ONLY where the Claude plugin bundle is
# assembled, never a removal from CLAUDE_SKILLS. CLAUDE_SKILLS stays the
# single source of truth for `tapps-mcp init`/`upgrade`, where docs-mcp
# genuinely exists and `linear-issue` is fully usable — a program invariant
# elsewhere requires ``len(CLAUDE_SKILLS) >= 26`` by module import, and
# removing the key would silently break that on a path this bundle doesn't
# own. `linear-issue` is unusable in THIS bundle specifically: every write it
# performs is gated behind `mcp__nlt-linear-issues__docs_*` tools this bundle
# cannot ever resolve (docs-mcp is a separate, undepended-on server —
# TAP-7758), with no reduced-but-real mode to document, unlike `linear-read`/
# `linear-release-update`/`tapps-continue-session`.
# That tool set is NAMED, never counted, in both this file and
# ``platform_bundles._CLAUDE_PLUGIN_README`` — three hand-typed counts of it
# disagreed (11 in the README, 9 in a code comment, 9 in a commit message)
# before anybody measured it. Re-derive it from the skill asset itself:
#
#   grep -oE 'mcp__nlt-linear-issues__docs_[a-z_]+' \
#     packages/tapps-mcp/src/tapps_mcp/pipeline/assets/claude_skills/linear-issue.md \
#     | sort -u
#
# -> docs_generate_epic, docs_generate_story, docs_linear_triage,
#    docs_lint_linear_issue, docs_save_linear_issue, docs_validate_linear_issue
CLAUDE_PLUGIN_EXCLUDED_SKILLS = frozenset({"linear-issue"})


def excluded_skill_note_marker(skill_name: str) -> str:
    """The exact sentence a bundled skill must carry when it routes to a skill
    this bundle does not ship. Derived from the name, never retyped — the
    bundle writer emits it and the test asserts on this same function."""
    return f"`{skill_name}` is not shipped in the Claude plugin bundle"


_EXCLUDED_SKILL_NOTE_HEADING = "## Skills referenced here but not shipped in this bundle"


def annotate_excluded_skill_refs(text: str) -> str:
    """Append a bundle-scoped availability note for every excluded skill this
    body routes to (TAP-7753 round 3).

    Six shipped references pointed at ``linear-issue`` — including a mandatory
    "Linear writes only via `linear-issue`" — after round 2 filtered that skill
    out of the bundle. Part (e) of ``scripts/validate-claude-plugin.sh`` scans
    ``mcp__*`` tool prefixes and is structurally blind to skill-to-skill
    routing, so nothing caught it.

    This runs at the bundle write point rather than in the shared
    ``assets/claude_skills/*.md`` sources on purpose: ``tapps-mcp
    init``/``upgrade`` DO ship ``linear-issue``, so a note edited into the
    shared source would have to be true where the skill is present. Deriving
    the note from :data:`CLAUDE_PLUGIN_EXCLUDED_SKILLS` also means a future
    exclusion is annotated automatically rather than needing six more
    hand-edits nobody would remember to make.
    """
    referenced = [
        name
        for name in sorted(CLAUDE_PLUGIN_EXCLUDED_SKILLS)
        if f"`{name}`" in text or f"/{name}" in text
    ]
    if not referenced:
        return text

    lines = [text.rstrip("\n"), "", _EXCLUDED_SKILL_NOTE_HEADING, ""]
    for name in referenced:
        lines.append(
            f"- **{excluded_skill_note_marker(name)}.** It is installed by"
            f" `tapps-mcp init`/`upgrade`, which also provision the docs-mcp"
            f" server every step of it calls; a plugin-only install cannot"
            f" resolve those tools, so shipping it here would load an inert"
            f" skill (TAP-7753). Where `{name}` is unavailable, the validator"
            f" gate it enforces is unavailable too — run `tapps-mcp init`"
            f" rather than doing the work it describes unvalidated."
        )
    return "\n".join(lines) + "\n"
