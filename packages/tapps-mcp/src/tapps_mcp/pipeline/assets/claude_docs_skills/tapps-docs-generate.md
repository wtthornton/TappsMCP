---
name: tapps-docs-generate
user-invocable: true
description: >-
  Quick doc generation: README, llms.txt, changelog. Use for a minimal
  generate pass; prefer tapps-docs-bootstrap for new projects.
allowed-tools: >-
  {{docs_prefix}}docs_generate_readme
  {{docs_prefix}}docs_generate_llms_txt
  {{docs_prefix}}docs_generate_changelog
  {{docs_prefix}}docs_generate_runbook
  {{docs_prefix}}docs_generate_postmortem
---

Generate documentation artifacts:

1. `{{docs_prefix}}docs_generate_readme(merge=true)`
2. `{{docs_prefix}}docs_generate_llms_txt(mode="compact")`
3. `{{docs_prefix}}docs_generate_changelog` when git tags exist
4. For operational docs: `docs_generate_runbook` / `docs_generate_postmortem` with structured fields
