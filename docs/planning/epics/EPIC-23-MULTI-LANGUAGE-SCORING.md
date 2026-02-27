# Epic 23: Multi-Language Scoring Support

**Status:** Proposed
**Priority:** P2 - Important but large effort
**Estimated LOE:** ~6-8 weeks (1 developer)
**Dependencies:** Epic 0 (Foundation), Epic 1 (Core Quality MVP), Epic 9 (Scoring Reliability)
**Blocks:** None

---

## Goal

Extend TappsMCP's scoring pipeline beyond Python to support TypeScript/JavaScript projects, enabling quality scoring, linting, type checking, and security scanning for the most common polyglot stacks.

## Why This Epic Exists

TappsMCP currently scores **only Python files**. The scoring engine, tool wrappers, AST fallbacks, and quality gates are all deeply coupled to Python:

1. **Python AST throughout** - `scoring/scorer.py` uses Python's `ast` module for complexity, security, maintainability, performance, structure, and devex heuristics. Every fallback path parses Python AST nodes (`ast.FunctionDef`, `ast.ClassDef`, `ast.Import`, etc.).

2. **Python-specific tool wrappers** - All 6 tool wrappers in `tools/` are Python-only: ruff (Python linter), mypy (Python type checker), bandit (Python security scanner), radon (Python complexity), vulture (Python dead code), pip-audit (Python dependency scanner).

3. **Hardcoded `.py` extension checks** - File validation, batch processing, and the `tapps_validate_changed` pipeline filter for `.py` files.

4. **Python-specific patterns** - Insecure pattern lists (`eval(`, `pickle.loads`, `os.system`), performance anti-patterns, and structure heuristics all target Python idioms.

Many projects using AI coding assistants are polyglot (Python backend + TypeScript frontend). Supporting TypeScript/JavaScript would significantly expand TappsMCP's user base and utility for full-stack projects.

## LLM Error Sources Addressed

| Error Source | How This Epic Helps |
|---|---|
| JS/TS code quality unmonitored | Brings scoring parity to the most common companion language |
| Polyglot projects partially scored | Full-stack projects get holistic quality visibility |
| Type errors in TypeScript ignored | tsc integration catches type issues before PR merge |
| JS security vulnerabilities undetected | Security scanning covers both languages |

## Architecture Notes

### Python coupling depth assessment

The scoring pipeline has **deep Python coupling** across multiple layers:

- **`CodeScorer` class** (scoring/scorer.py) - 7 category methods all use `ast.parse()` and walk Python AST nodes. These cannot be reused for JS/TS.
- **Tool wrappers** (tools/*.py) - Each wraps a Python-specific CLI tool. JS/TS equivalents exist (eslint/biome, tsc, semgrep) but need new wrapper modules.
- **Scoring models** (scoring/models.py) - `ScoreResult` and `CategoryScore` are language-agnostic and can be reused.
- **Quality gates** (gates/evaluator.py) - Gate evaluation logic is language-agnostic (compares scores to thresholds).
- **Parallel runner** (tools/parallel.py) - `run_all_tools()` is hardcoded to run ruff+mypy+bandit+radon. Needs a language-dispatch layer.

**Estimated reuse: ~30%** - Models, gates, batch validator, and reporting are reusable. Scoring engine, tool wrappers, and AST fallbacks need new implementations per language.

### Recommended architecture

```
scoring/
  scorer.py          -> scorer_python.py (rename)
  scorer_js.py       -> new: JS/TS scoring engine
  scorer_factory.py  -> new: language detection + router
  models.py          -> unchanged (language-agnostic)
  constants.py       -> constants_python.py + constants_js.py

tools/
  ruff.py, mypy.py, bandit.py, radon.py  -> unchanged (Python)
  eslint.py          -> new: eslint/biome wrapper
  tsc.py             -> new: TypeScript type checker
  semgrep_js.py      -> new: JS/TS security scanning
  parallel.py        -> extended: language-aware tool selection
```

## Stories

### Story 23.1: Language Detection and Routing

Add a language detection layer that identifies file language by extension (`.py`, `.ts`, `.tsx`, `.js`, `.jsx`) and routes to the appropriate scoring engine. Update `tapps_score_file`, `tapps_quick_check`, and `tapps_validate_changed` to accept non-Python files.

- Detect language from file extension
- Create `ScorerFactory` that returns the appropriate scorer
- Update tool handlers to use factory instead of direct `CodeScorer`
- Gracefully reject unsupported languages with clear message

### Story 23.2: ESLint/Biome Linter Integration

Create a tool wrapper for JavaScript/TypeScript linting, supporting both eslint and biome (auto-detected). Map lint output to TappsMCP's `LintIssue` model.

- `tools/eslint.py` wrapper with JSON output parsing
- `tools/biome.py` wrapper as alternative
- Auto-detect which linter is available in the project
- Calculate lint score using same 0-10 scale as ruff

### Story 23.3: TypeScript Type Checking (tsc)

Create a tool wrapper for TypeScript type checking via `tsc --noEmit`. Map type errors to a type safety score comparable to mypy's output.

- `tools/tsc.py` wrapper with JSON diagnostic parsing
- Score calculation parallel to `calculate_type_score` from mypy
- Handle projects without tsconfig.json gracefully
- Support both `.ts` and `.tsx` files

### Story 23.4: JavaScript/TypeScript Security Scanning

Integrate semgrep or a similar tool for JS/TS security scanning. Provide AST-based heuristic fallbacks for common JS security anti-patterns (`eval()`, `innerHTML`, `document.write`, unsanitized user input).

- `tools/semgrep_js.py` wrapper or equivalent
- Heuristic fallback patterns for JS/TS (no external tool needed)
- Score calculation parallel to bandit's security scoring
- Cover OWASP Top 10 patterns relevant to JS/TS

### Story 23.5: Quality Gate Adaptation for Multi-Language Projects

Extend quality gates and the `tapps_validate_changed` pipeline to handle mixed-language projects. Report per-language scores and an aggregate project score.

- Update `tapps_validate_changed` to detect JS/TS files alongside Python
- Per-language quality gate thresholds (configurable)
- Aggregate reporting across languages
- Update `tapps_report` to show language breakdown

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Deep Python coupling requires parallel implementation, not refactoring | High | Story 23.1 creates clean abstraction layer first |
| JS/TS ecosystem fragmentation (eslint vs biome, npm vs pnpm vs bun) | Medium | Auto-detect available tools, support top 2 linters |
| AST fallbacks for JS/TS are harder (no stdlib parser) | Medium | Use tree-sitter or regex-based heuristics |
| Maintenance burden doubles with two language stacks | Medium | Share models, gates, and reporting; only scoring differs |
| Scope creep to other languages (Go, Rust, Java) | Low | Explicitly scope to JS/TS only; design for extensibility |
