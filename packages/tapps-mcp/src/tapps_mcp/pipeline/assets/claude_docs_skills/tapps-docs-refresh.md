---
name: tapps-docs-refresh
user-invocable: true
description: >-
  Full documentation refresh workflow: cross-refs, narrative docs, API/diagrams,
  validation suite. Codifies docs/tutorials/05-docs-refresh-workflow.md. Use when
  refreshing project docs, auditing doc health, or preparing docs before a release.
allowed-tools: >-
  {{docs_prefix}}docs_session_start
  {{docs_prefix}}docs_check_cross_refs
  {{docs_prefix}}docs_check_links
  {{docs_prefix}}docs_generate_doc_index
  {{docs_prefix}}docs_generate_purpose
  {{docs_prefix}}docs_generate_onboarding
  {{docs_prefix}}docs_generate_llms_txt
  {{docs_prefix}}docs_generate_api
  {{docs_prefix}}docs_generate_architecture
  {{docs_prefix}}docs_generate_interactive_diagrams
  {{docs_prefix}}docs_check_completeness
  {{docs_prefix}}docs_check_freshness
  {{docs_prefix}}docs_check_drift
  {{docs_prefix}}docs_check_diataxis
  {{docs_prefix}}docs_check_style
argument-hint: "[--exclude docs/archive]"
---

Run the full documentation refresh pipeline. Requires **nlt-project-docs** (and **nlt-build** for code edits). Do not skip failed validation steps.

**Phase 0 — Scope:** Exclude `docs/archive/**` from validation. Tier-1 targets: `PURPOSE.md`, `ONBOARDING.md`, `ARCHITECTURE.md`, `docs/api/*`, `docs/adr/*`.

**Phase 1 — Navigation:**
1. `{{docs_prefix}}docs_check_cross_refs(doc_dirs="docs", exclude="docs/archive")`
2. `{{docs_prefix}}docs_check_links(broken_only=true)`
3. `{{docs_prefix}}docs_generate_doc_index(doc_dirs="docs,README.md,AGENTS.md", output_path="docs/INDEX.md")`

**Phase 2 — Narrative:** `{{docs_prefix}}docs_generate_purpose`, `docs_generate_onboarding`, `docs_generate_llms_txt(mode="compact")` — hand-edit placeholders after generation.

**Phase 3 — API & diagrams:** Regenerate `docs_generate_api` per package; `docs_generate_architecture`; `docs_generate_interactive_diagrams`.

**Phase 4 — Verification (targets):** completeness ≥ 98, cross-refs ≥ 90; run `docs_check_drift`, `docs_check_freshness(summary_only=true)`, `docs_check_diataxis`.

**Phase 5 — Style (optional):** `docs_check_style` on tier-1 narrative files only — skip auto-generated `docs/api/*`.

**Report:** Summary table of scores, broken links count, drift findings, files written.
