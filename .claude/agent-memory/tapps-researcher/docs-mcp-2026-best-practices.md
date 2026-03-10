# 2026 Best Practices Research: docs-mcp Planning Document Generators

## Research Date
2026-03-09

## Scope
Research findings on 2026 best practices for auto-generated planning documentation (epics, stories, PRDs) with focus on:
1. Epic/story documentation generation best practices
2. Risk assessment automation
3. Test case name generation from acceptance criteria
4. Template deduplication in generated docs
5. Success metrics and stakeholder sections
6. INVEST checklist auto-assessment

---

## 1. EPIC/STORY DOCUMENTATION GENERATION BEST PRACTICES (2026)

### Current Implementation Status
The docs-mcp codebase already implements solid patterns with `epics.py` and `stories.py` generators.

**Current patterns found:**
- Two style variants: `standard` (core sections only) and `comprehensive` (adds advanced sections)
- SmartMerger pattern with `<!-- docsmcp:start:section -->` / `<!-- docsmcp:end:section -->` markers for human-edit preservation
- Auto-populate enrichment from project analyzers (metadata, module map, git history, expert consultation)
- Empty content fallback with sensible placeholders ("Define what...", "TBD", etc.)
- Expert domain consultation for security, testing, performance, architecture, code-quality, API design, observability, DevOps

**2026 Best Practice Recommendations:**

### 1a. Content Completeness Strategy: "Never Emit Empty Content"
**Finding**: 2026 planning docs should follow a strict "principle of complete content" — every generated section should either have real data or a specific action placeholder, never generic placeholder text.

**Pattern to implement:**
- **Empty content detection**: Before rendering any section, check if the input is empty/minimal
- **Three-tier rendering**:
  1. **Real content**: Render actual input data
  2. **Structured placeholder**: Render actionable prompt (not "Define X" but "Define X by [date] — current: empty")
  3. **Disabled section**: Optionally skip the entire section if `include_empty_sections=False`
- **Example**: Epic goal section should either have "Deliver memory system" OR "Goal: TBD (set by [sprint start])" — never both

**Recommended additions to `EpicConfig` and `StoryConfig`:**
- `include_empty_sections: bool = True` — controls whether placeholder-only sections appear
- `placeholder_style: str = "actionable"` — enum: "none" (skip), "actionable" (prompt for action), "generic" (current)
- `completeness_check: bool = False` — flag to emit warnings for empty critical sections

### 1b. Success Metrics Integration
**Finding**: 2026 planning docs increasingly include quantifiable success metrics in epics, tied to OKRs or business outcomes.

**Pattern to implement in `EpicConfig`:**
```
success_metrics: list[str] = []  # E.g., ["Memory hit rate > 80%", "Query latency < 100ms"]
metric_targets: dict[str, str] = {}  # E.g., {"memory_hit_rate": "80%"}
measurement_plan: str = ""  # How/when to measure
```

**Rendering pattern:**
- New section "## Success Metrics" after "## Acceptance Criteria"
- Format: table with Metric | Target | Measurement Method | Owner
- Example from Epic 65 (Memory Best Practices):
  - Memory consolidation deduplication rate > 30%
  - Query latency p99 < 200ms
  - Federation sync within 24h for 95% of entries

### 1c. Stakeholder & RACI Matrix
**Finding**: Enterprise planning docs (2026) increasingly include RACI (Responsible/Accountable/Consulted/Informed) matrices to clarify roles and reduce ambiguity.

**Pattern to implement in `EpicConfig`:**
```
stakeholders: list[str] = []  # E.g., ["Platform PM", "Security lead", "Infra team"]
raci_matrix: dict[str, dict[str, str]] = {}  # story_id -> {stakeholder: role}
  # Roles: "Responsible", "Accountable", "Consulted", "Informed"
```

**Rendering pattern:**
- New section "## Stakeholder Roles" (comprehensive style only)
- Format: RACI table with stories on Y-axis, stakeholders on X-axis
- Helps prevent "nobody took responsibility" failures

### 1d. Dependencies and Blockers Materialization
**Finding**: Current implementation lists dependencies/blocks as text. 2026 best practice is to inline detailed dependency info including: story ID, milestone, risk of drift.

**Enhancement:**
- Dependencies should reference other stories by ID (`Epic N.M`)
- Add `dependency_risk: str` field (e.g., "High — depends on external API release")
- Validate that referenced stories exist in the epic

### 1e. Technical Debt Callout
**Finding**: Epics increasingly call out architectural debt introduced by implementation.

**Pattern:**
- New optional field in `EpicConfig`: `introduces_tech_debt: list[str]`
- Render in Technical Notes section with mitigation timeline (e.g., "Pay down via Epic 67, Q3 2026")

---

## 2. RISK ASSESSMENT AUTOMATION (2026)

### Current Implementation
`epics.py` has `_render_risk_assessment()` that:
- Accepts manual risk list from config
- Auto-detects risks from expert guidance (security/performance/devops domains)
- Renders as 3-column table: Risk | Probability | Impact | Mitigation

**Gap**: Currently, user must provide probability/impact; generators don't auto-classify.

### 2026 Best Practice: Auto-Risk Classification from Keywords

**Recommendation: Implement RiskClassifier**

**Pattern 1: Domain-Keyword Risk Mapping**
Map keywords to risk categories with auto-derived probability/impact:

```
RISK_KEYWORDS = {
    # Security risks
    "encryption": {"category": "security", "probability": "high", "impact": "high"},
    "token": {"category": "security", "probability": "high", "impact": "high"},
    "auth": {"category": "security", "probability": "medium", "impact": "high"},
    "api-key": {"category": "security", "probability": "high", "impact": "high"},
    "injection": {"category": "security", "probability": "medium", "impact": "high"},
    "breach": {"category": "security", "probability": "medium", "impact": "critical"},

    # Performance risks
    "database": {"category": "performance", "probability": "medium", "impact": "medium"},
    "migration": {"category": "performance", "probability": "high", "impact": "high"},
    "scaling": {"category": "performance", "probability": "medium", "impact": "high"},
    "network": {"category": "performance", "probability": "medium", "impact": "medium"},

    # Compatibility risks
    "deprecated": {"category": "compatibility", "probability": "high", "impact": "medium"},
    "breaking": {"category": "compatibility", "probability": "high", "impact": "high"},

    # Organizational risks
    "vendor": {"category": "vendor", "probability": "low", "impact": "high"},
    "dependency": {"category": "dependency", "probability": "medium", "impact": "medium"},
    "refactor": {"category": "architecture", "probability": "medium", "impact": "medium"},
}
```

**Implementation approach:**
1. Tokenize each risk string (or story title, goal)
2. Match against RISK_KEYWORDS (case-insensitive, word-boundary regex: `\b{keyword}\b`)
3. If keyword found, auto-assign probability/impact
4. Allow user override: `risks: list[{"text": "...", "probability": "low", "impact": "high"}]`

**Pattern 2: Standard Risk Matrix (ISO 31000)**
Adopt the 3x3 or 5x5 risk matrix:

```
           Low Impact    Medium Impact    High Impact    Critical Impact
Low Prob      Green        Yellow         Yellow          Orange
Med Prob      Yellow       Yellow         Orange          Red
High Prob     Yellow       Orange         Red             Red
```

**Risk scoring**: Probability × Impact = Risk Score (1-25 scale)
- 1-4: Monitor
- 5-12: Mitigate
- 13-20: Urgent mitigation
- 21-25: Blocker — must resolve before go-live

**Pattern 3: Risk vs Mitigation Pairing**
Current implementation has weak mitigation guidance. 2026 best practice:

```
class EpicRisk(BaseModel):
    description: str
    probability: str  # "Low", "Medium", "High"
    impact: str  # "Low", "Medium", "High", "Critical"
    mitigation: str  # Specific action, not just "Define mitigation strategy"
    owner: str = ""  # Who owns this risk?
    mitigation_deadline: str = ""  # By when?
```

**Rendering**:
- Risk Assessment table: Risk | Prob | Impact | Score | Mitigation | Owner | Deadline
- Color-code by score (green/yellow/orange/red)
- Add summary: "3 High-score risks identified; 2 mitigated by [date], 1 accepted"

### Recommended additions to docs-mcp:

**New module**: `generators/risk_classifier.py`
- `RiskClassifier` class with keyword matching
- `classify_risk(text: str) -> RiskAssessment`
- `merge_expert_risks()` to combine manual + auto-detected risks

**Update `EpicConfig`**:
```python
risks: list[EpicRisk] = []  # Changed from list[str]
auto_classify_risks: bool = True  # Auto-detect from title/goal/stories
risk_matrix_style: str = "3x3"  # or "5x5"
```

---

## 3. TEST CASE NAME GENERATION FROM ACCEPTANCE CRITERIA

### Current Implementation
`stories.py` has `_render_test_cases()` that accepts `test_cases: list[str]`. No auto-generation from ACs.

### 2026 Best Practice: AC-Driven Test Name Generation

**Pattern 1: AC to Test Name Derivation**
Transform acceptance criteria into test names using standard patterns:

```python
AC: "Login form validates empty email"
  → test_login_form_rejects_empty_email()
  → test_login_validation_empty_email_fails()

AC: "API returns 401 for invalid token"
  → test_api_returns_401_invalid_token()
  → test_api_auth_invalid_token_unauthorized()

AC: "Memory consolidation reduces entry count by >30%"
  → test_memory_consolidation_deduplication_rate()
  → test_memory_consolidation_exceeds_30_percent_reduction()
```

**Algorithm**:
1. Extract primary action verb from AC (validates, returns, reduces, prevents, ensures)
2. Extract noun/object (email, token, entry count)
3. Extract condition (empty, invalid, >30%, etc.)
4. Assemble: `test_{component}_{verb}_{noun}_{condition}` or `test_{action}_{expected_outcome}`

**Pattern 2: AC Coverage Matrix**
Pair each AC with generated test names, allowing user refinement:

```python
class ACTestPair(BaseModel):
    acceptance_criterion: str
    auto_generated_tests: list[str]  # 2-3 suggestions
    user_selected_test: str = ""  # User picks or custom
    test_type: str = "unit"  # unit, integration, e2e, contract
```

**Rendering**:
```markdown
## Test Coverage

| AC | Auto-Generated Test Names | Selected |
|----|---------------------------|----------|
| Login form validates empty email | test_login_form_rejects_empty_email<br>test_login_validation_empty_email | test_login_form_rejects_empty_email |
```

**Pattern 3: Test Type Classification from AC Keywords**
Map AC keywords to test type:

```
Keywords → Test Type
"given ... when ... then" → integration (likely BDD/feature test)
"returns 401/403/404" → unit (likely API contract)
"validates" → unit
"persists" → integration (touches DB)
"eventually" → e2e (async/timing concern)
"across sessions" → integration
```

### Recommended additions to docs-mcp:

**New module**: `generators/test_case_generator.py`
- `TestCaseGenerator` class
- `generate_test_names_from_ac(ac: str) -> list[str]`
- `classify_test_type(ac: str) -> str`
- `pair_acs_with_tests(acs: list[str]) -> list[ACTestPair]`

**Update `StoryConfig`**:
```python
acceptance_criteria: list[str] = []
auto_generate_tests: bool = True
test_cases: list[str] = []  # Now optional; can be auto-populated
ac_test_pairs: list[ACTestPair] = []  # New field
```

**Update `StoryGenerator._render_test_cases()`**:
- If `auto_generate_tests=True` and `ac_test_pairs` populated, render the table
- Else fall back to current `test_cases` list

---

## 4. TEMPLATE DEDUPLICATION IN GENERATED DOCS

### Current Implementation
Each epic and story are generated independently. No deduplication of shared sections.

**Example of current redundancy**:
- Epic 65 goal: "Implement memory best practices for 2026"
- Epic 65.1 goal: "Implement memory best practices for 2026 — stats dashboard"
- Both cover similar intro; differs only in specialization

### 2026 Best Practice: DRY for Generated Docs

**Pattern 1: Inherited vs. Specialized Fields**
Implement inheritance-like structure:

```python
class StoryConfig(BaseModel):
    title: str
    epic_number: int = 0
    inherit_from_epic: bool = False  # If True, inherit goal, motivation, technical_notes

    # Inherited fields (only rendered if not overridden)
    goal: str = ""  # If empty and inherit_from_epic, use parent epic's goal
    motivation: str = ""  # Same
    technical_notes: list[str] = []  # Extend, not replace
```

**Rendering pattern**:
- If story goal is empty and `inherit_from_epic=True`, note in story doc:
  ```markdown
  **Goal:** (See Epic 65: Implement memory best practices)

  This story specializes that goal for dashboard stats.
  ```
- Avoids copy-paste; link back to parent

**Pattern 2: Shared Section Library**
For epic + story collections, extract common sections:

```python
class EpicSeriesConfig(BaseModel):
    epics: list[EpicConfig]
    shared_sections: dict[str, str] = {
        "architecture_context": "...",  # Shared arch overview
        "platform_constraints": "...",  # Shared DevOps limits
        "team_notes": "...",  # Shared context for all stories
    }
```

**Rendering**:
- Each epic doc includes a "## Shared Context" section that references the library
- Links to the shared doc (e.g., "See [Architecture Context](../ARCHITECTURE_CONTEXT.md)")
- Reduces per-doc repetition

**Pattern 3: Section Anchoring & Cross-References**
Instead of repeating content, use anchor-based references:

```markdown
# Epic 65.1 — Memory Stats Dashboard

## Goal

(See [Epic 65 Goal](#epic-65-goal))

This story specializes that goal for dashboard implementation.

## Dependencies

- Epic 65: Memory Best Practices (parent)
- [Architecture Context](#shared-architecture-context) — storage layer required
```

**Current SmartMerger already supports markers; enhance it:**
- Markers can point to external files: `<!-- docsmcp:inherit:file=../SHARED.md:section=architecture -->`
- SmartMerger resolves and inlines on merge

### Recommended additions to docs-mcp:

**Update `StoryConfig`**:
```python
inherit_from_epic: bool = False
goal_override: str = ""  # If provided, use; else inherit or leave empty
shared_section_keys: list[str] = []  # Which shared sections to reference
```

**Update `EpicGenerator` & `StoryGenerator`**:
- Add method: `_render_inherited_section(parent: EpicConfig, section: str)`
- In story rendering, check `inherit_from_epic` and render reference instead of placeholder

**New pattern for series generation:**
```python
class DocumentSeries:
    def generate_with_deduplication(self, epics: list[EpicConfig]) -> dict[str, str]:
        # Returns {filename: content} with cross-references instead of duplication
        shared = self._extract_shared_sections(epics)
        # ... generate each epic, use inherit_from_epic=True for stories
```

---

## 5. SUCCESS METRICS AND STAKEHOLDER SECTIONS

### Current Implementation
Epics have acceptance criteria but no success metrics or stakeholder tracking.

### 2026 Best Practice: Metrics-Driven Planning

**Pattern 1: Success Metrics Framework**
Integrate metrics aligned with OKRs:

```python
class SuccessMetric(BaseModel):
    name: str  # E.g., "Memory hit rate"
    target: str  # E.g., ">80%"
    baseline: str = ""  # Current state: "45%"
    measurement_method: str  # How to measure: "Log cache.hit / cache.attempts"
    owner: str = ""  # Who owns this metric?
    tracking_frequency: str = "weekly"  # "daily", "weekly", "quarterly"
    acceptance_threshold: str = "75%"  # Pass if target >= this
```

**Rendering in epic**:
```markdown
## Success Metrics

| Metric | Baseline | Target | Owner | Measurement | Freq |
|--------|----------|--------|-------|-------------|------|
| Memory hit rate | 45% | >80% | [Memory PM] | Log cache.hit / cache.attempts | weekly |
| Query latency p99 | 450ms | <200ms | [Perf team] | Load test (k6) | post-release |
```

**Pattern 2: Stakeholder & RACI Matrix**
Clarify roles to prevent "nobody owns this":

```python
class StakeholderRole(BaseModel):
    stakeholder: str  # "Platform PM", "Security lead", "Infra team"
    role: str  # "Responsible" (does work), "Accountable" (final say),
               # "Consulted" (asked for input), "Informed" (kept updated)
    story_ids: list[str] = []  # Which stories they own
```

**Rendering**:
```markdown
## Stakeholder Roles & RACI

| Stakeholder | Role | Involved In Stories |
|-------------|------|-------------------|
| Platform PM | Accountable | 65.1, 65.2, 65.3 |
| Security Lead | Consulted | 65.1 (risk), 65.4 (auth) |
| Infra Team | Responsible | 65.6 (federation deployment) |
```

**Pattern 3: Success Definition Hierarchy**
Multiple levels of success (ambitious → guaranteed):

```python
class SuccessDefinition(BaseModel):
    # MVP (must-have for success)
    mvp_criteria: list[str]  # E.g., ["Hybrid search working", "Consolidation active"]

    # Expected (likely outcome)
    expected_outcomes: list[str]  # E.g., [">70% memory hit rate", "Token savings visible"]

    # Ambitious (stretch goal)
    ambitious_targets: list[str]  # E.g., [">85% hit rate", "50% token reduction"]
```

**Rendering**:
```markdown
## Success Definition

### MVP (Required)
- [ ] Hybrid BM25 + vector search integrated
- [ ] Memory consolidation auto-runs

### Expected Outcomes
- [ ] Memory hit rate > 70%
- [ ] Query latency improved 20%

### Ambitious (Stretch)
- [ ] Memory hit rate > 85%
- [ ] 50% token reduction in retrieval
```

### Recommended additions to docs-mcp:

**Update `EpicConfig`**:
```python
success_metrics: list[SuccessMetric] = []
stakeholders: list[StakeholderRole] = []
success_definition: SuccessDefinition = SuccessDefinition()
```

**New rendering methods**:
- `_render_success_metrics()`
- `_render_stakeholders_raci()`
- `_render_success_definition()`

---

## 6. INVEST CHECKLIST AUTO-ASSESSMENT

### Current Implementation
`stories.py` renders a static INVEST checklist:
```markdown
## INVEST Checklist

- [ ] **I**ndependent — Can be developed independently
- [ ] **N**egotiable — Details can be refined
- [ ] **V**aluable — Delivers value
- [ ] **E**stimable — Team can estimate
- [ ] **S**mall — Completable in one sprint
- [ ] **T**estable — Has clear criteria
```

No validation or pre-filling of INVEST criteria.

### 2026 Best Practice: Auto-Assessment with Signals

**Pattern: INVEST Signal Detection**

For each INVEST criterion, detect signals from story config:

```python
INVEST_SIGNALS = {
    "Independent": {
        "positive": [
            "no dependencies",
            "no external blockers",
            "can start immediately",
        ],
        "negative": [
            "depends on",
            "blocked by",
            "must wait for",
        ],
        "signal_score": 0.0,  # 0.0-1.0, auto-assessed
    },
    "Negotiable": {
        "positive": [
            "flexible acceptance criteria",
            "configurable",
            "phased approach",
        ],
        "negative": [
            "fixed in stone",
            "non-negotiable",
            "exact requirements",
        ],
    },
    "Valuable": {
        "positive": [
            "impacts user",
            "business value",
            "customer-facing",
            "reduces toil",
        ],
        "negative": [
            "internal-only",
            "nice-to-have",
            "low impact",
        ],
    },
    "Estimable": {
        "positive": [
            "clear definition",
            "precedent in codebase",
            "known technology",
            "points assigned",
        ],
        "negative": [
            "vague",
            "novel",
            "experimental",
            "points TBD",
        ],
    },
    "Small": {
        "positive": [
            "points <= 5",
            "< 1 week",
            "single feature",
        ],
        "negative": [
            "points > 8",
            "> 2 weeks",
            "multiple features",
            "refactor",
        ],
    },
    "Testable": {
        "positive": [
            "acceptance criteria provided",
            "test cases defined",
            "> 2 ACs",
        ],
        "negative": [
            "no criteria",
            "vague criteria",
            "< 1 AC",
        ],
    },
}
```

**Implementation approach:**

```python
class INVESTAssessment(BaseModel):
    criterion: str  # "Independent", "Negotiable", etc.
    signal_score: float  # 0.0-1.0
    confidence: float  # How confident in this assessment?
    signals_found: list[str]  # Positive signals detected
    signals_missing: list[str]  # Negative signals
    recommendation: str  # "PASS" / "REVIEW" / "FAIL"
    notes: str = ""

def assess_story_against_invest(config: StoryConfig) -> list[INVESTAssessment]:
    """Scan story config and return INVEST assessment."""
    assessments = []

    # Independence: check dependencies field
    independent_score = 1.0 - (len(config.dependencies) * 0.2)
    assessments.append(INVESTAssessment(
        criterion="Independent",
        signal_score=max(0, independent_score),
        signals_missing=["Story depends on " + d for d in config.dependencies],
        recommendation="PASS" if not config.dependencies else "REVIEW",
    ))

    # Estimable: check if points assigned
    estimable_score = 1.0 if config.points > 0 else 0.3
    assessments.append(INVESTAssessment(
        criterion="Estimable",
        signal_score=estimable_score,
        signals_missing=["Points not assigned"] if not config.points else [],
        recommendation="PASS" if config.points else "REVIEW",
    ))

    # Testable: check acceptance criteria
    testable_score = min(1.0, len(config.acceptance_criteria) / 3.0)  # 3+ ACs = full score
    assessments.append(INVESTAssessment(
        criterion="Testable",
        signal_score=testable_score,
        signals_missing=["< 2 acceptance criteria"],
        recommendation="PASS" if len(config.acceptance_criteria) >= 2 else "REVIEW",
    ))

    # ... similar for other criteria

    return assessments
```

**Rendering pattern:**
```python
def _render_invest_checklist_with_assessment(
    self, config: StoryConfig
) -> list[str]:
    """Render INVEST checklist with auto-assessment checkmarks and notes."""
    assessments = assess_story_against_invest(config)

    lines = [
        "<!-- docsmcp:start:invest -->",
        "## INVEST Checklist",
        "",
        "| Criterion | Score | Status | Notes |",
        "|-----------|-------|--------|-------|",
    ]

    for assess in assessments:
        status = "✓ PASS" if assess.recommendation == "PASS" else "⚠ REVIEW"
        score = f"{assess.signal_score:.0%}"
        notes_text = "; ".join(assess.signals_missing) if assess.signals_missing else "Good"
        lines.append(f"| {assess.criterion} | {score} | {status} | {notes_text} |")

    lines.extend(["", "<!-- docsmcp:end:invest -->", ""])
    return lines
```

**Pattern 2: INVEST Compliance Report**
Generate a summary:

```
Overall INVEST Score: 78/100
- 4/6 criteria PASS
- 2/6 criteria REVIEW (Negotiable, Small)

Recommendations:
1. Story too large (10 points) for single sprint — consider split into 65.4a (core) + 65.4b (optional)
2. Stakeholder flexibility unclear — align with PM on scope negotiability
```

### Recommended additions to docs-mcp:

**New module**: `generators/invest_assessor.py`
- `INVESTAssessment` model
- `StoryINVESTValidator` class
- `assess_story_against_invest(config: StoryConfig) -> list[INVESTAssessment]`

**Update `StoryConfig`**:
```python
auto_assess_invest: bool = True
invest_assessments: list[INVESTAssessment] = []  # Populated by validator
```

**Update `StoryGenerator._render_invest_checklist()`**:
```python
def _render_invest_checklist(self, config: StoryConfig) -> list[str]:
    if config.auto_assess_invest:
        return self._render_invest_checklist_with_assessment(config)
    else:
        return self._render_invest_checklist_static()  # Current impl
```

---

## 7. IMPLEMENTATION PRIORITY & EFFORT ESTIMATES

### Quick Wins (1-2 weeks)
1. **Success Metrics in Epics** — Add fields to `EpicConfig`, new rendering method
   - LOE: 2-3 days
   - Value: High (aligns with Epic 65 documentation pattern)

2. **Risk Auto-Classification** — Keyword mapping + risk matrix
   - LOE: 3-4 days
   - Value: High (reduces manual risk assessment overhead)

3. **INVEST Auto-Assessment** — Signal detection + checklist rendering
   - LOE: 3-4 days
   - Value: Medium (quality gate before story implementation)

### Medium Effort (2-4 weeks)
4. **Test Case Generation from ACs** — AC-to-test-name derivation + pairing
   - LOE: 1 week
   - Value: High (reduces test planning time, ensures coverage)

5. **Stakeholder & RACI Matrix** — Add to `EpicConfig`, rendering
   - LOE: 3-4 days
   - Value: Medium (clarity on roles, prevents ownership gaps)

6. **Story Inheritance from Epic** — Shared section deduplication
   - LOE: 3-5 days
   - Value: Medium (DRY principle, easier updates)

### Larger Initiatives (1+ months)
7. **Epic Series with Shared Sections** — DocumentSeries class, cross-reference links
   - LOE: 2-3 weeks
   - Value: High (enables large multi-story planning docs)

### Optional (Future)
- **Placeholder Style Customization** — `include_empty_sections`, `placeholder_style` enum
- **AC-to-Gherkin Automatic Expansion** — Enhanced Gherkin rendering with more context
- **Metric Tracking Integration** — Link success metrics to actual measurement data (requires tapps integration)

---

## 8. INTEGRATION WITH EXISTING DOCS-MCP PATTERNS

### SmartMerger Compatibility
All new sections should follow existing marker pattern:
```markdown
<!-- docsmcp:start:section-name -->
## Section Name
...content...
<!-- docsmcp:end:section-name -->
```

This allows human edits to be preserved across regenerations.

### Auto-Populate Enrichment Pattern
Follow existing pattern in `epics.py._auto_populate()`:
- Try to enrich from project analyzers (metadata, module map, git, experts)
- Fail gracefully: log at debug level, don't break generation
- Return dict with optional keys — only include if enrichment succeeded

### Expert Consultation Pattern
Current: 8 expert domains queried (security, architecture, testing, performance, DevOps, code-quality, API-design, observability)

New patterns should:
- Consult experts for domain-specific guidance (e.g., ask "testing" expert about test strategy)
- Filter guidance by confidence >= 0.3
- Extract first meaningful paragraph (skip markdown headers)
- Cache results to avoid repeated calls

### Type Hints & Validation
Maintain 100% type hints per CLAUDE.md:
- Use Pydantic v2 BaseModel for all config classes
- Use `from __future__ import annotations` at top
- Run `mypy --strict` on all new modules

---

## 9. REFERENCES & RESEARCH SOURCES

**2026 Memory & Planning Research:**
- Epic 65 best practices (TappMCP repo): `docs/planning/EPIC-65-MEMORY-2026-BEST-PRACTICES.md`
- Zylos AI Agent Memory Systems 2026 (reference in Epic 65)
- Neuronex: Agent Memory Without Creepy or Wrong
- Mem0 architecture (26% accuracy boost, 90% token savings via consolidation)
- OpenClaw auto-recall/auto-capture hook patterns

**Agile & Planning Best Practices:**
- INVEST criteria (User Stories Applied by Mike Cohn)
- RACI matrix (Project Management Institute)
- Risk matrix (ISO 31000)
- Success metrics frameworks (OKR-aligned planning)

**Doc Generation Best Practices:**
- SmartMerger pattern (docs-mcp precedent)
- DRY principle for generated docs
- Placeholder strategy (never emit empty sections)

---

## Summary

**Key 2026 Recommendations for docs-mcp:**

1. **Metrics-Driven**: Add success metrics to epics with OKR alignment
2. **Risk-Aware**: Auto-classify risks from keywords; use standard 3x3/5x5 matrix
3. **Test-Focused**: Generate test names from ACs; create AC-test pairing matrix
4. **DRY Documentation**: Story inheritance from epic; shared section libraries
5. **Clarity on Roles**: RACI matrices for stakeholders; prevents ownership gaps
6. **Quality Gates**: INVEST auto-assessment with signals; flag risky stories early
7. **Never Empty**: Actionable placeholders, not generic "Define X"

**Estimated total LOE for full implementation**: 4-6 weeks (phased in priority order)

**Immediate next step**: Implement success metrics + risk auto-classification (quick wins, high value)
