---
name: tapps-domain-frontend
user-invocable: true
model: claude-sonnet-5
description: >-
  Frontend/UX TAPPS workflow: playbook, UI library docs, and quality gate on scored files. Use when building UI components, accessibility fixes, or client-side routing changes.
allowed-tools: mcp__plugin_tapps-mcp_tapps-mcp__tapps_session_start mcp__plugin_tapps-mcp_tapps-mcp__tapps_domain_playbook mcp__plugin_tapps-mcp_tapps-mcp__tapps_lookup_docs mcp__plugin_tapps-mcp_tapps-mcp__tapps_quick_check mcp__plugin_tapps-mcp_tapps-mcp__tapps_validate_changed mcp__plugin_tapps-mcp_tapps-mcp__tapps_checklist mcp__plugin_tapps-mcp_tapps-mcp__tapps_score_file
argument-hint: "[file-path or scope]"
---

Domain playbook workflow — same quality gate as the standard TAPPS pipeline.

1. **Session bootstrap.** Call `tapps_session_start()` if not already called this session.
2. **Load playbook.** Call `tapps_domain_playbook(domain="user-experience")` (or read bundled checklist from the response). Follow its workflow and checklist.
3. **Library docs.** For each entry in `lookup_hints`, call `tapps_lookup_docs(library=..., topic=...)` before using those APIs.
4. **Domain tools.** Run the tools listed in `recommended_tools` on changed files in scope.
5. **Edit loop.** After each Python file change, call `tapps_quick_check(file_path=...)`.
6. **Close out.** Invoke `/tapps-finish-task` with the task_type=frontend. Do not declare done without validate + checklist.

