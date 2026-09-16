---
name: tapps-docs-validate
description: >-
  Validate documentation quality. Checks drift, freshness, links, and
  Diataxis balance. Use for a lighter validation pass than tapps-docs-finish-task.
allowed-tools: >-
  {{docs_prefix}}docs_check_drift
  {{docs_prefix}}docs_check_freshness
  {{docs_prefix}}docs_check_links
  {{docs_prefix}}docs_check_diataxis
---

Validate documentation quality across the project:

1. `{{docs_prefix}}docs_check_drift`
2. `{{docs_prefix}}docs_check_freshness`
3. `{{docs_prefix}}docs_check_links`
4. `{{docs_prefix}}docs_check_diataxis`
5. Present pass/fail with specific fixes
