# Docs-MCP 2026 Best Practices Research — Executive Summary

## Research Overview
Comprehensive analysis of 2026 best practices for docs-mcp planning document generators (epics, stories, PRDs) across 6 domains.

**Completion Date**: 2026-03-09
**Full Report**: `docs-mcp-2026-best-practices.md`

---

## Key Findings

### 1. Current State: Strong Foundation
docs-mcp already implements good patterns:
- ✓ Two-style variants (standard/comprehensive)
- ✓ SmartMerger for human-edit preservation
- ✓ Auto-populate enrichment from analyzers
- ✓ Expert consultation integration
- ✓ Risk assessment table (manual classification only)

### 2. Top Opportunities (2026)

| Area | 2026 Gap | Recommended Solution | Effort | Impact |
|------|----------|----------------------|--------|--------|
| **Metrics** | Epics lack OKR-aligned success metrics | Add `success_metrics: list[SuccessMetric]` with target/baseline/owner | 2-3d | High |
| **Risk** | Manual risk classification | Auto-detect risks from keywords; classify by 3x3 matrix | 3-4d | High |
| **Tests** | ACs disconnected from test planning | Auto-generate test names from ACs; AC-test pairing matrix | 1w | High |
| **Roles** | No stakeholder/RACI tracking | Add RACI matrix section showing who owns what | 3-4d | Medium |
| **DRY** | Epic/story duplication | Story inheritance from epic; shared section library | 3-5d | Medium |
| **Quality** | No story quality validation | INVEST auto-assessment with signal detection | 3-4d | Medium |

---

## Highest Priority: Quick Wins (Start Here)

### 1. Success Metrics in Epics (2-3 days)
**What**: Add fields to `EpicConfig` for quantifiable success metrics.

**Example**:
```python
success_metrics: list[SuccessMetric] = [
    SuccessMetric(
        name="Memory hit rate",
        baseline="45%",
        target=">80%",
        owner="Platform PM",
        measurement_method="Log cache.hit / cache.attempts"
    )
]
```

**Rendering**: New "## Success Metrics" table after "## Acceptance Criteria"

**Why**: Epic 65 (Memory 2026) and other planning docs increasingly require metrics tied to outcomes. Enables OKR-aligned planning.

---

### 2. Risk Auto-Classification (3-4 days)
**What**: Detect risks from keywords; use standard 3x3 probability/impact matrix.

**Example**:
```python
RISK_KEYWORDS = {
    "encryption": {"probability": "high", "impact": "high"},
    "migration": {"probability": "high", "impact": "high"},
    "deprecated": {"probability": "high", "impact": "medium"},
    ...
}
```

**Rendering**: Risk Assessment table with color-coding by score (green/yellow/orange/red)

**Why**: Reduces manual effort; standardizes risk classification across epics; flags blockers early.

---

### 3. INVEST Auto-Assessment (3-4 days)
**What**: Scan story config for INVEST signals; pre-fill checklist with recommendations.

**Example**:
```
| Criterion | Score | Status | Notes |
|-----------|-------|--------|-------|
| Independent | 100% | ✓ PASS | No dependencies |
| Small | 60% | ⚠ REVIEW | 10 points > sprint capacity |
| Testable | 100% | ✓ PASS | 4 acceptance criteria |
```

**Why**: Quality gate before dev; early detection of oversized/vague stories.

---

## Medium Priority (2-4 weeks)

### 4. Test Case Generation from Acceptance Criteria
Transform ACs → test names. Example:
```
AC: "Login form validates empty email"
  → test_login_form_rejects_empty_email()

AC: "Memory consolidation reduces entry count by >30%"
  → test_memory_consolidation_exceeds_30_percent_reduction()
```

**Implementation**: New `generators/test_case_generator.py` module

---

### 5. Stakeholder & RACI Matrix
Show who's Responsible, Accountable, Consulted, Informed for each story.

**Example**:
| Stakeholder | Role | Stories |
|---|---|---|
| Platform PM | Accountable | 65.1, 65.2, 65.3 |
| Security | Consulted | 65.1, 65.4 |

---

### 6. Story Inheritance from Epic
Reduce duplication: stories can inherit goal, motivation from parent epic.

```python
inherit_from_epic: bool = True  # Story references epic goal instead of repeating
```

---

## Implementation Checklist

**Phase 1 — Quick Wins (1-2 weeks)**
- [ ] Add `SuccessMetric` model to `EpicConfig`
- [ ] Implement `RiskClassifier` with keyword detection
- [ ] Add `INVEST_SIGNALS` detection + assessment rendering
- [ ] Update `EpicGenerator` and `StoryGenerator` to use new fields

**Phase 2 — Medium Effort (2-4 weeks)**
- [ ] Create `test_case_generator.py` module
- [ ] Add `StakeholderRole` + RACI rendering to `EpicConfig`
- [ ] Implement story inheritance pattern in `StoryGenerator`

**Phase 3 — Larger Initiatives (future)**
- [ ] Epic series with shared sections
- [ ] Placeholder style customization
- [ ] Metric tracking integration

---

## File Structure to Preserve

All new patterns must maintain:
1. **SmartMerger markers**: `<!-- docsmcp:start:section -->` / `<!-- docsmcp:end:section -->`
2. **Type hints**: 100% Pydantic v2 models, `mypy --strict`
3. **Graceful fallback**: Enrichment failures are logged, not fatal
4. **Expert integration**: Consult domains on semantic guidance (security, testing, etc.)

---

## Research Validation

**Sources reviewed:**
- Current docs-mcp implementation: `epics.py`, `stories.py`, `specs.py`
- Epic planning doc: `EPIC-65-MEMORY-2026-BEST-PRACTICES.md`
- Test coverage: `test_epics.py`, `test_stories.py` (130+ tests)
- SmartMerger pattern: `smart_merge.py` (robust section preservation)
- Project metadata extraction: `metadata.py` (3-format support)

**Validation against 2026 standards:**
- Risk matrix: ISO 31000 standard (3x3 / 5x5)
- RACI: PMI project management framework
- INVEST: Agile user story framework (Cohn)
- Success metrics: OKR alignment best practice
- Test generation: Industry pattern (AC → test name)

---

## Next Steps

1. **Start Phase 1**: Begin with success metrics + risk classification (high impact, quick to implement)
2. **Validate with Epic 65**: Pilot new features on Memory 2026 planning doc
3. **Iterate**: Gather feedback from planning doc users
4. **Scale to Phase 2**: Expand to test generation + INVEST assessment

---

## Related Artifacts

- Full research report: `/c/cursor/TappMCP/.claude/agent-memory/tapps-researcher/docs-mcp-2026-best-practices.md`
- Epic 65 planning: `docs/planning/EPIC-65-MEMORY-2026-BEST-PRACTICES.md`
- Current implementation: `packages/docs-mcp/src/docs_mcp/generators/`
- Tests: `packages/docs-mcp/tests/unit/test_epics.py`, `test_stories.py`
