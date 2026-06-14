# Epic 111: Dependency Upgrade: Latest Stable Quality & Runtime Libraries

<!-- docsmcp:start:metadata -->
**Status:** Accepted
**Linear:** TAP-3933
**Priority:** Medium
**Estimated LOE:** M

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that tapps-mcp stays on supported, CVE-patched, and checker-accurate dependency versions without agents or CI running on stale floors that drift from resolved installs.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Raise pyproject.toml floor pins and uv lockfile across tapps-mcp, tapps-core, docs-mcp, and workspace dev-deps to the latest recommended stable PyPI releases identified in the June 2026 audit, then verify the full test suite and quality gates pass.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Installed versions lag latest stable for 20+ packages (mcp, pydantic, structlog, cryptography caps, pytest, ruff, etc.). Stale floors in packages/tapps-mcp dev extras also diverge from root pyproject.toml. Security-floor caps (<47 cryptography, <26 structlog) block current stable majors.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] All pyproject.toml dependency floors updated to latest stable targets from the audit list
- [x] uv lock refreshed and uv sync --all-packages succeeds on Python 3.12+
- [x] Full unit test suites pass for tapps-core, tapps-mcp, and docs-mcp
- [x] ruff check, mypy --strict, and TAPPS quality gates pass on changed files
- [x] CHANGELOG.md documents the dependency bump scope
- [x] No pylint 4 upgrade attempted while perflint caps pylint<4 (documented blocker)

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 111.1 -- Bump quality checker pins (ruff, pip-audit) (TAP-3937)

**Points:** 2

Update ruff 0.15.16→0.15.17 and pip-audit 2.10.0→2.10.1; align packages/tapps-mcp dev ruff floor 0.15.2→0.15.17 with root.

**Tasks:**
- [x] Implement bump quality checker pins (ruff, pip-audit)
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Bump quality checker pins (ruff, pip-audit) is implemented, tests pass, and documentation is updated.

---

### 111.2 -- Bump core runtime pins (mcp, pydantic, structlog) (TAP-3934)

**Points:** 3

Update mcp 1.26→1.27.2, pydantic 2.12.5→2.13.4, pydantic-settings 2.13.1→2.14.1, structlog 25.5→26.1 (raise <26 cap), click 8.3.1→8.4.1, anyio 4.12.1→4.13.0, filelock 3.24.3→3.29.4.

**Tasks:**
- [x] Implement bump core runtime pins (mcp, pydantic, structlog)
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Bump core runtime pins (mcp, pydantic, structlog) is implemented, tests pass, and documentation is updated.

---

### 111.3 -- Bump security floor caps (cryptography, pyjwt) (TAP-3935)

**Points:** 3

Raise cryptography cap <47→<50 (46.0.7→49.0.0), pyjwt 2.12→2.13, python-multipart 0.0.29→0.0.32, requests 2.33→2.34.2, pip 26.1.1→26.1.2.

**Tasks:**
- [x] Implement bump security floor caps (cryptography, pyjwt)
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Bump security floor caps (cryptography, pyjwt) is implemented, tests pass, and documentation is updated.

---

### 111.4 -- Align test/dev toolchain pins (TAP-3936)

**Points:** 2

pytest 9.0.3→9.1.0, pytest-asyncio 1.3→1.4, pytest-cov 7.0→7.1, pytest-xdist 3.5→3.8, pytest-randomly 3.16→4.1, pre-commit 4.5.1→4.6.0, playwright 1.58→1.60.

**Tasks:**
- [x] Implement align test/dev toolchain pins
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Align test/dev toolchain pins is implemented, tests pass, and documentation is updated.

---

### 111.5 -- Bump optional RAG and tree-sitter pins (TAP-3938)

**Points:** 2

numpy 2.4.2→2.4.6, sentence-transformers 5.5.0→5.5.1, faiss-cpu 1.13.2→1.14.3, tree-sitter 0.24→0.25.2, tree-sitter-go 0.23.4→0.25.0, tree-sitter-rust 0.23.2→0.24.2.

**Tasks:**
- [x] Implement bump optional rag and tree-sitter pins
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Bump optional RAG and tree-sitter pins is implemented, tests pass, and documentation is updated.

---

### 111.6 -- Bump build and eval dependency pins (TAP-3939)

**Points:** 1

hatchling 1.28→1.30.1, anthropic 0.103→0.109.1; evaluate cohere 5.0→7.0.4 floor in tapps-core reranker extra.

**Tasks:**
- [x] Implement bump build and eval dependency pins
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Bump build and eval dependency pins is implemented, tests pass, and documentation is updated.

---

### 111.7 -- Reconcile tapps-brain git pin vs releases (TAP-3940)

**Points:** 2

Verify floor >=3.24.0 and git rev d893fc1 against latest GitHub tag v3.22.4; pin to intended release tag or document why pre-release rev is required.

**Tasks:**
- [x] Implement reconcile tapps-brain git pin vs releases
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Reconcile tapps-brain git pin vs releases is implemented, tests pass, and documentation is updated. Documented in `pyproject.toml` comment and ADR-0015; switch to `v3.24.0` tag when released.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Audit date: 2026-06-13.
- Already current: mypy 2.1.0, bandit 1.9.4, radon 6.0.1, vulture 2.16, perflint 0.8.1, pylint 3.3.9, httpx 0.28.1.
- Blocked: pylint 4.0.5 (perflint requires pylint<4).

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Upgrading pylint to 4.x until perflint supports it
- Bumping unrelated application code or refactoring beyond pin/lock changes
- Changing tapps-mcp version number unless release workflow requires it

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Lines | Recent Commits | Public Symbols |
|------|-------|----------------|----------------|
| `pyproject.toml:1-35` | *(not found)* | - | - |
| `packages/tapps-mcp/pyproject.toml:1-70` | *(not found)* | - | - |
| `packages/tapps-core/pyproject.toml:1-45` | *(not found)* | - | - |
| `packages/docs-mcp/pyproject.toml:1-55` | *(not found)* | - | - |
| `uv.lock:1-50` | *(not found)* | - | - |
| `CHANGELOG.md:1-30` | *(not found)* | - | - |

<!-- docsmcp:end:files-affected -->
