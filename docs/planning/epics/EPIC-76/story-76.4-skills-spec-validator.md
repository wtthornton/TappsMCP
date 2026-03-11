# Story 76.4: Optional skills spec validator (test or CLI)

**Epic:** [EPIC-76-SKILLS-SPEC-COMPLIANCE-AND-VALIDATION](../EPIC-76-SKILLS-SPEC-COMPLIANCE-AND-VALIDATION.md)  
**Priority:** P3 | **LOE:** 1–2 days

## Problem

There is no single place that validates all SKILL.md frontmatter against the Agent Skills spec (name regex, name matches dir, description 1–1024 chars, optional allowed-tools format). A validator would catch regressions when templates are edited and help third-party skill authors.

## Purpose & Intent

This story exists so that **spec compliance is enforced in one place** and regressions are caught by tests or CLI before skills are generated or shipped. A reusable validator benefits both TappsMCP (CI) and consumers who author their own skills and want to check them against the same spec.

## Tasks

- [ ] Add a validator function (e.g. in `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py` or a small `skills_validator.py`) that, given a skill name and frontmatter dict (or raw SKILL.md content), checks: name 1–64 chars, lowercase alphanumeric + hyphens, no leading/trailing/consecutive hyphens; description 1–1024 chars; if allowed-tools present, optionally check format (space-delimited or list). Return a list of errors (empty if valid).
- [ ] Wire the validator into test_platform_skills.py so all CLAUDE_SKILLS and CURSOR_SKILLS are validated (and generate_skills output if desired). Optionally add a CLI command `tapps-mcp validate-skills [path]` that validates skills in a given directory (default: .claude/skills or .cursor/skills from project root).
- [ ] Document in README or AGENTS.md that skills can be validated via pytest or CLI.

## Acceptance criteria

- [ ] Validator exists and is called from tests for all built-in skills.
- [ ] Validator checks name and description per spec; allowed-tools format is optional.
- [ ] Optional CLI `validate-skills` works and is documented.
- [ ] No breaking changes to generate_skills or init/upgrade.

## Files

- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py` or `packages/tapps-mcp/src/tapps_mcp/pipeline/skills_validator.py`
- `packages/tapps-mcp/tests/unit/test_platform_skills.py`
- `packages/tapps-mcp/src/tapps_mcp/cli.py` (if adding `validate-skills` command — register new Click command)
- README or AGENTS.md

## Dependencies

- Story 76.1 (description length) — validator reuses description 1–1024 check; 76.1 test can call validator.

## References

- agentskills.io specification; Epic 76; platform_skills.generate_skills()
