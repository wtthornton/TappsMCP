---
name: tapps-docs-finish-task
user-invocable: true
description: >-
  End-of-doc-work validation bundle: drift, links, cross-refs, completeness,
  optional release gate. Use when documentation edits are complete and you
  need a pass/fail verdict before merging or releasing.
allowed-tools: >-
  {{docs_prefix}}docs_check_drift
  {{docs_prefix}}docs_check_links
  {{docs_prefix}}docs_check_cross_refs
  {{docs_prefix}}docs_check_completeness
  {{docs_prefix}}docs_release_gate
  mcp__nlt-build__tapps_checklist
argument-hint: "[--release]"
---

Close out documentation work:

1. `{{docs_prefix}}docs_check_drift` — stop if critical undocumented APIs (report count).
2. `{{docs_prefix}}docs_check_links(broken_only=true)` — stop on broken internal links.
3. `{{docs_prefix}}docs_check_cross_refs(doc_dirs="docs")` — orphans and broken refs.
4. `{{docs_prefix}}docs_check_completeness` — target ≥ 90 for merge-ready.
5. **Release only:** `{{docs_prefix}}docs_release_gate` — aggregate verdict; stop if fail.
6. `mcp__nlt-build__tapps_checklist(task_type=documentation)` — TAPPS doc-workflow checklist.

**Report:** `Drift: N findings. Links: pass|fail. Completeness: X/100. Release gate: pass|skipped|fail.`
