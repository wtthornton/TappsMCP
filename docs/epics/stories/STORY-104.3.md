# judge.py: add shell command judge type

## What

Add generic subprocess judge for consumer audit CLIs (report-studio audit, npm test, docker compose config).

## Where

- `packages/tapps-core/src/tapps_core/metrics/judge.py:1-226`
- `packages/tapps-core/src/tapps_core/config/settings.py:748-758`

## Acceptance

- [ ] - [ ] JudgeDefinition accepts type shell (alias command) with target command string
- [ ] Subprocess runs with cwd=project_root
- [ ] inherited env
- [ ] configurable timeout (default 300s)
- [ ] Exit code 0 is pass; non-zero is fail with stderr tail in message
- [ ] Settings docstring and validate_changed docstring list shell type
- [ ] Unit tests cover pass
- [ ] fail
- [ ] timeout
- [ ] and missing command

## Refs

docs/epics/EPIC-104.md
