# cli.py: quick-check + validate-changed --file-paths

## What

cli.py: quick-check + validate-changed --file-paths

## Where

- `packages/tapps-mcp/src/tapps_mcp/cli.py:430-474`
- `docs/TROUBLESHOOTING.md:17-34`
- `AGENTS.md`

## Acceptance

- [ ] - New CLI command: tapps-mcp quick-check --file-path PATH [--preset standard]
- validate-changed accepts --file-paths comma-separated (alias --paths)
- TROUBLESHOOTING.md and AGENTS.md table updated with correct CLI equivalents
- CLI quick-check exit code 1 on gate fail; prints lint excerpts
- Unit test for CLI argument parsing
