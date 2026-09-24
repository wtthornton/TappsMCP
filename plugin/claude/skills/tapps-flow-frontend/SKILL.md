---
name: tapps-flow-frontend
user-invocable: true
model: claude-sonnet-5
description: >-
  Frontend work flow combining UX playbook and standard finish pipeline.
  Use when the task is primarily UI/UX implementation or accessibility.
allowed-tools: mcp__plugin_tapps-mcp_tapps-mcp__tapps_session_start mcp__plugin_tapps-mcp_tapps-mcp__tapps_domain_playbook mcp__plugin_tapps-mcp_tapps-mcp__tapps_lookup_docs mcp__plugin_tapps-mcp_tapps-mcp__tapps_quick_check mcp__plugin_tapps-mcp_tapps-mcp__tapps_validate_changed mcp__plugin_tapps-mcp_tapps-mcp__tapps_checklist
---

1. Invoke `/tapps-domain-frontend` steps 1-5, **or** run this shortcut:
   - `tapps_domain_playbook(domain="user-experience")`
   - `tapps_lookup_docs` for UI libraries in scope
2. `/tapps-finish-task` with `task_type=frontend`
3. Optional persona: agency-agents Frontend Developer (voice only; TappsMCP owns gates)
