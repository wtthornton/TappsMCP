# Epic 17: Circular Dependency Detection

**Status:** Complete - 3 source files (import_graph.py, cycle_detector.py, coupling_metrics.py), 57 tests, tapps_dependency_graph tool
**Priority:** P0 — Critical (AI assistants routinely create circular imports; deterministic to check)
**Estimated LOE:** ~1.5-2 weeks (1 developer)
**Dependencies:** Epic 0 (Foundation), Epic 4 (Project Context)
**Blocks:** None

---

## Goal

Detect circular imports and unhealthy dependency patterns in Python projects. AI coding assistants routinely introduce circular imports because they lack structural awareness of the module graph. Provide a standalone `tapps_dependency_graph` tool and feed findings into the `structure` scoring category.

## Why This Epic Exists

Circular imports are the **#1 structural defect** AI assistants create in Python projects:

1. **AI adds imports freely** — when generating code, LLMs import whatever they need without checking the dependency graph
2. **Circular imports cause runtime crashes** — `ImportError` at module load time, often only caught in production
3. **Circular imports are hard to debug** — the error message points to the import site, not the cycle
4. **Existing tools don't catch this** — ruff, mypy, and bandit do not detect import cycles
5. **Architecture drift accumulates silently** — each individual change is fine, but the aggregate creates cycles

TappsMCP's `tapps_impact_analysis` already maps file dependencies, but it doesn't detect cycles or validate dependency direction. This epic adds cycle detection, dependency graph visualization, and optional module boundary enforcement.

## LLM Error Sources Addressed

| Error Source | How This Epic Helps |
|---|---|
| Circular imports | Detect import cycles before they cause runtime crashes |
| Wrong import direction | Flag when low-level modules import high-level ones |
| Hidden coupling | Identify modules with excessive afferent/efferent coupling |
| Architecture drift | Track dependency health over time via scoring |
| Opaque module structure | Provide clear dependency graph for project understanding |

## Acceptance Criteria

- [ ] Import graph builder: parse all `.py` files to extract import relationships
- [ ] Cycle detection: find all circular import chains in the project
- [ ] `tapps_dependency_graph` tool: standalone dependency analysis with cycle detection
- [ ] Cycle findings feed into the `structure` scoring category
- [ ] Support both absolute and relative imports
- [ ] Handle conditional imports (`TYPE_CHECKING`, `try/except ImportError`)
- [ ] Provide cycle-breaking suggestions (which import to move/restructure)
- [ ] Coupling metrics: afferent (Ca) and efferent (Ce) coupling per module
- [ ] Configurable: exclude test files, vendored code, generated code
- [ ] All changes covered by unit tests
- [ ] Zero mypy/ruff errors

---

## Stories

### 17.1 — Import Graph Builder

**Points:** 5
**Priority:** Critical
**Status:** Planned

Build a Python import graph from AST analysis. Parse all `.py` files in a project to extract import relationships, distinguishing runtime imports from type-checking-only imports.

**Source Files:**
- `src/tapps_mcp/project/import_graph.py` (NEW)

**Tasks:**
- [ ] Create `import_graph.py` with `ImportGraph` class
- [ ] `build_graph(project_root, exclude_patterns=None) -> ImportGraph` — walks all `.py` files and parses imports
- [ ] Parse `import X` and `from X import Y` statements via `ast.Import` and `ast.ImportFrom`
- [ ] Handle relative imports: resolve `.foo` and `..bar` relative to file position
- [ ] Detect conditional imports: `TYPE_CHECKING` blocks, `try/except ImportError`
- [ ] Mark edges as `runtime` or `type_checking_only`
- [ ] Define `ImportEdge` dataclass: `source_module`, `target_module`, `import_type` (runtime/type_checking/conditional), `line_number`, `import_name`
- [ ] Define `ImportGraph` dataclass: `edges`, `modules`, `project_root`
- [ ] Exclude patterns: `["tests/*", "docs/*", "*_pb2.py", "migrations/*"]` by default
- [ ] Map file paths to module names: `src/tapps_mcp/tools/ruff.py` -> `tapps_mcp.tools.ruff`

**Implementation Notes:**
- Use Python's `ast` module (already used in `project/ast_parser.py`)
- Only track intra-project imports (ignore stdlib and third-party)
- Relative import resolution: use file's `__package__` context
- `TYPE_CHECKING` detection: check `if TYPE_CHECKING:` guard via AST analysis
- `try/except ImportError` detection: check for import inside `ast.Try` with `ImportError` handler
- Graph stored as adjacency list: `dict[str, list[ImportEdge]]`

**Definition of Done:** Import graph accurately represents the project's module dependency structure, including conditional import classification.

---

### 17.2 — Cycle Detection Algorithm

**Points:** 5
**Priority:** Critical
**Status:** Planned

Implement cycle detection on the import graph. Find all strongly connected components (SCCs) and extract minimal cycles. Generate human-readable cycle descriptions with suggested fixes.

**Source Files:**
- `src/tapps_mcp/project/import_graph.py`
- `src/tapps_mcp/project/cycle_detector.py` (NEW)

**Tasks:**
- [ ] Implement Tarjan's SCC algorithm or use iterative DFS cycle detection
- [ ] Find all cycles in the runtime import graph (exclude type-checking-only edges)
- [ ] Define `ImportCycle` dataclass: `modules` (ordered list forming the cycle), `edges` (the import edges), `length`, `involves_type_checking` (bool)
- [ ] Rank cycles by severity: shorter cycles are more critical than longer ones
- [ ] Generate cycle description: "Circular import: A -> B -> C -> A"
- [ ] Generate fix suggestions based on common patterns:
  - Move shared types to a dedicated `types.py` or `models.py` module
  - Use `TYPE_CHECKING` guard for annotation-only imports
  - Defer import to function scope (lazy import)
  - Extract shared dependency to break the cycle
- [ ] Handle self-imports (module imports itself)
- [ ] Option to include/exclude `TYPE_CHECKING` edges in cycle analysis

**Implementation Notes:**
- Tarjan's algorithm is O(V+E) — efficient for large projects
- Report cycles involving only runtime imports as errors
- Report cycles involving `TYPE_CHECKING` imports as warnings (these are usually intentional and safe)
- Suggestion heuristic: if the cycle includes a `models.py`, suggest extracting types; if it includes a utility, suggest lazy import
- Limit reported cycles to top 20 (large projects can have hundreds of cycles in a dense graph)

**Definition of Done:** All import cycles detected with severity ranking and actionable fix suggestions. `TYPE_CHECKING`-only cycles distinguished from runtime cycles.

---

### 17.3 — Coupling Metrics

**Points:** 3
**Priority:** Important
**Status:** Planned

Calculate module coupling metrics to identify over-coupled modules that are likely to cause future circular imports.

**Source Files:**
- `src/tapps_mcp/project/import_graph.py`
- `src/tapps_mcp/project/coupling_metrics.py` (NEW)

**Tasks:**
- [ ] Calculate afferent coupling (Ca): number of modules that depend on this module
- [ ] Calculate efferent coupling (Ce): number of modules this module depends on
- [ ] Calculate instability: `I = Ce / (Ca + Ce)` (0 = maximally stable, 1 = maximally unstable)
- [ ] Identify "hub" modules: high Ca AND high Ce (potential cycle magnets)
- [ ] Define `ModuleCoupling` dataclass: `module`, `afferent`, `efferent`, `instability`, `is_hub`
- [ ] Flag modules where `Ca > threshold` or `Ce > threshold` (configurable, default 10)
- [ ] Generate suggestions for over-coupled modules: "Module X is imported by 15 modules and imports 12 — consider splitting"

**Implementation Notes:**
- Robert C. Martin's stability metrics from "Clean Architecture"
- Stable modules (low instability) should be at the bottom of the dependency hierarchy
- Unstable modules importing stable modules is fine; stable modules importing unstable ones violates the Stable Dependencies Principle
- Hub detection threshold: `Ca >= 8 AND Ce >= 8` (both high)

**Definition of Done:** Coupling metrics calculated per module with instability scores and hub detection.

---

### 17.4 — `tapps_dependency_graph` Tool + Scoring Integration

**Points:** 5
**Priority:** Critical
**Status:** Planned

Expose the dependency analysis as an MCP tool and integrate findings into the `structure` scoring category.

**Source Files:**
- `src/tapps_mcp/server.py`
- `src/tapps_mcp/scoring/scorer.py`
- `src/tapps_mcp/scoring/constants.py`

**Tasks:**
- [ ] Register `tapps_dependency_graph(project_root="", include_type_checking=False)` as an MCP tool
- [ ] Response includes: cycle count, cycle details (top 10), coupling metrics (top 10 most coupled), total modules, total edges
- [ ] Add `_ANNOTATIONS_READ_ONLY` tool annotations
- [ ] Scoring integration: cycles reduce `structure` score
- [ ] Define penalties: `RUNTIME_CYCLE_PENALTY = 10`, `TYPE_CHECKING_CYCLE_PENALTY = 2`, `HUB_MODULE_PENALTY = 3`
- [ ] Cap total dependency penalty at 30
- [ ] Add `details["circular_imports"]` count to structure category
- [ ] Generate suggestions referencing specific module names and line numbers
- [ ] Cache graph per session (dependency graph doesn't change between `tapps_score_file` calls)

**Implementation Notes:**
- Graph building is project-level, not file-level — run once per session
- Cache in module-level variable keyed by project_root + mtime of newest .py file
- For `tapps_score_file` on a single file: check if that file participates in any cycle
- For `tapps_validate_changed`: run graph analysis once, check changed files against cycles
- Runtime cycles are scored as errors; `TYPE_CHECKING` cycles as warnings

**Definition of Done:** `tapps_dependency_graph` tool returns cycle and coupling analysis. Runtime cycles reduce structure scores.

---

### 17.5 — Tests

**Points:** 3
**Priority:** Important
**Status:** Planned

Comprehensive tests for import graph building, cycle detection, coupling metrics, and scoring integration.

**Source Files:**
- `tests/unit/test_import_graph.py` (NEW)
- `tests/unit/test_cycle_detector.py` (NEW)
- `tests/unit/test_coupling_metrics.py` (NEW)

**Tasks:**
- [ ] Test import graph building from sample Python files (AST parsing)
- [ ] Test relative import resolution
- [ ] Test `TYPE_CHECKING` guard detection
- [ ] Test `try/except ImportError` detection
- [ ] Test cycle detection: simple A->B->A cycle
- [ ] Test cycle detection: longer A->B->C->D->A cycle
- [ ] Test cycle detection: no cycles in clean graph
- [ ] Test cycle detection: multiple independent cycles
- [ ] Test `TYPE_CHECKING`-only cycles are marked as warnings
- [ ] Test coupling metrics: Ca, Ce, instability calculation
- [ ] Test hub detection
- [ ] Test scoring integration: cycles reduce structure score
- [ ] Test suggestion generation
- [ ] Test `tapps_dependency_graph` tool handler
- [ ] Test exclusion patterns (tests/, migrations/)
- [ ] Test with TappsMCP's own codebase as integration test

**Definition of Done:** ~40 new tests covering graph building, cycle detection, coupling metrics, and tool integration. Zero mypy/ruff errors.

---

## Performance Targets

| Operation | SLA |
|---|---|
| Graph building (100 modules) | < 2 s |
| Graph building (500 modules) | < 10 s |
| Cycle detection | < 500 ms (Tarjan's is O(V+E)) |
| Coupling metrics | < 100 ms |
| `tapps_dependency_graph` tool | < 15 s (includes graph building) |
| Per-file cycle check (cached graph) | < 10 ms |

## Key Dependencies

- Python `ast` module (stdlib — no external dependency)
- Epic 0 (path validation for safe file traversal)
- Epic 4 (project context — `project_root` resolution)
- Epic 13 (structured outputs — optional, for structured response)
