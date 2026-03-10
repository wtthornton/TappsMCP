# Docs-MCP 2026 Best Practices — Implementation Specification

## Document Purpose
Technical specification for implementing 2026 best practices in docs-mcp generators. Includes code structure, type definitions, and integration patterns.

---

## 1. SUCCESS METRICS FEATURE

### 1.1 New Models (add to `generators/epics.py`)

```python
class SuccessMetric(BaseModel):
    """A quantifiable success metric for an epic."""
    name: str  # E.g., "Memory hit rate"
    target: str  # E.g., ">80%"
    baseline: str = ""  # E.g., "45%"
    measurement_method: str  # E.g., "Log cache.hit / cache.attempts"
    owner: str = ""  # E.g., "Platform PM"
    tracking_frequency: str = "weekly"  # "daily", "weekly", "quarterly"
    acceptance_threshold: str = ""  # Pass if target >= this, else optional

class SuccessDefinition(BaseModel):
    """Three-tier success definition."""
    mvp_criteria: list[str] = []  # Must-haves
    expected_outcomes: list[str] = []  # Likely outcomes
    ambitious_targets: list[str] = []  # Stretch goals
```

### 1.2 Update EpicConfig

```python
class EpicConfig(BaseModel):
    # ... existing fields ...
    success_metrics: list[SuccessMetric] = []
    success_definition: SuccessDefinition = Field(default_factory=SuccessDefinition)
```

### 1.3 New Rendering Method

```python
def _render_success_metrics(self, config: EpicConfig) -> list[str]:
    """Render the Success Metrics section."""
    lines = [
        "<!-- docsmcp:start:success-metrics -->",
        "## Success Metrics",
        "",
    ]

    if config.success_metrics:
        lines.extend([
            "| Metric | Baseline | Target | Owner | Measurement | Frequency |",
            "|--------|----------|--------|-------|-------------|-----------|",
        ])
        for metric in config.success_metrics:
            baseline = metric.baseline or "—"
            owner = metric.owner or "TBD"
            freq = metric.tracking_frequency
            lines.append(
                f"| {metric.name} | {baseline} | {metric.target} | {owner} | "
                f"{metric.measurement_method} | {freq} |"
            )
    else:
        lines.append("Define quantifiable success metrics (e.g., performance targets, adoption rates)...")

    lines.extend(["", "<!-- docsmcp:end:success-metrics -->", ""])
    return lines
```

### 1.4 Integration in generate()

```python
def generate(self, config: EpicConfig, *, project_root: Path | None = None, auto_populate: bool = False) -> str:
    # ... existing setup ...

    lines.extend(self._render_acceptance_criteria(config))
    lines.extend(self._render_success_metrics(config))  # ADD THIS
    lines.extend(self._render_stories(config))

    # ... rest ...
```

### 1.5 Testing Pattern

```python
def test_success_metrics_rendered(self) -> None:
    metrics = [
        SuccessMetric(name="Hit rate", target=">80%", baseline="45%", owner="PM"),
    ]
    config = _make_config(success_metrics=metrics)
    content = self.gen.generate(config)
    assert "## Success Metrics" in content
    assert "Hit rate" in content
    assert ">80%" in content
    assert "45%" in content

def test_success_metrics_placeholder(self) -> None:
    config = _make_config(success_metrics=[])
    content = self.gen.generate(config)
    assert "Define quantifiable success metrics" in content
```

---

## 2. RISK AUTO-CLASSIFICATION FEATURE

### 2.1 New Module: `generators/risk_classifier.py`

```python
"""Risk classification and assessment from natural language."""

from __future__ import annotations

from enum import Enum
from typing import ClassVar

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class RiskProbability(str, Enum):
    """Risk probability levels."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class RiskImpact(str, Enum):
    """Risk impact levels."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class RiskCategory(str, Enum):
    """Risk category."""
    SECURITY = "security"
    PERFORMANCE = "performance"
    COMPATIBILITY = "compatibility"
    ARCHITECTURE = "architecture"
    DEPENDENCY = "dependency"
    VENDOR = "vendor"
    ORGANIZATIONAL = "organizational"


class RiskAssessment(BaseModel):
    """Auto-assessed risk classification."""
    description: str
    category: RiskCategory
    probability: RiskProbability
    impact: RiskImpact
    mitigation: str = ""  # User-provided mitigation
    owner: str = ""
    confidence: float = 0.0  # 0.0-1.0, based on keyword match strength


class RiskClassifier:
    """Detects and classifies risks from keywords."""

    RISK_KEYWORDS: ClassVar[dict[str, dict[str, str]]] = {
        # Security
        "encryption": {"category": "security", "probability": "High", "impact": "High"},
        "token": {"category": "security", "probability": "High", "impact": "High"},
        "auth": {"category": "security", "probability": "Medium", "impact": "High"},
        "api-key": {"category": "security", "probability": "High", "impact": "High"},
        "injection": {"category": "security", "probability": "Medium", "impact": "High"},
        "breach": {"category": "security", "probability": "Medium", "impact": "Critical"},
        "vulnerable": {"category": "security", "probability": "High", "impact": "High"},

        # Performance
        "database": {"category": "performance", "probability": "Medium", "impact": "Medium"},
        "migration": {"category": "performance", "probability": "High", "impact": "High"},
        "scaling": {"category": "performance", "probability": "Medium", "impact": "High"},
        "network": {"category": "performance", "probability": "Medium", "impact": "Medium"},
        "latency": {"category": "performance", "probability": "Medium", "impact": "Medium"},

        # Compatibility
        "deprecated": {"category": "compatibility", "probability": "High", "impact": "Medium"},
        "breaking": {"category": "compatibility", "probability": "High", "impact": "High"},

        # Dependency
        "dependency": {"category": "dependency", "probability": "Medium", "impact": "Medium"},
        "external": {"category": "dependency", "probability": "Medium", "impact": "High"},

        # Architecture
        "refactor": {"category": "architecture", "probability": "Medium", "impact": "Medium"},
        "redesign": {"category": "architecture", "probability": "Low", "impact": "High"},
    }

    def classify(self, text: str) -> RiskAssessment | None:
        """Classify a risk description from keywords.

        Returns RiskAssessment if keywords found, else None.
        """
        text_lower = text.lower()

        for keyword, props in self.RISK_KEYWORDS.items():
            if self._word_boundary_match(text_lower, keyword):
                return RiskAssessment(
                    description=text,
                    category=RiskCategory(props["category"]),
                    probability=RiskProbability(props["probability"]),
                    impact=RiskImpact(props["impact"]),
                    confidence=0.7,  # Keyword match confidence
                )

        return None

    @staticmethod
    def _word_boundary_match(text: str, keyword: str) -> bool:
        """Match keyword with word boundaries."""
        import re
        pattern = rf"\b{re.escape(keyword)}\b"
        return bool(re.search(pattern, text, re.IGNORECASE))

    def compute_risk_score(
        self,
        probability: RiskProbability,
        impact: RiskImpact,
    ) -> int:
        """Compute risk score using 3x4 matrix (1-12 scale)."""
        prob_map = {"Low": 1, "Medium": 2, "High": 3}
        impact_map = {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}

        return prob_map[probability.value] * impact_map[impact.value]

    def risk_level(self, score: int) -> str:
        """Risk level from score (1-12)."""
        if score <= 2:
            return "Monitor"
        elif score <= 6:
            return "Mitigate"
        elif score <= 9:
            return "Urgent"
        else:
            return "Blocker"
```

### 2.2 Update `EpicConfig` in `epics.py`

```python
class EpicRisk(BaseModel):
    """An epic risk with probability/impact classification."""
    description: str
    probability: str  # "Low", "Medium", "High"
    impact: str  # "Low", "Medium", "High", "Critical"
    mitigation: str = ""  # How to mitigate
    owner: str = ""  # Who owns this risk?
    auto_detected: bool = False  # Was this detected by RiskClassifier?

class EpicConfig(BaseModel):
    # ... existing fields ...
    risks: list[EpicRisk] = []  # Changed from list[str]
    auto_classify_risks: bool = True  # Auto-detect risks from keywords
```

### 2.3 Update Risk Assessment Rendering

```python
def _render_risk_assessment(
    self,
    config: EpicConfig,
    enrichment: dict[str, Any] | None = None,
) -> list[str]:
    """Render the Risk Assessment section with auto-classification."""
    lines = [
        "<!-- docsmcp:start:risk-assessment -->",
        "## Risk Assessment",
        "",
        "| Risk | Probability | Impact | Score | Mitigation | Owner |",
        "|---|---|---|---|---|---|",
    ]

    classifier = RiskClassifier()
    processed_risks: list[EpicRisk] = []

    # Auto-classify if enabled
    if config.auto_classify_risks and config.risks:
        for risk in config.risks:
            if not isinstance(risk, EpicRisk):
                # Try to auto-classify string risks (backward compat)
                assessment = classifier.classify(str(risk))
                if assessment:
                    processed_risks.append(EpicRisk(
                        description=assessment.description,
                        probability=assessment.probability.value,
                        impact=assessment.impact.value,
                        auto_detected=True,
                    ))
                else:
                    processed_risks.append(EpicRisk(
                        description=str(risk),
                        probability="Medium",
                        impact="Medium",
                    ))
            else:
                processed_risks.append(risk)

    # Render risk rows
    if processed_risks:
        for risk in processed_risks:
            score = classifier.compute_risk_score(
                RiskProbability(risk.probability),
                RiskImpact(risk.impact),
            )
            owner = risk.owner or "TBD"
            mitigation = risk.mitigation or "Define mitigation strategy"
            lines.append(
                f"| {risk.description} | {risk.probability} | {risk.impact} | "
                f"{score}/12 | {mitigation} | {owner} |"
            )
    else:
        lines.append("| Describe potential risks... | Low/Medium/High | Low/Medium/High/Critical | — | Mitigation | Owner |")

    # Expert-identified risks
    expert_guidance = (enrichment or {}).get("expert_guidance", [])
    risk_domains = {"security", "performance", "devops"}
    risk_items = [g for g in expert_guidance if g.get("domain") in risk_domains]
    if risk_items:
        lines.append("")
        lines.append("**Expert-Identified Risks:**")
        lines.append("")
        for item in risk_items:
            lines.append(f"- **{item['expert']}**: {item['advice']}")

    lines.extend(["", "<!-- docsmcp:end:risk-assessment -->", ""])
    return lines
```

### 2.4 Testing Pattern

```python
def test_risk_classification_security(self) -> None:
    classifier = RiskClassifier()
    assessment = classifier.classify("Encryption key rotation required")
    assert assessment is not None
    assert assessment.category == RiskCategory.SECURITY
    assert assessment.probability == RiskProbability.HIGH
    assert assessment.impact == RiskImpact.HIGH

def test_risk_score_computation(self) -> None:
    classifier = RiskClassifier()
    score = classifier.compute_risk_score(RiskProbability.HIGH, RiskImpact.HIGH)
    assert score == 9  # 3 * 3

def test_epic_with_auto_classified_risks(self) -> None:
    risks = [
        EpicRisk(description="Database migration required", auto_detected=False),
    ]
    config = _make_config(risks=risks, auto_classify_risks=True)
    content = self.gen.generate(config)
    assert "## Risk Assessment" in content
    assert "Database migration" in content
    # Should auto-classify as High/High probability
    assert "High" in content
```

---

## 3. INVEST AUTO-ASSESSMENT FEATURE

### 3.1 New Module: `generators/invest_assessor.py`

```python
"""INVEST checklist auto-assessment from story configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from stories import StoryConfig

logger = structlog.get_logger(__name__)


class INVESTAssessment(BaseModel):
    """Assessment result for one INVEST criterion."""
    criterion: str  # "Independent", "Negotiable", etc.
    signal_score: float  # 0.0-1.0
    confidence: float  # How confident in this assessment? 0.0-1.0
    signals_found: list[str] = []  # Positive signals detected
    signals_missing: list[str] = []  # Red flags
    recommendation: str  # "PASS", "REVIEW", "FAIL"
    notes: str = ""


class StoryINVESTValidator:
    """Validates stories against INVEST criteria."""

    def assess(self, config: StoryConfig) -> list[INVESTAssessment]:
        """Assess a story against all INVEST criteria.

        Returns list of 6 assessments (one per criterion).
        """
        return [
            self._assess_independent(config),
            self._assess_negotiable(config),
            self._assess_valuable(config),
            self._assess_estimable(config),
            self._assess_small(config),
            self._assess_testable(config),
        ]

    @staticmethod
    def _assess_independent(config: StoryConfig) -> INVESTAssessment:
        """Assess independence: can it be developed independently?"""
        signals_missing = []
        if config.dependencies:
            signals_missing.extend([f"Depends on {d}" for d in config.dependencies[:2]])

        score = 1.0 - (len(config.dependencies) * 0.2)
        score = max(0.0, score)

        return INVESTAssessment(
            criterion="Independent",
            signal_score=score,
            confidence=0.9,
            signals_missing=signals_missing,
            recommendation="PASS" if score >= 0.8 else "REVIEW",
        )

    @staticmethod
    def _assess_negotiable(config: StoryConfig) -> INVESTAssessment:
        """Assess negotiability: can details be refined?"""
        # If story has flexible AC and good description, it's negotiable
        signals_found = []
        signals_missing = []

        if config.description:
            signals_found.append("Description provided")

        # Heuristic: many ACs = less negotiable (more locked down)
        if len(config.acceptance_criteria) > 5:
            signals_missing.append("Many ACs (>5) — less room for refinement")

        score = 0.7 if signals_found else 0.4
        if signals_missing:
            score -= 0.2

        return INVESTAssessment(
            criterion="Negotiable",
            signal_score=max(0, score),
            confidence=0.6,
            signals_found=signals_found,
            signals_missing=signals_missing,
            recommendation="PASS" if score >= 0.5 else "REVIEW",
        )

    @staticmethod
    def _assess_valuable(config: StoryConfig) -> INVESTAssessment:
        """Assess value: does it deliver value to user/system?"""
        signals_found = []

        # Heuristic: story title and description should indicate value
        value_keywords = ["user", "customer", "feature", "improve", "reduce", "enable"]
        text = (config.title + " " + config.description).lower()

        for keyword in value_keywords:
            if keyword in text:
                signals_found.append(f"Contains '{keyword}' (value indicator)")

        score = len(signals_found) / len(value_keywords)

        return INVESTAssessment(
            criterion="Valuable",
            signal_score=score,
            confidence=0.7,
            signals_found=signals_found,
            signals_missing=[] if score >= 0.5 else ["No clear user/customer value indicated"],
            recommendation="PASS" if score >= 0.5 else "REVIEW",
        )

    @staticmethod
    def _assess_estimable(config: StoryConfig) -> INVESTAssessment:
        """Assess estimability: can team estimate effort?"""
        signals_found = []
        signals_missing = []

        if config.points and config.points > 0:
            signals_found.append(f"Points assigned: {config.points}")
        else:
            signals_missing.append("No points assigned")

        if config.description:
            signals_found.append("Description provided (helps estimation)")
        else:
            signals_missing.append("No description (hard to estimate)")

        score = len(signals_found) / 2.0

        return INVESTAssessment(
            criterion="Estimable",
            signal_score=score,
            confidence=0.8,
            signals_found=signals_found,
            signals_missing=signals_missing,
            recommendation="PASS" if score >= 0.8 else "REVIEW",
        )

    @staticmethod
    def _assess_small(config: StoryConfig) -> INVESTAssessment:
        """Assess smallness: completable in one sprint?"""
        signals_found = []
        signals_missing = []

        # Heuristic: points <= 5 is small, <= 8 is medium, > 8 is large
        if config.points and config.points <= 5:
            signals_found.append(f"Small point estimate ({config.points})")
            score = 1.0
        elif config.points and config.points <= 8:
            signals_missing.append(f"Medium points ({config.points}) — might span sprints")
            score = 0.6
        else:
            signals_missing.append(f"Large points ({config.points or 'TBD'}) — too big for single sprint")
            score = 0.2

        # Multiple files affected = larger
        if len(config.files) > 3:
            signals_missing.append(f"Many files ({len(config.files)}) — broad impact")
            score -= 0.2

        return INVESTAssessment(
            criterion="Small",
            signal_score=max(0, score),
            confidence=0.8,
            signals_found=signals_found,
            signals_missing=signals_missing,
            recommendation="PASS" if score >= 0.7 else "REVIEW",
        )

    @staticmethod
    def _assess_testable(config: StoryConfig) -> INVESTAssessment:
        """Assess testability: has clear verification criteria?"""
        signals_found = []
        signals_missing = []

        if config.acceptance_criteria:
            count = len(config.acceptance_criteria)
            if count >= 2:
                signals_found.append(f"{count} acceptance criteria")
                score = min(1.0, count / 3.0)  # 3+ ACs = full score
            else:
                signals_missing.append(f"Only {count} AC (need >= 2 for testability)")
                score = 0.3
        else:
            signals_missing.append("No acceptance criteria")
            score = 0.0

        if config.test_cases:
            signals_found.append(f"{len(config.test_cases)} test cases defined")
            score = min(1.0, score + 0.3)

        return INVESTAssessment(
            criterion="Testable",
            signal_score=min(1.0, score),
            confidence=0.9,
            signals_found=signals_found,
            signals_missing=signals_missing,
            recommendation="PASS" if score >= 0.7 else "REVIEW",
        )
```

### 3.2 Update `StoryConfig`

```python
class StoryConfig(BaseModel):
    # ... existing fields ...
    auto_assess_invest: bool = True  # Enable INVEST auto-assessment
    invest_assessments: list[INVESTAssessment] = []  # Populated after assessment
```

### 3.3 Update Story Generator

```python
def generate(self, config: StoryConfig, *, project_root: Path | None = None, auto_populate: bool = False) -> str:
    # ... existing setup ...

    # Run INVEST assessment if enabled
    if config.auto_assess_invest:
        validator = StoryINVESTValidator()
        config.invest_assessments = validator.assess(config)

    # ... render sections ...
    if style == "comprehensive":
        lines.extend(self._render_invest_checklist(config))

def _render_invest_checklist(self, config: StoryConfig) -> list[str]:
    """Render INVEST checklist with auto-assessment if available."""
    lines = [
        "<!-- docsmcp:start:invest -->",
        "## INVEST Checklist",
        "",
    ]

    if config.invest_assessments:
        # Render table with assessments
        lines.extend([
            "| Criterion | Score | Status | Signals |",
            "|-----------|-------|--------|---------|",
        ])
        for assess in config.invest_assessments:
            status = "✓" if assess.recommendation == "PASS" else "⚠"
            score = f"{assess.signal_score:.0%}"
            signals_text = "; ".join(assess.signals_missing) if assess.signals_missing else "Good"
            lines.append(
                f"| {assess.criterion} | {score} | {status} {assess.recommendation} | "
                f"{signals_text} |"
            )
    else:
        # Fall back to static checklist
        lines.extend([
            "- [ ] **I**ndependent — Can be developed independently",
            "- [ ] **N**egotiable — Details can be refined",
            "- [ ] **V**aluable — Delivers value to user/system",
            "- [ ] **E**stimable — Team can estimate effort",
            "- [ ] **S**mall — Completable within one sprint",
            "- [ ] **T**estable — Has clear verification criteria",
        ])

    lines.extend(["", "<!-- docsmcp:end:invest -->", ""])
    return lines
```

### 3.4 Testing Pattern

```python
def test_invest_assessment_independent_no_deps(self) -> None:
    config = _make_config(dependencies=[])
    validator = StoryINVESTValidator()
    assessments = validator.assess(config)

    independent = next(a for a in assessments if a.criterion == "Independent")
    assert independent.signal_score == 1.0
    assert independent.recommendation == "PASS"

def test_invest_assessment_small_large_points(self) -> None:
    config = _make_config(points=13)  # Too large
    validator = StoryINVESTValidator()
    assessments = validator.assess(config)

    small = next(a for a in assessments if a.criterion == "Small")
    assert small.signal_score < 0.5
    assert small.recommendation == "REVIEW"
    assert any("too big" in s for s in small.signals_missing)
```

---

## 4. COMMON PATTERNS

### Import Path Consistency
All new modules should maintain:
```python
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, ClassVar

import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)
```

### Rendering Template
All new section renderers follow:
```python
def _render_section_name(self, config: Config) -> list[str]:
    """Render the Section Name section."""
    lines = [
        "<!-- docsmcp:start:section-name -->",
        "## Section Name",
        "",
    ]

    if config.field:
        # Render real content
        for item in config.field:
            lines.append(f"- {item}")
    else:
        # Render placeholder
        lines.append("Define section content...")

    lines.extend(["", "<!-- docsmcp:end:section-name -->", ""])
    return lines
```

### Graceful Enrichment Fallback
```python
try:
    from some_module import Something
    something = Something()
    enrichment["key"] = something.result()
except Exception:
    logger.debug("enrichment_failed", module="some_module", exc_info=True)
    # Continue — don't break generation
```

---

## 5. INTEGRATION CHECKLIST

### Before Implementation
- [ ] Review CLAUDE.md type hints & linting requirements
- [ ] Check existing test patterns in `test_epics.py` / `test_stories.py`
- [ ] Verify SmartMerger marker compatibility
- [ ] Plan for backward compatibility (string risks → EpicRisk conversion)

### During Implementation
- [ ] Add 100% type hints to all new modules
- [ ] Run `mypy --strict packages/docs-mcp/`
- [ ] Run `ruff check packages/docs-mcp/`
- [ ] Add comprehensive test coverage (>80%)
- [ ] Test SmartMerger with new sections

### After Implementation
- [ ] Update AGENTS.md if new MCP tools added
- [ ] Document new fields in docstrings
- [ ] Test backward compatibility with existing epics
- [ ] Validate against Epic 65 planning doc (pilot)

---

## 6. SUCCESS CRITERIA

| Feature | Implementation Criteria | Test Coverage |
|---------|--------------------------|---|
| Success Metrics | EpicConfig field + rendering | test_success_metrics_* (4+ tests) |
| Risk Classification | RiskClassifier + EpicRisk model | test_risk_classification_* (6+ tests) |
| INVEST Assessment | INVESTAssessment + validator | test_invest_assessment_* (8+ tests) |

---

## 7. File Changes Summary

| File | Change | Type |
|------|--------|------|
| `generators/epics.py` | Add SuccessMetric, update EpicConfig, add rendering | Modify |
| `generators/risk_classifier.py` | NEW module | Create |
| `generators/invest_assessor.py` | NEW module | Create |
| `generators/stories.py` | Update StoryConfig, enhance INVEST rendering | Modify |
| `tests/unit/test_epics.py` | Add success metrics tests | Modify |
| `tests/unit/test_stories.py` | Add INVEST assessment tests | Modify |
| `tests/unit/test_risk_classifier.py` | NEW test file | Create |
| `tests/unit/test_invest_assessor.py` | NEW test file | Create |

---

## 8. Timeline Estimate

- **Risk Classifier**: 2-3 days (single module, clear algorithm)
- **Success Metrics**: 1-2 days (config + rendering method)
- **INVEST Assessor**: 2-3 days (multi-criterion validator)
- **Tests & Integration**: 2-3 days (full coverage, backward compat)

**Total**: 1-2 weeks for all three features (Phase 1)
