---
name: tapps-domain-testing
user-invocable: true
model: claude-sonnet-5
description: >-
  Testing-focused TAPPS workflow: playbook, pytest docs, diff impact, and validation. Use when adding tests, fixing test gaps, or validating affected tests after refactors.
allowed-tools: mcp__plugin_tapps-mcp_tapps-mcp__tapps_session_start mcp__plugin_tapps-mcp_tapps-mcp__tapps_domain_playbook mcp__plugin_tapps-mcp_tapps-mcp__tapps_lookup_docs mcp__plugin_tapps-mcp_tapps-mcp__tapps_quick_check mcp__plugin_tapps-mcp_tapps-mcp__tapps_validate_changed mcp__plugin_tapps-mcp_tapps-mcp__tapps_checklist mcp__plugin_tapps-mcp_tapps-mcp__tapps_diff_impact mcp__plugin_tapps-mcp_tapps-mcp__tapps_call_graph
argument-hint: "[file-path or scope]"
---

Domain playbook workflow — same quality gate as the standard TAPPS pipeline.

1. **Session bootstrap.** Call `tapps_session_start()` if not already called this session.
2. **Load playbook.** Call `tapps_domain_playbook(domain="testing-strategies")` (or read bundled checklist from the response). Follow its workflow and checklist.
3. **Library docs.** For each entry in `lookup_hints`, call `tapps_lookup_docs(library=..., topic=...)` before using those APIs.
4. **Domain tools.** Run the tools listed in `recommended_tools` on changed files in scope.
5. **Edit loop.** After each Python file change, call `tapps_quick_check(file_path=...)`.
4b. Call `tapps_diff_impact(file_paths=...)` to rank affected tests.
6. **Close out.** Invoke `/tapps-finish-task` with the task_type=qa. Do not declare done without validate + checklist.

