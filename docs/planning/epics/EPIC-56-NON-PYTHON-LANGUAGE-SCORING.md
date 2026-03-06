# Epic 56: Non-Python Language Scoring

**Status:** Proposed
**Priority:** P1 — High (expands addressable market significantly)
**Estimated LOE:** ~3-4 weeks (1 developer)
**Dependencies:** DocsMCP Epic 12 (tree-sitter extractors) — Complete

---

## Problem Statement

TappsMCP's quality scoring tools (`tapps_score_file`, `tapps_quick_check`, `tapps_quality_gate`, `tapps_validate_changed`) only work for Python files. This limits adoption in polyglot codebases and excludes large segments of the developer market (TypeScript/JavaScript, Go, Rust, Java).

DocsMCP already has tree-sitter extractors for TypeScript, Go, Rust, and Java (Epic 12), providing the AST parsing foundation. This epic extends TappsMCP's scoring engine to leverage those extractors.

---

## Goals

1. Score TypeScript/JavaScript files across applicable quality categories
2. Score Go files across applicable quality categories
3. Score Rust files across applicable quality categories
4. Provide language-agnostic quality gate thresholds
5. Maintain backward compatibility with existing Python-only workflows

## Non-Goals

- Java scoring (defer to future epic due to complexity)
- Language-specific linters (eslint, golint, clippy) — future enhancement
- Refactoring existing Python scoring infrastructure

---

## Success Metrics

| Metric | Target |
|--------|--------|
| TypeScript/JS file scoring | 80%+ of Python categories applicable |
| Go file scoring | 70%+ of Python categories applicable |
| Rust file scoring | 70%+ of Python categories applicable |
| Performance | < 2x Python scoring time for equivalent LOC |
| Test coverage | 80%+ for new modules |

---

## Technical Approach

### Category Applicability by Language

| Category | Python | TypeScript | Go | Rust |
|----------|--------|------------|-----|------|
| Complexity | ✅ Cyclomatic | ✅ Cyclomatic | ✅ Cyclomatic | ✅ Cyclomatic |
| Security | ✅ Bandit | ⚠️ AST patterns | ⚠️ AST patterns | ⚠️ AST patterns |
| Maintainability | ✅ Docstrings, types | ✅ JSDoc, types | ✅ Comments, types | ✅ Doc comments |
| Test Coverage | ✅ pytest markers | ✅ Jest patterns | ✅ `_test.go` | ✅ `#[test]` |
| Performance | ✅ AST patterns | ✅ AST patterns | ✅ AST patterns | ✅ AST patterns |
| Structure | ✅ Imports, nesting | ✅ Imports, nesting | ✅ Imports, nesting | ✅ Imports, nesting |
| DevEx | ✅ Naming, clarity | ✅ Naming, clarity | ✅ Naming, clarity | ✅ Naming, clarity |

### Architecture

```
tapps-core/
  scoring/
    scorer.py              # Existing Python scorer
    scorer_base.py         # NEW: Abstract base scorer
    scorer_typescript.py   # NEW: TypeScript/JS scorer
    scorer_go.py           # NEW: Go scorer
    scorer_rust.py         # NEW: Rust scorer
    language_detector.py   # NEW: File extension -> scorer routing

docs-mcp/
  extractors/
    typescript.py          # EXISTING: tree-sitter TypeScript
    go.py                  # EXISTING: tree-sitter Go
    rust.py                # EXISTING: tree-sitter Rust
```

### Integration Points

1. **Language Detection:** `language_detector.py` routes files to appropriate scorer based on extension
2. **Shared Metrics:** Abstract `ScorerBase` defines common interface for all language scorers
3. **DocsMCP Extractors:** Import tree-sitter extractors from docs-mcp for AST parsing
4. **Fallback:** Unknown languages return `{ "supported": false, "message": "..." }`

---

## Stories

### 56.1 — Abstract Scorer Base Class

**Points:** 3

Create `ScorerBase` abstract class that defines the common interface:
- `score(file_path: Path) -> ScoreResult`
- `score_category(file_path: Path, category: str) -> CategoryScore`
- `supported_categories: list[str]`
- `language: str`

Refactor existing `CodeScorer` to inherit from `ScorerBase`.

**Acceptance Criteria:**
- [ ] `ScorerBase` ABC in `scoring/scorer_base.py`
- [ ] `CodeScorer` inherits from `ScorerBase` with no behavior change
- [ ] All existing Python scoring tests pass
- [ ] Type annotations for mypy --strict

### 56.2 — Language Detection & Routing

**Points:** 2

Create `language_detector.py` with:
- `detect_language(file_path: Path) -> str` — returns language identifier
- `get_scorer(file_path: Path) -> ScorerBase` — returns appropriate scorer instance
- Extension mapping: `.py` → Python, `.ts/.tsx/.js/.jsx` → TypeScript, `.go` → Go, `.rs` → Rust

**Acceptance Criteria:**
- [ ] `detect_language` handles all target extensions
- [ ] `get_scorer` returns correct scorer type
- [ ] Unknown extensions return `None` or raise clear error
- [ ] 15+ unit tests

### 56.3 — TypeScript/JavaScript Scorer

**Points:** 8

Implement `TypeScriptScorer` using docs-mcp's tree-sitter extractor:
- Complexity: Function cyclomatic complexity via AST
- Maintainability: JSDoc presence, TypeScript type coverage
- Test Coverage: Jest/Vitest test file detection, test function count
- Structure: Import analysis, nesting depth
- DevEx: Naming conventions (camelCase), `any` type usage

**Acceptance Criteria:**
- [ ] `TypeScriptScorer` in `scoring/scorer_typescript.py`
- [ ] Scores .ts, .tsx, .js, .jsx files
- [ ] 5 of 7 categories produce meaningful scores
- [ ] Degraded mode when tree-sitter unavailable
- [ ] 40+ unit tests

### 56.4 — Go Scorer

**Points:** 5

Implement `GoScorer` using docs-mcp's tree-sitter extractor:
- Complexity: Function cyclomatic complexity
- Maintainability: Comment coverage, exported vs unexported
- Test Coverage: `_test.go` file detection, `Test*` function count
- Structure: Package imports, nesting depth
- DevEx: Naming conventions (MixedCaps), error handling patterns

**Acceptance Criteria:**
- [ ] `GoScorer` in `scoring/scorer_go.py`
- [ ] Scores .go files
- [ ] 5 of 7 categories produce meaningful scores
- [ ] Degraded mode when tree-sitter unavailable
- [ ] 30+ unit tests

### 56.5 — Rust Scorer

**Points:** 5

Implement `RustScorer` using docs-mcp's tree-sitter extractor:
- Complexity: Function cyclomatic complexity
- Maintainability: Doc comment coverage (`///`), type annotations
- Test Coverage: `#[test]` attribute detection, test module presence
- Structure: Module imports, nesting depth
- DevEx: Naming conventions (snake_case), unsafe block detection

**Acceptance Criteria:**
- [ ] `RustScorer` in `scoring/scorer_rust.py`
- [ ] Scores .rs files
- [ ] 5 of 7 categories produce meaningful scores
- [ ] Degraded mode when tree-sitter unavailable
- [ ] 30+ unit tests

### 56.6 — Tool Integration

**Points:** 3

Update MCP tools to use language detection:
- `tapps_score_file`: Auto-detect language, use appropriate scorer
- `tapps_quick_check`: Support non-Python files
- `tapps_quality_gate`: Language-aware thresholds
- `tapps_validate_changed`: Multi-language batch validation

**Acceptance Criteria:**
- [ ] All 4 tools work with TypeScript, Go, Rust files
- [ ] Response includes `language` field
- [ ] Unsupported languages return clear message (not error)
- [ ] 20+ integration tests

### 56.7 — Documentation & AGENTS.md

**Points:** 2

Update documentation:
- AGENTS.md: Document multi-language support
- README.md: Add supported languages section
- API docs: Update tool descriptions

**Acceptance Criteria:**
- [ ] AGENTS.md mentions TypeScript, Go, Rust support
- [ ] README has "Supported Languages" section
- [ ] Tool docstrings updated

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| tree-sitter parsing edge cases | Medium | Medium | Graceful degradation; report parsing failures |
| Category scores not meaningful for all languages | Medium | Low | Document which categories apply per language |
| Performance regression | Low | Medium | Lazy scorer instantiation; benchmark tests |
| docs-mcp dependency coupling | Low | Medium | Abstract extractor interface; allow fallback |

---

## Open Questions

1. Should language-specific linters (eslint, golint, clippy) be integrated, or deferred?
2. Should thresholds differ by language, or use universal defaults?
3. Should `tapps_security_scan` support non-Python files?

---

## References

- DocsMCP Epic 12: Multi-Language Support (tree-sitter extractors)
- [tree-sitter](https://tree-sitter.github.io/tree-sitter/) documentation
- Existing `scoring/scorer.py` implementation
