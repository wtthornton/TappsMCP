# judge.py: uv-aware pytest resolution for MCP env

## What

judge.py: uv-aware pytest resolution for MCP env

## Where

- `packages/tapps-core/src/tapps_core/metrics/judge.py:204-256`
- `packages/tapps-core/tests/unit/test_judge.py:75-120`

## Acceptance

- [ ] - [ ] `_run_pytest_judge` tries `uv run pytest`
- [ ] then `.venv/bin/python -m pytest`
- [ ] then `python -m pytest`
- [ ] Optional `command` field on judge dict overrides auto-resolution
- [ ] cwd=project_root; inherit os.environ
- [ ] Error message names which strategies were attempted when all fail
- [ ] Unit tests in test_judge.py cover uv-first path with mocked subprocess
