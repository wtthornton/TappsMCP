# Epic 84: Doc Style & Tone Validation (Vale Integration)

<!-- docsmcp:start:metadata -->
**Status:** In Progress
**Priority:** P2 - Medium
**Started:** 2026-03-19
**Estimated LOE:** ~2 weeks (1 developer)
**Dependencies:** Epic 7 (Doc Validation)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that DocsMCP's validation suite is complete -- covering not just whether docs exist and are fresh, but whether they are well-written. Style and tone validation catches the issues that make documentation confusing even when it is technically correct.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

DocsMCP validates documentation style, tone, and writing quality using Vale-compatible rule sets, providing a new `docs_check_style` tool that enforces consistent technical writing standards -- completing the documentation validation suite alongside drift, freshness, completeness, links, and Diataxis checks.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Best-in-class documentation sites (Stripe, Vercel, Cloudflare) enforce strict style guides using Vale or equivalent linters. DocsMCP's validation suite covers code drift, freshness, completeness, and links but has no writing quality checks. Adding style validation catches jargon, passive voice, unclear language, and inconsistent terminology -- the issues that make documentation confusing even when it is technically complete and up-to-date.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] New `docs_check_style` tool analyzes markdown files for style and tone issues
- [ ] Built-in rule set covers: passive voice, jargon, sentence length, heading consistency, tense consistency
- [ ] Rules implemented as deterministic regex/AST patterns (no LLM calls)
- [ ] Each issue has severity (error/warning/suggestion) and fix recommendation
- [ ] Project-level style config supported via `.docsmcp.yaml` (enable/disable rules, custom terms)
- [ ] `docs_check_style` returns structured results with per-file and aggregate scores
- [ ] Optional Vale-compatible output format for teams already using Vale
- [ ] Custom terminology dictionary support for project-specific terms
- [ ] Init/upgrade generates default style config in `.docsmcp.yaml`

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### [84.1](EPIC-84/story-84.1-style-rule-engine.md) -- Style Rule Engine

**Points:** 8

Build a deterministic style checking engine with pluggable rules. Each rule receives parsed markdown content and returns issues with severity, location, and fix suggestion.

**Tasks:**
- [ ] Create `validators/style.py` with `StyleChecker` class
- [ ] Implement `RuleBase` abstract class with `check()` method
- [ ] Implement `PassiveVoiceRule` using regex patterns (be-verb + past-participle)
- [ ] Implement `JargonRule` with configurable term list
- [ ] Implement `SentenceLengthRule` (flag sentences >40 words)
- [ ] Implement `HeadingConsistencyRule` (case style, punctuation)
- [ ] Implement `TenseConsistencyRule` (imperative vs declarative)
- [ ] Add `StyleResult` model with per-file issues and aggregate score
- [ ] Add comprehensive tests for each rule

**Definition of Done:** Style Rule Engine is implemented, tests pass, and documentation is updated.

---

### [84.2](EPIC-84/story-84.2-docs-check-style-mcp-tool.md) -- docs_check_style MCP Tool

**Points:** 5

Register the style checker as an MCP tool with project-wide scanning, configurable rule sets, and structured output.

**Tasks:**
- [ ] Register `docs_check_style` in `server_val_tools.py`
- [ ] Support file path or project-wide scanning
- [ ] Load style config from `.docsmcp.yaml`
- [ ] Support rule enable/disable via config
- [ ] Add Vale-compatible output format option
- [ ] Add tests for tool handler

**Definition of Done:** docs_check_style MCP Tool is implemented, tests pass, and documentation is updated.

---

### [84.3](EPIC-84/story-84.3-custom-terminology-init.md) -- Custom Terminology & Init Integration

**Points:** 3

Support project-specific terminology dictionaries and wire style config into init/upgrade.

**Tasks:**
- [ ] Add terminology dictionary support (`.docsmcp-terms.txt`)
- [ ] Auto-detect project terms from code identifiers
- [ ] Add default style config section to `.docsmcp.yaml` template in init
- [ ] Add `docs_check_style` to AGENTS.md template
- [ ] Update docs-mcp CLAUDE.md
- [ ] Add tests for custom terms and init integration

**Definition of Done:** Custom Terminology & Init Integration is implemented, tests pass, and documentation is updated.

---

### [84.4](EPIC-84/story-84.4-style-report-project-scan.md) -- Style Report in Project Scan

**Points:** 2

Include style summary in `docs_project_scan` output when style rules are configured.

**Tasks:**
- [ ] Add optional `style_summary` to project scan results
- [ ] Run style checks during project scan when enabled
- [ ] Include top-5 most common issues in summary
- [ ] Add tests for enriched project scan

**Definition of Done:** Style Report in Project Scan is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Rules must be deterministic (regex/pattern-based) matching TappsMCP's no-LLM principle
- Vale rules use YAML format -- DocsMCP can read Vale configs but uses its own engine internally
- Passive voice detection uses a well-known regex pattern matching be-verb + past-participle
- Heading consistency checks case style (Title Case vs sentence case) and punctuation
- Custom terms prevent false positives on domain-specific vocabulary (e.g., "MCP" is not jargon)

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Full Vale compatibility (subset of common rules only)
- Grammar checking (too complex for deterministic rules)
- Auto-fixing style issues (report only)

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Style rules | 0 | 7 | built-in rule count |
| Adoption | 0 | 15 | monthly docs_check_style calls |
| Writing quality | qualitative | improved | before/after comparison |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 84.1: Style Rule Engine
2. Story 84.2: docs_check_style MCP Tool
3. Story 84.3: Custom Terminology & Init Integration
4. Story 84.4: Style Report in Project Scan

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Style rules can be noisy for terse technical docs | Medium | Low | Severity levels + easy per-rule disable in config |
| English-only initially | Medium | Medium | Non-English projects disable rules via config; future i18n epic |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| `packages/docs-mcp/src/docs_mcp/validators/style.py` | 84.1 | New file: StyleChecker + rules |
| `packages/docs-mcp/src/docs_mcp/server_val_tools.py` | 84.2 | Register docs_check_style |
| `packages/docs-mcp/src/docs_mcp/config/settings.py` | 84.3 | Add style config section |
| `packages/docs-mcp/src/docs_mcp/server.py` | 84.4 | Enrich project_scan with style |

<!-- docsmcp:end:files-affected -->
