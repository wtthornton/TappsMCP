# Epic 12: Platform Integration & Feature Gaps

**Created:** 2026-02-21
**Priority:** P1
**LOE:** ~4-6 weeks (1 developer), ~2-3 weeks (2 developers)
**Dependencies:** Epic 0 (Foundation), Epic 6 (Distribution), Epic 8 (Pipeline)
**Status:** In Progress (Tiers 1-3 Complete)

## Overview

TappsMCP currently generates minimal platform-specific configuration during `tapps_init`.
This epic closes the gap between what MCP clients (Claude Code, Cursor, VS Code) can do
and what TappsMCP leverages, transforming it from a manually-invoked tool into an
**always-on, automatic quality pipeline**.

## Research References

All specifications and detailed findings are in the `research/` directory:

| File | Contents |
|------|----------|
| [claude-code-hooks.md](research/claude-code-hooks.md) | All 17 Claude Code hook events with payloads, exit codes, matchers |
| [claude-code-subagents.md](research/claude-code-subagents.md) | Subagent format, Agent Teams, plugin format, TappsMCP agent definitions |
| [cursor-features.md](research/cursor-features.md) | Cursor hooks (6), rules, skills, subagents, plugins, BugBot, sandbox, elicitation |
| [tool-annotations.md](research/tool-annotations.md) | MCP tool annotation spec, audit of all 21 TappsMCP tools |
| [mcp-config-gaps.md](research/mcp-config-gaps.md) | Server instructions, env vars, permissions, VS Code config |
| [skills-format.md](research/skills-format.md) | SKILL.md open standard, cross-platform format, TappsMCP skill definitions |
| [platform-comparison.md](research/platform-comparison.md) | Side-by-side feature matrix: Claude Code vs Cursor vs VS Code |

## Story Overview

| Story | Name | Tier | Priority | LOE | Platform | Status |
|-------|------|------|----------|-----|----------|--------|
| [12.1](stories/12.1-tool-annotations.md) | Add Tool Annotations | T1 | P0 | 1 day | All | **Complete** |
| [12.2](stories/12.2-server-instructions.md) | Server Instructions Field | T1 | P0 | 0.5 day | Claude Code | **Complete** |
| [12.3](stories/12.3-permission-config.md) | Permission Pre-Configuration | T1 | P0 | 0.5 day | Claude Code | **Complete** |
| [12.4](stories/12.4-env-in-config.md) | Environment Variables in MCP Config | T1 | P0 | 0.5 day | All | **Complete** |
| [12.5](stories/12.5-claude-hooks.md) | Claude Code Hooks Generation | T2 | P1 | 3-4 days | Claude Code | **Complete** |
| [12.6](stories/12.6-subagent-definitions.md) | Custom Subagent Definitions | T2 | P1 | 2-3 days | Claude + Cursor | **Complete** |
| [12.7](stories/12.7-cursor-hooks.md) | Cursor Hooks Generation | T2 | P1 | 2 days | Cursor | **Complete** |
| [12.8](stories/12.8-skills-generation.md) | Skills Generation (SKILL.md) | T2 | P1 | 2 days | Claude + Cursor | **Complete** |
| [12.9](stories/12.9-claude-plugin.md) | Claude Code Plugin Bundle | T3 | P2 | 2 days | Claude Code | **Complete** |
| [12.10](stories/12.10-cursor-plugin.md) | Cursor Plugin Bundle | T3 | P2 | 2 days | Cursor | **Complete** |
| [12.11](stories/12.11-cursor-rule-types.md) | Cursor Rule Types Enhancement | T3 | P2 | 1 day | Cursor | **Complete** |
| [12.12](stories/12.12-agent-teams.md) | Agent Teams Integration | T3 | P2 | 1 day | Claude Code | **Complete** |
| [12.13](stories/12.13-vscode-instructions.md) | VS Code / Copilot Instructions | T4 | P3 | 0.5 day | VS Code | Pending |
| [12.14](stories/12.14-bugbot-rules.md) | Cursor BugBot Rules | T4 | P3 | 0.5 day | Cursor | Pending |
| [12.15](stories/12.15-elicitation.md) | MCP Elicitation Support | T4 | P3 | 2-3 days | Cursor | Pending |
| [12.16](stories/12.16-ci-headless.md) | CI/Headless Documentation | T4 | P3 | 1 day | CI | Pending |
| [12.17](stories/12.17-cursor-marketplace.md) | Cursor Marketplace Publishing | T4 | P3 | 2 days | Cursor | Pending |
| [12.18](stories/12.18-agent-sdk.md) | Agent SDK Integration | T4 | P3 | 3+ days | Custom | Pending |

## Implementation Tiers

### Tier 1 — Quick Wins (2.5 days)
**Ship first. Low effort, critical impact across all clients.**

Stories 12.1-12.4 can be implemented as a single PR:
- Tool annotations eliminate permission prompts on 18/21 tools
- Server instructions enable Tool Search discovery
- Permission config auto-allows all TappsMCP tools
- Env vars prevent path resolution failures

### Tier 2 — Hooks & Agents (9-11 days)
**The core of the "always-on quality pipeline."**

Stories 12.5-12.8 create the automated enforcement layer:
- Claude Code hooks: SessionStart auto-activates, Stop blocks until validated,
  TaskCompleted prevents premature completion, PreCompact preserves context
- Subagents: tapps-reviewer, tapps-researcher, tapps-validator run in parallel
- Cursor hooks: afterFileEdit triggers checks, stop continues for validation
- Skills: Cross-platform workflow templates for scoring, gating, validation

### Tier 3 — Package & Distribute (6 days)
**Bundle everything for easy installation.**

Stories 12.9-12.12 package the generated files:
- Claude Code plugin: agents + skills + hooks + MCP config as one install
- Cursor plugin: agents + skills + hooks + rules + MCP config for marketplace
- Enhanced Cursor rules: autoAttach for Python files, agentRequested for experts
- Agent Teams docs: quality watchdog teammate pattern

### Tier 4 — Polish (9+ days)
**Nice-to-have features for completeness.**

Stories 12.13-12.18 extend coverage:
- VS Code instructions for Copilot users
- BugBot rules for automated PR review
- MCP elicitation for interactive gate selection
- CI pipeline integration documentation
- Cursor marketplace listing
- Agent SDK integration for custom apps

## Dependency Graph

```
Tier 1 (12.1-12.4) — No dependencies, ship together
    ↓
Tier 2 (12.5-12.8) — Depends on Tier 1 for config patterns
    ├── 12.5 (Claude hooks) ← independent
    ├── 12.6 (Subagents) ← independent
    ├── 12.7 (Cursor hooks) ← independent
    └── 12.8 (Skills) ← independent
    ↓
Tier 3 (12.9-12.12) — Bundles output from Tier 2
    ├── 12.9 (Claude plugin) ← depends on 12.5, 12.6, 12.8
    ├── 12.10 (Cursor plugin) ← depends on 12.6, 12.7, 12.8, 12.11
    ├── 12.11 (Cursor rules) ← independent
    └── 12.12 (Agent Teams) ← depends on 12.5
    ↓
Tier 4 (12.13-12.18) — Independent, ship any order
```

## Parallelization

With 2 developers (or using Agent Teams):
- **Track A:** 12.1-12.4 (Tier 1) → 12.5 (Claude hooks) → 12.9 (Claude plugin) → 12.12 (Teams)
- **Track B:** (after Tier 1) 12.6 (Subagents) + 12.7 (Cursor hooks) → 12.8 (Skills) → 12.10 (Cursor plugin)

## Key Files Modified

| File | Changes |
|------|---------|
| `src/tapps_mcp/server.py` | Add tool annotations to all 21 `@mcp.tool()` decorators |
| `src/tapps_mcp/pipeline/init.py` | Generate hooks, subagents, skills, settings, BugBot rules |
| `src/tapps_mcp/distribution/setup_generator.py` | Add env, instructions to generated MCP configs |
| `src/tapps_mcp/prompts/` | New templates for hooks, subagents, skills |
| `tests/unit/` | Tests for all new generation logic |
| `tests/integration/` | End-to-end tapps_init tests with new file generation |

## Success Criteria

1. `tapps_init` generates complete platform-specific configurations for Claude Code, Cursor, and VS Code
2. Claude Code users experience zero permission prompts for TappsMCP tools
3. Quality enforcement is automatic via hooks (Stop blocks until validated)
4. Subagents run quality checks in parallel without user intervention
5. Skills provide discoverable workflows on both platforms
6. All changes are backward-compatible with existing tapps_init installations
