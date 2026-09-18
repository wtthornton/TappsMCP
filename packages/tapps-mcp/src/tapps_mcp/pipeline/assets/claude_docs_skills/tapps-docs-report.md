---
name: tapps-docs-report
user-invocable: true
description: >-
  Generate a documentation quality report. Runs project scan, completeness
  check, and Diataxis balance analysis. Use when you need a doc health
  dashboard or audit summary.
allowed-tools: >-
  {{docs_prefix}}docs_project_scan
  {{docs_prefix}}docs_check_completeness
  {{docs_prefix}}docs_check_diataxis
---

Run a comprehensive documentation quality report:

1. `{{docs_prefix}}docs_project_scan`
2. `{{docs_prefix}}docs_check_completeness`
3. `{{docs_prefix}}docs_check_diataxis`
4. Present a summary table with scores and recommendations
