---
name: tapps-flow-review
user-invocable: true
model: claude-sonnet-5
description: >-
  QA/review flow: parallel review pipeline or single-file review ending in checklist.
  Use when reviewing PRs, audit findings, or validating another agent's changes.
allowed-tools: mcp__plugin_tapps-mcp_tapps-mcp__tapps_validate_changed mcp__plugin_tapps-mcp_tapps-mcp__tapps_checklist mcp__plugin_tapps-mcp_tapps-mcp__tapps_security_scan
argument-hint: "[file paths]"
---

Prefer `/tapps-review-pipeline` for multiple Python files. Otherwise:

1. `tapps_security_scan` + `tapps_quick_check` on targets
2. `/tapps-finish-task` with `task_type=review` or `qa`
