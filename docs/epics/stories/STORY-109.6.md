# Skills and hooks: nlt-* server prefix migration

## What

Update generated skills and hook matchers from `mcp__tapps-mcp__` / `mcp__docs-mcp__` to `mcp__nlt-*__` prefixes.

## Where

1. `.claude/skills/linear-issue/SKILL.md:6`
2. `.claude/skills/linear-read/SKILL.md`
3. `.claude/skills/linear-release-update/SKILL.md`
4. `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py`
5. `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py`

## Acceptance

- [ ] linear-issue allowed-tools reference nlt-linear-issues + Linear plugin
- [ ] tapps-finish-task references nlt-code-quality
- [ ] Linear gate hooks match new server names (backward compat one release)
- [ ] `tapps_upgrade` regenerates skill files

## Refs

- EPIC-109 story 109.6
