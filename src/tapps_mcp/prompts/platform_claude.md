# TAPPS Quality Pipeline

This project uses the TAPPS MCP server for automated code quality.

## Setup

TappsMCP is connected as an MCP server. Call `tapps_server_info` at session start.

## 5-Stage Pipeline

Follow these stages in order for every code task:

1. **Discover** - `tapps_server_info`, `tapps_project_profile`
2. **Research** - `tapps_lookup_docs` (before using any library), `tapps_consult_expert`
3. **Develop** - `tapps_score_file(quick=True)` during edit loops
4. **Validate** - `tapps_score_file`, `tapps_quality_gate`, `tapps_security_scan`
5. **Verify** - `tapps_checklist` before declaring done

For detailed stage instructions, request the `tapps_pipeline` MCP prompt with the stage name.
For a full overview, request the `tapps_pipeline_overview` MCP prompt.

## Key Rules

- Always call `tapps_lookup_docs` before using an external library API.
- Quality gate must pass before work is complete.
- Run `tapps_checklist` as the final step.
- Record progress in `docs/TAPPS_HANDOFF.md` and `docs/TAPPS_RUNLOG.md`.
