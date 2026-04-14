# Story 100.1 -- Architecture pattern classifier

<!-- docsmcp:start:user-story -->

> **As a** docs-mcp maintainer, **I want** a deterministic classifier that labels a project as layered, hexagonal, monolith, microservice, event-driven, or pipeline, **so that** downstream generators can produce pattern-aware output without ad-hoc heuristics scattered across renderers

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 5 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that docs-mcp can name the architectural shape of any codebase, unlocking poster-style diagrams, ADR cross-links, and smarter architecture reports.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Build a pure-Python classifier that consumes ModuleMap + ImportGraph and returns (archetype, confidence, evidence). No LLM, no network. Evidence list cites which heuristic fired.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/docs-mcp/src/docs_mcp/analyzers/pattern.py`
- `packages/docs-mcp/src/docs_mcp/generators/architecture.py`
- `packages/docs-mcp/tests/unit/test_pattern_classifier.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Design ArchetypeResult dataclass (`packages/docs-mcp/src/docs_mcp/analyzers/pattern.py`)
- [ ] Implement 6 heuristic rules (`packages/docs-mcp/src/docs_mcp/analyzers/pattern.py`)
- [ ] Wire into architecture generator (`packages/docs-mcp/src/docs_mcp/generators/architecture.py`)
- [ ] Add unit tests with fixture projects (`packages/docs-mcp/tests/unit/test_pattern_classifier.py`)
- [ ] Benchmark against internal reference repos (`packages/docs-mcp/tests/integration/test_pattern_accuracy.py`)

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

### AC: Given a layered codebase When classifier runs Then returns layered with confidence > 0.7

```gherkin
Feature: given-a-layered-codebase-when-classifier-runs-then-returns-layered-with-confidence-07
  Scenario: Given a layered codebase When classifier runs Then returns layered with confidence > 0.7
    Given a docs-mcp maintainer is ready to perform the action
    When the docs-mcp maintainer a deterministic classifier that labels a project as layered, hexagonal, monolith, microservice, event-driven, or pipeline
    Then Given a layered codebase When classifier runs Then returns layered with confidence > 0.7 successfully
```

### AC: Given a monorepo with 5+ services When classifier runs Then returns microservice

```gherkin
Feature: given-a-monorepo-with-5-services-when-classifier-runs-then-returns-microservice
  Scenario: Given a monorepo with 5+ services When classifier runs Then returns microservice
    Given a docs-mcp maintainer is ready to perform the action
    When the docs-mcp maintainer a deterministic classifier that labels a project as layered, hexagonal, monolith, microservice, event-driven, or pipeline
    Then Given a monorepo with 5+ services When classifier runs Then returns microservice successfully
```

### AC: Given adapters/ and ports/ folders When classifier runs Then returns hexagonal

```gherkin
Feature: given-adapters-and-ports-folders-when-classifier-runs-then-returns-hexagonal
  Scenario: Given adapters/ and ports/ folders When classifier runs Then returns hexagonal
    Given a docs-mcp maintainer is ready to perform the action
    When the docs-mcp maintainer a deterministic classifier that labels a project as layered, hexagonal, monolith, microservice, event-driven, or pipeline
    Then Given adapters/ and ports/ folders When classifier runs Then returns hexagonal successfully
```

### AC: Given ambiguous project When classifier runs Then returns best guess plus alternatives list

```gherkin
Feature: given-ambiguous-project-when-classifier-runs-then-returns-best-guess-plus-alternatives-list
  Scenario: Given ambiguous project When classifier runs Then returns best guess plus alternatives list
    Given a docs-mcp maintainer is ready to perform the action
    When the docs-mcp maintainer a deterministic classifier that labels a project as layered, hexagonal, monolith, microservice, event-driven, or pipeline
    Then Given ambiguous project When classifier runs Then returns best guess plus alternatives list successfully
```

### AC: Given any project When classifier runs Then completes in under 500ms

```gherkin
Feature: given-any-project-when-classifier-runs-then-completes-in-under-500ms
  Scenario: Given any project When classifier runs Then completes in under 500ms
    Given a docs-mcp maintainer is ready to perform the action
    When the docs-mcp maintainer a deterministic classifier that labels a project as layered, hexagonal, monolith, microservice, event-driven, or pipeline
    Then Given any project When classifier runs Then completes in under 500ms successfully
```

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Architecture pattern classifier code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] Documentation updated
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->

<!-- docsmcp:start:test-cases -->
## Test Cases

1. Layered fixture returns layered
2. Hexagonal fixture returns hexagonal
3. Event-driven fixture with kafka imports returns event-driven
4. Tiny script returns monolith
5. Empty project returns unknown with zero confidence

<!-- docsmcp:end:test-cases -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Evidence list must include file paths
- Confidence is deterministic function of rule count
- No external deps beyond existing analyzers
- Expose via docs_api_surface for reuse

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:dependencies -->
## Dependencies

- List stories or external dependencies that must complete first...

<!-- docsmcp:end:dependencies -->

<!-- docsmcp:start:invest -->
## INVEST Checklist

- [x] **I**ndependent -- Can be developed and delivered independently
- [ ] **N**egotiable -- Details can be refined during implementation
- [x] **V**aluable -- Delivers value to a user or the system
- [x] **E**stimable -- Team can estimate the effort
- [x] **S**mall -- Completable within one sprint/iteration
- [x] **T**estable -- Has clear criteria to verify completion

<!-- docsmcp:end:invest -->
