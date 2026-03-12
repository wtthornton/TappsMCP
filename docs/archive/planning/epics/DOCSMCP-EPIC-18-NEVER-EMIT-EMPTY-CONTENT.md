# DocsMCP Epic 18 — Never Emit Empty Content

> Status: Complete | Priority: High | Package: docs-mcp
> Triggered by: [Epic 12 Review Feedback](../../epic-12-review-feedback.md) (TheStudio)
> Addresses: Review items #1, #2, #4, #9, #10, #13

---

## Goal

Eliminate all placeholder/template content from generated epic and story documents. Every section the generator emits must contain real, derived, or contextually appropriate content — or be omitted entirely. A reader should never encounter "Define mitigation strategy", "Test happy path...", or "No specific knowledge found" in generated output.

## Motivation

TheStudio's Epic 12 generation revealed a **"looks complete but isn't" problem**: risk tables with template placeholders instead of classifications, test cases with generic names, expert sections with empty recommendations, and INVEST checklists that are always unchecked. This creates **false confidence** — reviewers skim past sections that appear filled but contain zero information. For security-sensitive epics, this is actively harmful.

2026 best practices (ISO 31000, Agile Alliance) mandate that automated planning tools either produce actionable content or explicitly signal gaps requiring human input — never silently emit templates.

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Placeholder sections in generated output | 6+ per epic | 0 | Regex scan for known placeholder patterns |
| Expert recommendation usefulness | 30% show "No specific knowledge" | 0% empty; low-confidence suppressed or flagged | Count of empty expert blocks |
| Test case specificity | 6/8 stories have generic test names | 100% derived from ACs or omitted | Manual review of generated stories |
| INVEST pre-fill accuracy | 0/6 items auto-checked | 3+ items auto-assessed per story | Count of auto-checked items |

## Non-Goals

- Adding new section types to the template (that's Epic 19)
- Changing the SmartMerger or docsmcp marker system
- Requiring LLM calls for content generation (all derivation must be deterministic)
- Changing the MCP tool signatures (backward compatible)

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Over-aggressive suppression hides useful section structure | Medium | Medium | Emit a single-line "⚠ Manual input needed: {section}" note instead of full placeholder |
| Test name derivation produces poor names from vague ACs | Medium | Low | Fall back to numbered `test_ac_{N}_<first_3_words>` pattern; always better than "Test happy path" |
| Risk auto-classification misidentifies domain keywords | Low | Medium | Use conservative keyword sets; default to Medium/Medium when uncertain |
| INVEST auto-assessment gives false confidence | Low | Low | Only check items with high-signal indicators; leave ambiguous items unchecked |

## Dependencies

- DocsMCP Epics 1-17 complete (confirmed)
- TappsMCP expert system (tapps_core.experts) — for expert confidence thresholds

## Acceptance Criteria

- [ ] AC1: Risk assessment section auto-classifies probability and impact from keywords (e.g., "encryption"/"auth" → High impact; "UI"/"formatting" → Low impact)
- [ ] AC2: Risk mitigations are either derived from expert advice or the section shows "⚠ Mitigation needed" — never "Define mitigation strategy"
- [ ] AC3: When `test_cases` parameter is empty, test names are derived from acceptance criteria (e.g., AC "User can reset password" → `test_user_can_reset_password`)
- [ ] AC4: When no acceptance criteria exist either, the Test Cases section is omitted entirely
- [ ] AC5: Expert recommendations with confidence < 30% are suppressed; 30-50% show "⚠ Expert review recommended for {domain}"
- [ ] AC6: Expert recommendations with confidence ≥ 50% render the actual advice text (current behavior, preserved)
- [ ] AC7: INVEST checklist auto-checks "Testable" when test_cases or acceptance_criteria are present
- [ ] AC8: INVEST checklist auto-checks "Independent" when dependencies list is empty
- [ ] AC9: INVEST checklist auto-checks "Estimable" when points > 0 or size is set
- [ ] AC10: INVEST checklist auto-checks "Small" when points ≤ 5 or size in ("S", "M")
- [ ] AC11: Performance targets section is omitted when no performance-related expert advice exists (confidence ≥ 50%)
- [ ] AC12: All existing tests continue to pass (backward compatible)
- [ ] AC13: New tests cover each derivation pathway and suppression rule

---

## Stories

### Story 18.1 — Risk Assessment Auto-Classification

**Size: M (5 points)**

As a planning document consumer, I want risk assessments to have real probability/impact classifications so that I can prioritize mitigations without manual triage.

**Tasks:**
1. Create `RiskClassifier` class in `generators/risk_classifier.py` with keyword-to-risk mapping
   - Security keywords (encrypt, auth, credential, secret, token) → High impact
   - Data keywords (migration, schema, database, backup) → High impact
   - Infrastructure keywords (deploy, docker, CI, pipeline) → Medium impact
   - UI/UX keywords (display, format, label, color) → Low impact
   - Default: Medium probability, Medium impact
2. Add ISO 31000-aligned 3×3 risk matrix scoring (Low/Medium/High × Low/Medium/High → risk score 1-9)
3. Integrate `RiskClassifier` into `EpicGenerator._render_risk_assessment()`
4. When expert advice exists for a risk domain, derive mitigation from expert advice text
5. When no expert advice exists, emit "⚠ Mitigation required — no automated recommendation available"
6. Never emit "Define mitigation strategy" or template placeholders
7. Write unit tests for keyword classification, matrix scoring, and expert-derived mitigations

**Test Cases:**
- `test_risk_classifier_security_keywords_high_impact` — "encryption key rotation" → High impact
- `test_risk_classifier_ui_keywords_low_impact` — "button label alignment" → Low impact
- `test_risk_classifier_default_medium` — "refactor helper module" → Medium/Medium
- `test_risk_mitigation_from_expert_advice` — Expert advice present → mitigation derived
- `test_risk_mitigation_no_expert` — No advice → warning message, not placeholder
- `test_risk_matrix_scoring` — All 9 combinations produce correct risk score

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/risk_classifier.py` (new)
- `packages/docs-mcp/src/docs_mcp/generators/epics.py` (modify `_render_risk_assessment`)
- `packages/docs-mcp/tests/unit/test_risk_classifier.py` (new)
- `packages/docs-mcp/tests/unit/test_epics.py` (add risk integration tests)

---

### Story 18.2 — Test Case Name Derivation from Acceptance Criteria

**Size: M (5 points)**

As a story consumer, I want test case names derived from acceptance criteria when none are explicitly provided so that the test section contains actionable, specific test names.

**Tasks:**
1. Create `derive_test_names(acceptance_criteria: list[str]) -> list[str]` in `generators/test_deriver.py`
2. Derivation algorithm:
   - Strip leading "AC:", numbers, checkbox markers
   - Extract verb-object phrase (e.g., "User can reset password" → "reset_password")
   - Prefix with `test_` and snake_case the phrase
   - Truncate to 60 characters
   - Deduplicate names with numeric suffix if needed
3. Integrate into `StoryGenerator._render_test_cases()` — use derived names when `test_cases` is empty but `acceptance_criteria` is not
4. When both `test_cases` and `acceptance_criteria` are empty, omit the Test Cases section entirely
5. Write unit tests covering derivation edge cases

**Test Cases:**
- `test_derive_from_simple_ac` — "User can log in" → `test_user_can_log_in`
- `test_derive_strips_ac_prefix` — "AC1: Validates email format" → `test_validates_email_format`
- `test_derive_strips_checkbox` — "- [ ] Settings page loads in < 2s" → `test_settings_page_loads_in_2s`
- `test_derive_truncates_long_names` — 80-char AC → 60-char test name
- `test_derive_deduplicates` — Two similar ACs → `test_foo`, `test_foo_2`
- `test_omit_section_when_no_ac` — Empty ACs and test_cases → section not rendered
- `test_explicit_test_cases_take_precedence` — Provided test_cases used as-is

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/test_deriver.py` (new)
- `packages/docs-mcp/src/docs_mcp/generators/stories.py` (modify `_render_test_cases`)
- `packages/docs-mcp/tests/unit/test_test_deriver.py` (new)
- `packages/docs-mcp/tests/unit/test_stories.py` (add integration tests)

---

### Story 18.3 — Expert Recommendation Graceful Handling

**Size: S (3 points)**

As a planning document consumer, I want empty expert recommendations to be handled gracefully so that I see actionable guidance or an explicit gap flag — never a misleading empty block.

**Tasks:**
1. Modify `EpicGenerator._enrich_experts()` and `StoryGenerator._enrich_experts()`:
   - Filter out expert results where advice is empty/whitespace or matches "No specific knowledge"
   - For confidence < 30%: suppress entirely
   - For confidence 30-50%: emit "⚠ Expert review recommended for {domain} — automated analysis inconclusive"
   - For confidence ≥ 50%: render advice as-is (preserve current behavior)
2. Modify `_render_technical_notes()` to skip expert guidance entries that were filtered
3. Modify `_render_risk_assessment()` to not create risk rows from empty expert advice
4. Write tests for each confidence threshold and suppression path

**Test Cases:**
- `test_expert_below_30_suppressed` — 25% confidence → not in output
- `test_expert_30_to_50_flagged` — 40% confidence → "⚠ Expert review recommended"
- `test_expert_above_50_rendered` — 85% confidence → full advice text
- `test_expert_empty_advice_suppressed` — "No specific knowledge found" → not in output
- `test_risk_no_expert_rows_from_empty` — Empty expert → no risk row created

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/epics.py` (modify `_enrich_experts`, `_render_technical_notes`, `_render_risk_assessment`)
- `packages/docs-mcp/src/docs_mcp/generators/stories.py` (modify `_enrich_experts`)
- `packages/docs-mcp/tests/unit/test_epics.py` (add expert handling tests)
- `packages/docs-mcp/tests/unit/test_stories.py` (add expert handling tests)

---

### Story 18.4 — INVEST Checklist Auto-Assessment

**Size: S (3 points)**

As a story author, I want the INVEST checklist to be partially pre-filled based on story content so that it provides immediate signal rather than being a blank checklist.

**Tasks:**
1. Create `assess_invest(config: StoryConfig) -> dict[str, bool]` in `generators/invest_assessor.py`
2. Assessment rules:
   - **Independent**: `True` when `dependencies` is empty
   - **Negotiable**: Always `False` (requires human judgment)
   - **Valuable**: `True` when `so_that` is non-empty (has stated value)
   - **Estimable**: `True` when `points > 0` or `size` is set
   - **Small**: `True` when `points <= 5` or `size in ("S", "M")`
   - **Testable**: `True` when `test_cases` or `acceptance_criteria` are non-empty
3. Integrate into `StoryGenerator._render_invest_checklist()` — render `[x]` for True, `[ ]` for False
4. Write tests for each assessment rule

**Test Cases:**
- `test_invest_independent_no_deps` — Empty deps → Independent checked
- `test_invest_independent_has_deps` — Has deps → Independent unchecked
- `test_invest_testable_with_acs` — Has ACs → Testable checked
- `test_invest_estimable_with_points` — Points=3 → Estimable checked
- `test_invest_small_large_story` — Points=13 → Small unchecked
- `test_invest_valuable_with_so_that` — Has so_that → Valuable checked
- `test_invest_negotiable_always_false` — Always unchecked

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/invest_assessor.py` (new)
- `packages/docs-mcp/src/docs_mcp/generators/stories.py` (modify `_render_invest_checklist`)
- `packages/docs-mcp/tests/unit/test_invest_assessor.py` (new)

---

### Story 18.5 — Performance Targets Section Suppression

**Size: S (2 points)**

As a planning document consumer, I want the Performance Targets section omitted when no performance data is available so that I don't see placeholder `< N ms` values.

**Tasks:**
1. Modify `EpicGenerator._render_performance_targets()`:
   - Check if any expert guidance with domain "performance" exists at confidence ≥ 50%
   - If yes: render section with expert-derived targets
   - If no: omit section entirely (return empty string)
2. Write tests for suppression and rendering paths

**Test Cases:**
- `test_performance_targets_omitted_no_expert` — No performance expert → section absent
- `test_performance_targets_rendered_with_expert` — Performance expert at 70% → section present
- `test_performance_targets_omitted_low_confidence` — Performance expert at 25% → section absent

**Files:**
- `packages/docs-mcp/src/docs_mcp/generators/epics.py` (modify `_render_performance_targets`)
- `packages/docs-mcp/tests/unit/test_epics.py` (add suppression tests)
