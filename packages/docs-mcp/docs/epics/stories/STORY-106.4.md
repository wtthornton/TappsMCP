# linear-release-update skill + tapps_init/tapps_upgrade deployment

## What

Write the linear-release-update skill (generator → validator → tapps_release_update → invalidate cache).

## Where

- `.claude/skills/linear-release-update/skill.md:1-80`
- `packages/tapps-mcp/src/tapps_mcp/tools/init.py:1-100`
- `packages/tapps-mcp/src/tapps_mcp/tools/upgrade.py:1-80`

## Acceptance

- [ ] linear-release-update skill file is created at .claude/skills/linear-release-update/skill.md with correct trigger description and flow steps
- [ ] tapps_init includes the skill in its bootstrap file set (creates the skill file in the target project)
- [ ] tapps_upgrade --dry-run lists linear-release-update as a file that will be written/updated

## Refs

TAP-1108
