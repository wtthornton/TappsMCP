---
name: tapps-docs-bootstrap
user-invocable: true
description: >-
  Bootstrap documentation for a new or under-documented project: README,
  CONTRIBUTING, onboarding, completeness check. Use when creating a README,
  onboarding guide, or initial doc scaffold (Anthropic documentation skill parity).
allowed-tools: >-
  {{docs_prefix}}docs_session_start
  {{docs_prefix}}docs_module_map
  {{docs_prefix}}docs_generate_readme
  {{docs_prefix}}docs_generate_contributing
  {{docs_prefix}}docs_generate_onboarding
  {{docs_prefix}}docs_check_completeness
argument-hint: "[style: minimal|standard|comprehensive]"
---

Bootstrap project documentation end-to-end:

1. `{{docs_prefix}}docs_session_start` — inventory gaps and recommendations.
2. `{{docs_prefix}}docs_module_map` — understand structure (optional but recommended).
3. `{{docs_prefix}}docs_generate_readme(style="standard", merge=true)` — create/update README.
4. `{{docs_prefix}}docs_generate_contributing` — CONTRIBUTING.md.
5. `{{docs_prefix}}docs_generate_onboarding` — docs/ONBOARDING.md.
6. `{{docs_prefix}}docs_check_completeness` — target score ≥ 80 for bootstrap; list remaining gaps.

Hand-edit placeholders in onboarding/README before declaring done.
