# Epic 57: Adaptive Business Domain Learning

**Status:** Complete
**Priority:** P1 — High (closes feedback loop on Epic 43-45 business expert system)
**Estimated LOE:** ~2 weeks (1 developer)
**Dependencies:** Epic 43-45 (Business Expert Foundation/Consultation/Lifecycle) — Complete

---

## Problem Statement

The business expert system (Epics 43-45) allows projects to define custom business-domain experts via `.tapps-mcp/experts.yaml`. However, the `AdaptiveDomainDetector` currently only learns routing for **technical domains** (the 17 built-in experts). Business domain queries rely solely on static keyword matching, which means:

1. Feedback on business expert consultations doesn't improve future routing
2. Projects with custom experts don't benefit from adaptive learning
3. The system can't learn project-specific terminology for business domains

---

## Goals

1. Extend `AdaptiveDomainDetector` to learn routing for business domains
2. Persist business domain feedback alongside technical domain feedback
3. Apply the 0.4 confidence threshold consistently across both domain types
4. Maintain separation between built-in and project-specific learned weights

## Non-Goals

- Sharing learned weights across projects (each project learns independently)
- Modifying the business expert YAML schema
- Changing the underlying feedback mechanism

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Business domain routing accuracy after 10 feedback samples | 70%+ |
| Feedback persistence for business domains | 100% |
| No regression in technical domain routing | Existing accuracy maintained |
| Test coverage | 80%+ for modified modules |

---

## Technical Approach

### Current State

```python
# adaptive/scoring_engine.py
class AdaptiveDomainDetector:
    def detect(self, question: str) -> tuple[str, float]:
        # Uses learned weights from feedback
        # Only considers BUILTIN_DOMAINS

# experts/domain_detector.py  
class DomainDetector:
    def detect_from_question_merged(self, question: str) -> tuple[str, float]:
        # Static keyword matching for both builtin + business
        # No learning
```

### Target State

```python
# adaptive/scoring_engine.py
class AdaptiveDomainDetector:
    def detect(self, question: str, include_business: bool = True) -> tuple[str, float]:
        # Uses learned weights from feedback
        # Considers BUILTIN_DOMAINS + business domains when include_business=True
        # Business domain weights stored separately in persistence

# experts/domain_detector.py
class DomainDetector:
    def detect_from_question_merged(self, question: str) -> tuple[str, float]:
        # Delegates to AdaptiveDomainDetector when adaptive.enabled
        # Falls back to static matching otherwise
```

### Persistence Schema

```yaml
# .tapps-mcp/adaptive/domain_weights.yaml (existing)
technical:
  security: { weight: 1.2, samples: 45 }
  testing-strategies: { weight: 0.9, samples: 32 }
  ...

# NEW section
business:
  acme-billing: { weight: 1.1, samples: 8 }
  acme-compliance: { weight: 0.8, samples: 5 }
  ...
```

---

## Stories

### 57.1 — Business Domain Weight Storage

**Points:** 3

Extend `adaptive/persistence.py` to store business domain weights separately:
- New `business_weights` section in persistence file
- `save_business_weight(domain: str, weight: float, samples: int)`
- `load_business_weights() -> dict[str, WeightEntry]`
- Migration: existing files get empty `business` section

**Acceptance Criteria:**
- [ ] Business weights stored separately from technical
- [ ] Backward compatible with existing persistence files
- [ ] 15+ unit tests

### 57.2 — AdaptiveDomainDetector Business Support

**Points:** 5

Extend `AdaptiveDomainDetector` to consider business domains:
- Add `include_business: bool = True` parameter to `detect()`
- Load business domains from `ExpertRegistry.get_all_business_experts()`
- Apply same confidence threshold (0.4) and fallback logic
- Weight updates for business domains go to business section

**Acceptance Criteria:**
- [ ] `detect()` considers business domains when `include_business=True`
- [ ] Business domain weights loaded from correct persistence section
- [ ] Confidence threshold applies uniformly
- [ ] 25+ unit tests

### 57.3 — Feedback Integration

**Points:** 3

Update `tapps_feedback` to route business domain feedback correctly:
- Detect if feedback target is business vs technical domain
- Store weight update in appropriate section
- Include domain type in feedback response

**Acceptance Criteria:**
- [ ] Feedback for business experts updates business weights
- [ ] Feedback for technical experts updates technical weights
- [ ] Response includes `domain_type: "business" | "technical"`
- [ ] 10+ unit tests

### 57.4 — DomainDetector Delegation

**Points:** 2

Update `DomainDetector.detect_from_question_merged()` to delegate:
- When `adaptive.enabled` and business domains exist, use `AdaptiveDomainDetector`
- Fall back to static keyword matching otherwise
- Log when adaptive routing overrides static routing

**Acceptance Criteria:**
- [ ] Delegation works when adaptive enabled
- [ ] Fallback works when adaptive disabled
- [ ] Logging shows routing decision source
- [ ] 10+ unit tests

### 57.5 — Documentation & AGENTS.md

**Points:** 1

Update documentation:
- AGENTS.md: Note that business experts benefit from adaptive learning
- Expert system docs: Explain feedback loop for custom experts

**Acceptance Criteria:**
- [ ] AGENTS.md mentions adaptive business learning
- [ ] Expert docs updated

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Business domain name collisions with technical | Low | Medium | Prefix business domains with project identifier |
| Slow convergence with few samples | Medium | Low | Document minimum feedback needed; lower initial threshold |
| Persistence file growth | Low | Low | Periodic cleanup of low-sample domains |

---

## Open Questions

1. Should business domain weights be shareable across projects (e.g., org-level)?
2. Should there be a minimum sample count before adaptive routing activates?
3. Should the confidence threshold differ for business vs technical domains?

---

## References

- Epic 43: Business Expert Foundation
- Epic 44: Business Expert Consultation
- Epic 45: Business Expert Lifecycle
- `adaptive/scoring_engine.py` — `AdaptiveDomainDetector`
- `experts/domain_detector.py` — `DomainDetector`
