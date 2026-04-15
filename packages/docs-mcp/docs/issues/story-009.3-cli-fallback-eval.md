# Story 9.3 -- Evaluate CLI Fallback Agent (Aider or Codex)

<!-- docsmcp:start:user-story -->

> **As a** server administrator, **I want** a researched and documented evaluation of Aider and/or Codex CLI as fallback coding agents, **so that** development can continue when Claude Code hits token limits

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 2 | **Size:** S

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that we have a documented fallback strategy when Claude Code CLI exhausts its token budget, avoiding development downtime.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Research Aider (open-source, multi-LLM) and Codex CLI (OpenAI) as headless CLI fallback agents. Evaluate installation, headless mode, cost, LLM backend options, and integration feasibility with the server agent. Produce a recommendation doc. If viable, create an MCP tool module for the chosen agent.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `docs/cli-fallback-evaluation.md`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Research Aider CLI: install, headless mode, LLM backends, cost
- [ ] Research Codex CLI: install, headless mode, API requirements, cost
- [ ] Test headless execution of top candidate on this server
- [ ] Write evaluation doc with recommendation (`docs/cli-fallback-evaluation.md`)
- [ ] If adopted: create MCP tool module (`src/server_agent/tools/`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Research doc comparing Aider and Codex CLI capabilities produced
- [ ] Headless/non-interactive mode tested for chosen candidate
- [ ] Cost and token model documented
- [ ] Recommendation for or against adoption with rationale
- [ ] If adopted: MCP tool module created following claude_cli.py pattern

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Evaluate CLI Fallback Agent (Aider or Codex) code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] Documentation updated
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
