# Story 89.3: Annotate installed_checkers with environment context

<!-- docsmcp:start:metadata -->
**Epic:** [89 - Cross-Project Tool Parity](../EPIC-89-CROSS-PROJECT-TOOL-PARITY.md)
**Points:** 3
**Priority:** P2 - Medium
**Status:** Proposed

<!-- docsmcp:end:metadata -->

## User Story

As an agent interpreting session start results, I need to know whether `installed_checkers` availability reflects the MCP server's environment or the target project's environment, so that I can correctly assess which tools are actually available for the project I'm working on.

## Description

`installed_checkers` in the session start response lists tools like ruff, bandit, mypy with `available: true/false`. When TappsMCP runs in Docker or a separate virtualenv, these reflect the **MCP server's** installed tools, not the target project's. An agent seeing `bandit: available=false` might skip security scanning, not realizing bandit is installed in the project's own venv.

Add metadata to clarify the detection context and prevent misinterpretation.

## Tasks

- [ ] Add `checker_environment` field to the session start response (value: `"mcp_server"`)
- [ ] Add `checker_environment_note` field: `"Checker availability reflects the MCP server process environment. Target project may have different tools installed."`
- [ ] Consider adding the field to each `InstalledChecker` model or as a section-level annotation
- [ ] Add tests verifying the new fields
- [ ] Update output schema documentation

## Acceptance Criteria

- [ ] Response includes clear indication that checker detection is from MCP server environment
- [ ] Note explains the potential discrepancy for Docker/remote setups
- [ ] Existing checker data structure is not broken (backward compatible)

## Definition of Done

Agents can read the environment context and understand that checker availability may not reflect the target project's state.
