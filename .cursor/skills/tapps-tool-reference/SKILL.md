---
name: tapps-tool-reference
description: >-
  Look up when to use each TappsMCP tool. Full tool reference with per-tool
  guidance for session start, scoring, validation, checklist, docs, experts.
mcp_tools:
  - tapps_server_info
---

When the user asks about TappsMCP tools, provide the full tool reference.
Essential: tapps_session_start (first), tapps_quick_check (after edits),
tapps_validate_changed (before complete, always pass file_paths), tapps_checklist (before complete).
For the full table, see the skill content. Call tapps_server_info for workflow.

## tapps_consult_expert — built-in domain slugs (17)

`accessibility`, `agent-learning`, `ai-frameworks`, `api-design-integration`, `cloud-infrastructure`, `code-quality-analysis`, `database-data-management`, `data-privacy-compliance`, `development-workflow`, `documentation-knowledge-management`, `github`, `observability-monitoring`, `performance-optimization`, `security`, `software-architecture`, `testing-strategies`, `user-experience`.

Routing: GitHub *platform* (rulesets, Copilot agent, GH Actions as product) → `github`. Generic CI/CD and other hosts → `development-workflow`. LLM/agent/MCP abuse and hardening → `security`. See project `AGENTS.md` for the full table and ownership rules.
