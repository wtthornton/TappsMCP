# Epic 4: Project Context & Session Management

**Status:** Not Started
**Priority:** P2 — Important (addresses scope drift and lost context)
**Estimated LOE:** ~2 weeks (1 developer)
**Dependencies:** Epic 0 (Foundation & Security), Epic 1 (Core Quality — for scoring integration in reports)
**Blocks:** None

---

## Goal

Add `tapps_project_profile`, `tapps_session_notes`, `tapps_impact_analysis`, and `tapps_report`. These tools address **scope drift** (LLM over-engineering or using wrong patterns for the project), **lost context** (LLM forgetting constraints from earlier in the session), and **change management** (understanding blast radius before refactors).

## LLM Error Sources Addressed

| Error Source | Tool |
|---|---|
| Scope drift | `tapps_project_profile` |
| Lost context in long sessions | `tapps_session_notes` |

## 2026 Best Practices Applied

- **Project detection via heuristics, not config**: Detect tech stack, frameworks, and project type automatically from file system signals (package managers, config files, directory structure). Don't require manual configuration.
- **Session notes scoped to project root**: Prevent context leakage between projects in multi-project setups. Notes are stored under `{TAPPS_MCP_PROJECT_ROOT}/.tapps-mcp/sessions/`.
- **JSON persistence with crash recovery**: Session notes are in-memory for speed but persisted to JSON for crash recovery. Use atomic writes (tempfile + os.replace).
- **AST-based impact analysis**: Use Python's `ast` module for import graph analysis. Don't shell out to external tools — keep it fast and dependency-free.
- **Lightweight over complex**: `tapps_session_notes` is intentionally simple (key-value store) instead of the full checkpoint/restore system. Full workflow state is deferred to Epic 6 as an optional advanced tool.

## Acceptance Criteria

- [ ] `tapps_project_profile` detects: languages, frameworks, test framework, package manager, CI, Docker, deployment type
- [ ] `tapps_project_profile` works for Python, JS/TS, Rust, Go, and multi-language projects
- [ ] `tapps_project_profile` returns quality config recommendations based on detected stack
- [ ] `tapps_session_notes` supports save, get, list, clear actions
- [ ] Session notes persist to disk for crash recovery
- [ ] Session notes are scoped to project root (no cross-project leakage)
- [ ] `tapps_impact_analysis` identifies affected files and modules for a given change
- [ ] `tapps_impact_analysis` uses AST parsing for import graph analysis
- [ ] `tapps_report` generates quality reports in JSON, markdown, and HTML formats
- [ ] All tools return `elapsed_ms` in response
- [ ] Unit tests: ~25 tests ported + ~15 new tests for session notes
- [ ] Cross-platform: file paths and AST parsing work on Windows + Linux

---

## Stories

### 4.1 — Extract Project Profiling

**Points:** 5

Extract the project detection and profiling system.

**Tasks:**
- Extract `core/project_profile.py` → `tapps_mcp/project/profile.py`
  - Decouple from `workflow.detector` — extract only the profiling logic
  - Accept project root as parameter, return profile as structured data
- Extract from `workflow/detector.py` → `tapps_mcp/project/detector.py`
  - Extract tech stack detection parts only
  - Drop workflow-specific logic
- Copy standalone modules:
  - `core/project_type_detector.py` → `type_detector.py`
  - `core/stack_analyzer.py` → `stack_analyzer.py`
  - `core/ast_parser.py` → `ast_parser.py` — `ModuleInfo`, `FunctionInfo`, `ClassInfo` extraction
- Reuse from Epic 2 (already extracted):
  - `project/language.py` — language detection
  - `project/library_detector.py` — library/dependency detection
- Port ~15 unit tests

**Detection capabilities:**
| Signal | Detection Method |
|---|---|
| Languages | File extensions, shebang lines, language_detector |
| Frameworks | Import analysis, config files (pyproject.toml, package.json) |
| Test framework | pytest.ini, jest.config, go test conventions |
| Package manager | pip/uv/poetry (pyproject.toml), npm/yarn/pnpm (package.json), cargo (Cargo.toml) |
| CI | .github/workflows/, .gitlab-ci.yml, Jenkinsfile |
| Docker | Dockerfile, docker-compose.yml |
| Deployment type | Cloud configs, Procfile, serverless.yml |

**Definition of Done:** `tapps_project_profile` accurately detects tech stack for Python, JS/TS, Rust, Go projects. ~15 tests pass.

---

### 4.2 — Implement Session Notes

**Points:** 3

New implementation — lightweight key-value note storage per session.

**Tasks:**
- Implement `tapps_mcp/session_notes.py`:
  - In-memory dict for speed
  - JSON persistence to `{TAPPS_MCP_PROJECT_ROOT}/.tapps-mcp/sessions/{session_id}.json`
  - Atomic writes (tempfile + os.replace) for crash safety
  - Session ID generated on server start
- Support four actions:
  - `save`: Store key-value pair
  - `get`: Retrieve value by key
  - `list`: Return all notes for current session
  - `clear`: Clear all notes (or single key)
- Notes scoped to project root — different projects get different note stores
- Include `session_id`, `note_count`, `session_started` in responses
- Write ~15 new unit tests

**Definition of Done:** Session notes save, retrieve, list, and persist across server restarts. No cross-project leakage.

---

### 4.3 — Extract Impact Analysis

**Points:** 3

Extract the change impact analyzer for understanding blast radius.

**Tasks:**
- Extract `core/change_impact_analyzer.py` → `tapps_mcp/project/impact_analyzer.py`
  - `ChangeImpactAnalyzer`, `ChangeImpact`, `ChangeImpactReport`
  - Uses AST parsing to build import graph
  - Identifies: directly affected files, transitively affected files, test files to re-run
- Reuse `ast_parser.py` from story 4.1
- Reuse `service_discovery.py` from Epic 2 (validators — for monorepo support)
- Port ~10 unit tests

**Definition of Done:** Impact analysis returns affected files and blast radius for a change. ~10 tests pass.

---

### 4.4 — Extract Report Generation

**Points:** 2

Extract report generation for quality reports.

**Tasks:**
- Reuse `scoring/report_generator.py` (already extracted in Epic 1) for code quality reports
- Reuse `scoring/aggregator.py` (already extracted in Epic 1) for multi-file aggregation
- Reuse `experts/report_generator.py` (already extracted in Epic 3) for expert reports
- Wire into `tapps_report` tool: combine scoring + expert data into unified report
- Support three output formats: JSON (default), markdown, HTML (optional jinja2)

**Definition of Done:** `tapps_report` generates formatted reports from scoring data in all three formats.

---

### 4.5 — Wire MCP Tools

**Points:** 3

Wire all four tools into the MCP server.

**Tasks:**
- Implement `tapps_project_profile` MCP tool handler:
  - `project_root` parameter (default: server's project root)
  - Path validation before any file system scanning
  - Return structured profile with quality config recommendations
- Implement `tapps_session_notes` MCP tool handler:
  - `action` parameter: save/get/list/clear
  - `key` and `value` parameters for save/get
  - Return note data with session metadata
- Implement `tapps_impact_analysis` MCP tool handler:
  - `file_path` parameter: file being changed
  - `change_type` parameter: added/modified/removed
  - Path validation before analysis
  - Return affected files, blast radius, test files to re-run
- Implement `tapps_report` MCP tool handler:
  - `file_path` parameter: optional (project-wide if omitted)
  - `format` parameter: json/markdown/html
  - Return formatted report

**Definition of Done:** All four tools callable via MCP protocol with correct schemas.

---

### 4.6 — Tests

**Points:** 2

Unit and integration tests for all new tools.

**Tasks:**
- Port profile detection tests (~15 tests): Python, JS/TS, Rust, Go, multi-language
- Write session notes tests (~15 tests): save/get/list/clear, persistence, crash recovery
- Port impact analysis tests (~10 tests): single-file, multi-file, transitive
- MCP integration tests: tool call → response for all four tools
- Cross-platform: AST parsing and file paths on Windows + Linux

**Definition of Done:** ~40+ tests pass. All tools work cross-platform.

---

## Performance Targets

| Tool | Target (p95) | Notes |
|---|---|---|
| `tapps_project_profile` | < 3s | File system scanning + detection |
| `tapps_session_notes` | < 100ms | In-memory with file persistence |
| `tapps_impact_analysis` | < 5s | AST parsing + dependency graph |
| `tapps_report` | < 2s | Formatting only (data already scored) |

## Key Dependencies
- None beyond Epic 0 dependencies

## Optional Dependencies
- `jinja2` — for HTML report generation (graceful degradation to JSON/markdown)
