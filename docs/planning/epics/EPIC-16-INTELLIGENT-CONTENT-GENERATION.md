# Epic 16: Intelligent Content Generation

**Status:** Open
**Priority:** P2
**Estimated LOE:** ~1.5–2 weeks
**Dependencies:** DocsMCP Epics 3, 8 (README, Guides)
**Blocks:** None

---

## Goal

Replace generic placeholder content in README, CONTRIBUTING, and ONBOARDING generators with project-specific content derived from actual code analysis.

## Current State

- `readme.py` falls back to `"A {name} project."` when no description found
- `readme.py._generate_features()` uses hardcoded directory checks (`if (project_root / "tests").exists()`)
- `guides.py` emits `<!-- Add key concepts and domain terminology here -->` placeholder
- No integration between guide generators and the extractor/analyzer modules

## Acceptance Criteria

- [ ] README description pulled from pyproject.toml or package docstring
- [ ] Features derived from API surface analysis, not directory existence
- [ ] Key concepts section populated from primary classes and their docstrings
- [ ] Contributing guide detects test framework and linter config from project files
- [ ] Grammar bug `"1 public APIs"` fixed
- [ ] All existing DocsMCP tests pass; new tests for each story

---

## Stories

### 16.1 — Smart Description Fallback

**Priority:** High | **Points:** 3

**Source Files:**
- `packages/docs-mcp/src/docs_mcp/generators/readme.py` — description logic
- `packages/docs-mcp/src/docs_mcp/generators/metadata.py` — metadata extraction

**Tasks:**
- Read `pyproject.toml` `[project].description` field as primary source
- Fall back to first non-empty paragraph of existing README
- Fall back to top-level package `__init__.py` module docstring
- For monorepos, compose description from sub-package descriptions
- Remove `"A {name} project."` fallback (replace with meaningful default)

**Definition of Done:** README generation produces a meaningful project description without manual input.

---

### 16.2 — Code-Derived Feature Detection

**Priority:** High | **Points:** 3

**Source Files:**
- `packages/docs-mcp/src/docs_mcp/generators/readme.py` — `_generate_features()`

**Tasks:**
- Replace directory-existence checks with API surface analysis
- Count public functions/classes per subpackage for feature bullets
- Detect framework usage (FastMCP, Click, Pydantic, pytest) from imports
- Generate feature descriptions based on detected patterns

**Definition of Done:** Feature section reflects actual code capabilities, not filesystem structure.

---

### 16.3 — Key Concepts from API Surface

**Priority:** Medium | **Points:** 5

**Source Files:**
- `packages/docs-mcp/src/docs_mcp/generators/guides.py` — key concepts section
- `packages/docs-mcp/src/docs_mcp/analyzers/api_surface.py` — API surface data

**Tasks:**
- Replace `<!-- Add key concepts -->` placeholder with auto-generated content
- Extract primary classes (most public methods, most imported) and their docstrings
- Group by subpackage or domain
- Include cross-references to API docs where available
- Limit to top 10 concepts to avoid bloat

**Definition of Done:** Onboarding guide includes meaningful key concepts derived from code.

---

### 16.4 — Contributing Guide Source Analysis

**Priority:** Medium | **Points:** 3

**Source Files:**
- `packages/docs-mcp/src/docs_mcp/generators/guides.py` — contributing generation

**Tasks:**
- Detect test framework from `pyproject.toml` (`[tool.pytest]`) and conftest patterns
- Detect linter/formatter config (`[tool.ruff]`, `[tool.mypy]`) and generate lint instructions
- Detect CI configuration (`.github/workflows/`) and reference workflow files
- Fix grammar: `"1 public APIs"` → `"1 public API"` (pluralization)

**Definition of Done:** Contributing guide includes project-specific test, lint, and CI instructions.

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| pyproject.toml parsing edge cases | Low | Use tomllib (stdlib in 3.12+) |
| API surface analysis slow for large projects | Medium | Cache results; limit scan depth |
| Over-generated key concepts | Low | Cap at top 10; sort by relevance |
