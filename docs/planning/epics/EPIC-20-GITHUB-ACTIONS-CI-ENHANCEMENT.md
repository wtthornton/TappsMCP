# Epic 20: GitHub Actions CI Enhancement

**Status:** Planned
**Priority:** P1 — High (existing CI workflow needs modernization; new workflows unlock agent-in-CI patterns)
**Estimated LOE:** ~2-2.5 weeks (1 developer)
**Dependencies:** Epic 8 (Pipeline Orchestration), Epic 12 (Platform Integration)
**Blocks:** Epic 21 (Copilot Agent Integration)

---

## Goal

Modernize the existing `tapps-quality.yml` CI workflow and add new GitHub Actions workflows that support the 2026 ecosystem: CodeQL scanning, Copilot coding agent environment setup, Dependabot auto-merge, and reusable workflow modules. These workflows make TappsMCP-initialized repositories CI-ready with security attestations, cost-optimized runners, and agent-compatible environments.

## Why This Epic Exists

GitHub Actions has evolved significantly in 2025-2026:

1. **Artifacts v4 is mandatory** — v3 was deprecated January 2025. The current `tapps-quality.yml` needs updating.
2. **Arm64 runners are 37% cheaper** (GA 2025) and free for public repos — cost optimization is now trivial.
3. **CodeQL incremental analysis** (GA September 2025) makes security scanning fast enough to be a required check.
4. **Copilot coding agent** runs in a GitHub Actions environment configured via `.github/workflows/copilot-setup-steps.yml` — TappsMCP should generate this so the agent has ruff, mypy, bandit, and radon available.
5. **Reusable workflows** now support 10 nested levels and 50 total workflows — modular quality pipelines are practical.
6. **Artifact attestations** enable SLSA Level 2-3 supply chain security with minimal effort.
7. **SHA-pinned actions** are now a best practice enforced by action allowlisting (GA February 2026, all plans).
8. **Agentic Workflows** (technical preview February 2026) let AI agents run as part of CI — TappsMCP quality checks can be part of this.

The current `generate_ci_workflow()` produces a minimal single-job workflow. This epic expands it into a comprehensive, modular CI suite.

## LLM Error Sources Addressed

| Error Source | How This Epic Helps |
|---|---|
| Agent PRs skip quality checks | Copilot setup-steps ensures quality tools are available to the coding agent |
| Outdated CI patterns | Upgraded workflow uses Artifacts v4, SHA-pinned actions, minimal permissions |
| Security vulnerabilities in dependencies | CodeQL workflow catches vulnerabilities before merge |
| Expensive CI runs | Arm64 runners reduce costs 37%; incremental CodeQL reduces scan time |
| Manual Dependabot PR triage | Auto-merge workflow handles patch/minor updates automatically |
| Supply chain attacks | Artifact attestations provide provenance verification |
| Agent-created code lacks security review | CodeQL + TappsMCP quality gate run on every PR |

## 2026 Best Practices Applied

- **`actions/upload-artifact@v4`** and **`actions/download-artifact@v4`** (v3 is dead)
- **SHA-pinned actions** for all third-party dependencies
- **`runs-on: ubuntu-24.04-arm`** for cost savings where compatible
- **Minimal `permissions`** on every job (principle of least privilege)
- **`actions/attest-build-provenance`** for supply chain security
- **`workflow_dispatch` with 25 inputs** for manual quality check triggers
- **Reusable workflow composition** for modular pipeline stages
- **Copilot setup-steps** pattern for coding agent environment
- **CodeQL Action v4** with incremental analysis

## Acceptance Criteria

- [ ] Upgraded `tapps-quality.yml` with Artifacts v4, SHA-pinned actions, minimal permissions
- [ ] Optional Arm64 runner configuration
- [ ] CodeQL scanning workflow generated (`.github/workflows/codeql.yml`)
- [ ] Copilot setup-steps workflow generated (`.github/workflows/copilot-setup-steps.yml`)
- [ ] Dependabot auto-merge workflow generated (`.github/workflows/dependabot-automerge.yml`)
- [ ] Reusable workflow module for TappsMCP quality checks
- [ ] All workflows use `permissions:` block with minimal required scopes
- [ ] Generator functions are ecosystem-aware (Python-focused but extensible)
- [ ] All generators integrated into `tapps_init` and `tapps_upgrade`
- [ ] All changes covered by unit tests
- [ ] Zero mypy/ruff errors

## Implementation Order

```
Story 20.1 (Upgrade Quality Workflow) ──► Story 20.5 (Reusable Module)
                                                │
Story 20.2 (CodeQL Workflow) ───────────────────┤
                                                │
Story 20.3 (Copilot Setup-Steps) ──────────────┤
                                                │
Story 20.4 (Auto-Merge Workflow) ──────────────┤
                                                │
                                          Story 20.6 (Init/Upgrade Wire)
                                                │
                                          Story 20.7 (Tests)
```

---

## Stories

### 20.1 — Upgrade Quality Workflow

**Points:** 5
**Priority:** Critical
**Status:** Planned

Modernize the existing `generate_ci_workflow()` output to follow 2026 GitHub Actions best practices.

**Source Files:**
- `src/tapps_mcp/pipeline/platform_generators.py`

**Tasks:**
- [ ] Update `generate_ci_workflow()` in `platform_generators.py` (current `_CI_WORKFLOW` string template at line ~1624) to produce a modernized `tapps-quality.yml`
- [ ] Add explicit `permissions:` block with minimal scopes (`contents: read`, `pull-requests: write` for annotations)
- [ ] SHA-pin all action references (e.g., `actions/checkout@v4` → `actions/checkout@<sha>`)
- [ ] Use `actions/upload-artifact@v4` for quality report artifacts
- [ ] Add `concurrency:` group to cancel superseded runs on same PR
- [ ] Add `workflow_dispatch:` trigger for manual quality checks with inputs (preset, file_paths)
- [ ] Add job-level `timeout-minutes: 15` to prevent runaway jobs
- [ ] Add comment with Arm64 runner option: `# runs-on: ubuntu-24.04-arm  # 37% cheaper`
- [ ] Use `actions/setup-python@v5` with version from project profile (default `"3.12"`)
- [ ] Add `pip install tapps-mcp` step (or `uv pip install tapps-mcp`)
- [ ] Quality check step: `tapps-mcp validate-changed --preset standard`
- [ ] Upload quality report as artifact (Artifacts v4)
- [ ] Backward compatible — existing installs get upgraded on `tapps_upgrade`

**Implementation Notes:**
- SHA-pinning: use well-known SHAs for `actions/checkout@v4`, `actions/setup-python@v5`, `actions/upload-artifact@v4`
- Store SHA values as constants in the module for easy updates
- `concurrency.cancel-in-progress: true` prevents wasted compute on rapid pushes
- `workflow_dispatch` with `inputs:` allows manual quality checks from the Actions UI

**Definition of Done:** Quality workflow uses 2026 best practices. Existing projects get the upgrade via `tapps_upgrade`.

---

### 20.2 — CodeQL Scanning Workflow

**Points:** 3
**Priority:** Important
**Status:** Planned

Generate a CodeQL code scanning workflow that runs incremental analysis on PRs.

**Source Files:**
- `src/tapps_mcp/pipeline/github_workflows.py` (NEW)

**Tasks:**
- [ ] Create `github_workflows.py` module in `pipeline/` (string templates, NOT PyYAML — GitHub Actions YAML uses `${{ }}` expressions incompatible with YAML libraries)
- [ ] `generate_codeql_workflow(project_root, project_profile=None) -> dict[str, Any]` function
- [ ] Generate `.github/workflows/codeql.yml` with:
  - Triggers: `push` (default branch), `pull_request` (default branch), `schedule` (weekly)
  - `permissions: { actions: read, contents: read, security-events: write }`
  - `github/codeql-action/init@v4` with `languages: ["python"]` (auto-detect from profile)
  - `github/codeql-action/autobuild@v4`
  - `github/codeql-action/analyze@v4`
- [ ] Auto-detect languages from project profile (Python, JavaScript, TypeScript, etc.)
- [ ] SHA-pin all CodeQL action references
- [ ] Skip generation if `.github/workflows/codeql.yml` already exists (respect `overwrite` flag)

**Implementation Notes:**
- CodeQL Action v4 is the current version (v3 deprecated October 2025)
- Incremental analysis is automatic — no configuration needed, CodeQL handles it
- For Python, `autobuild` usually works out of the box
- Only generate languages the project actually uses (from `project_profile.languages`)

**Definition of Done:** CodeQL workflow generated with incremental analysis, correct language detection, and SHA-pinned actions.

---

### 20.3 — Copilot Setup-Steps Workflow

**Points:** 5
**Priority:** Critical
**Status:** Planned

Generate `.github/workflows/copilot-setup-steps.yml` that configures the Copilot coding agent's development environment with TappsMCP quality tools installed.

**Source Files:**
- `src/tapps_mcp/pipeline/github_workflows.py`

**Tasks:**
- [ ] `generate_copilot_setup_steps(project_root, project_profile=None) -> dict[str, Any]` function
- [ ] Generate `.github/workflows/copilot-setup-steps.yml` with:
  - `name: "Copilot Setup Steps"`
  - Step 1: `actions/setup-python@v5` with version from project profile
  - Step 2: Install project dependencies (`uv sync` or `pip install -r requirements.txt`)
  - Step 3: Install TappsMCP (`uv pip install tapps-mcp` or `pip install tapps-mcp`)
  - Step 4: Install quality checkers (`pip install ruff mypy bandit radon`)
  - Step 5: Verify tools available (`tapps-mcp doctor` or simple version checks)
- [ ] Auto-detect package manager from project profile (`uv`, `pip`, `poetry`, `pdm`)
- [ ] Include comment explaining what this file is for
- [ ] SHA-pin action references

**Implementation Notes:**
- This file is NOT a regular CI workflow — it's specifically for the Copilot coding agent
- The coding agent uses this to set up its isolated development environment
- The file format is standard GitHub Actions YAML but with a specific name convention
- Without this file, the Copilot coding agent may not have quality tools available
- TappsMCP being available means the agent can use `tapps_quick_check` and `tapps_validate_changed` during autonomous PR creation

**Definition of Done:** Copilot setup-steps workflow installs all quality tools so the coding agent can use TappsMCP during autonomous work.

---

### 20.4 — Dependabot Auto-Merge Workflow

**Points:** 2
**Priority:** Important
**Status:** Planned

Generate a workflow that auto-approves and auto-merges Dependabot PRs for patch and minor updates.

**Source Files:**
- `src/tapps_mcp/pipeline/github_workflows.py`

**Tasks:**
- [ ] `generate_dependabot_automerge(project_root) -> dict[str, Any]` function
- [ ] Generate `.github/workflows/dependabot-automerge.yml` with:
  - Trigger: `pull_request` from `dependabot[bot]`
  - `permissions: { contents: write, pull-requests: write }`
  - Step: Fetch Dependabot metadata (`dependabot/fetch-metadata@v2`)
  - Step: Auto-approve if patch or minor update (`gh pr review --approve`)
  - Step: Enable auto-merge (`gh pr merge --auto --squash`)
- [ ] Only auto-merge `patch` and `minor` updates (not `major`)
- [ ] SHA-pin action references

**Implementation Notes:**
- Uses `dependabot/fetch-metadata` to determine update type (major/minor/patch)
- Conditional: `if: steps.metadata.outputs.update-type != 'version-update:semver-major'`
- Auto-merge requires branch protection / merge queue to be configured (PRs still need passing checks)
- Uses `GITHUB_TOKEN` — no additional secrets needed

**Definition of Done:** Auto-merge workflow handles Dependabot patch/minor PRs without manual intervention.

---

### 20.5 — Reusable Quality Workflow Module

**Points:** 3
**Priority:** Important
**Status:** Planned

Extract TappsMCP quality checks into a reusable workflow that other workflows can call.

**Source Files:**
- `src/tapps_mcp/pipeline/github_workflows.py`

**Tasks:**
- [ ] `generate_reusable_quality_workflow(project_root) -> dict[str, Any]` function
- [ ] Generate `.github/workflows/tapps-quality-reusable.yml` with:
  - `on: workflow_call:` trigger
  - `inputs:` — `preset` (string, default "standard"), `python-version` (string, default "3.12"), `file_paths` (string, default "")
  - `secrets: inherit`
  - Job: install TappsMCP, run `tapps-mcp validate-changed`
  - Upload quality report artifact
- [ ] Update `tapps-quality.yml` to optionally call the reusable workflow instead of inline steps
- [ ] Reusable workflow supports both `uv` and `pip` installation paths

**Implementation Notes:**
- Reusable workflows use `workflow_call` trigger (not `workflow_dispatch`)
- Callers use `uses: ./.github/workflows/tapps-quality-reusable.yml` with `with:` inputs
- This enables projects to compose quality checks into larger CI pipelines
- Supports up to 10 nested levels and 50 total workflows per run (2025 limit increase)

**Definition of Done:** Reusable workflow module can be called from any workflow to run TappsMCP quality checks.

---

### 20.6 — Init/Upgrade Integration

**Points:** 3
**Priority:** Critical
**Status:** Planned

Wire all new workflow generators into `tapps_init` and `tapps_upgrade`.

**Source Files:**
- `src/tapps_mcp/pipeline/init.py`
- `src/tapps_mcp/pipeline/upgrade.py`
- `src/tapps_mcp/server_pipeline_tools.py`
- `src/tapps_mcp/distribution/doctor.py`

**Tasks:**
- [ ] Add `create_ci_workflows: bool = True` parameter to `tapps_init`
- [ ] Refactor `_setup_platform()` in `init.py` — extract `_setup_github_workflows()` sub-function to keep the orchestrator manageable
- [ ] Call all workflow generators from the new sub-function
- [ ] Add new workflows to `tapps_upgrade` refresh logic
- [ ] Add workflow checks to `tapps_doctor`:
  - Check `tapps-quality.yml` exists and uses v4 artifacts
  - Check `copilot-setup-steps.yml` exists
  - Warn if `codeql.yml` is missing
- [ ] Report created workflows in init/upgrade return dict under `"ci_workflows"` key
- [ ] Respect `dry_run` flag

**Implementation Notes:**
- CodeQL workflow is optional (some repos may not want it) — generate by default but document how to skip
- Copilot setup-steps is highly recommended — generate for all platforms
- Auto-merge workflow only generated when Dependabot config is also generated

**Definition of Done:** `tapps_init` creates all workflows. `tapps_upgrade` refreshes them. `tapps_doctor` verifies them.

---

### 20.7 — Tests

**Points:** 3
**Priority:** Important
**Status:** Planned

Comprehensive tests for all workflow generators.

**Source Files:**
- `tests/unit/test_github_workflows.py` (NEW)

**Tasks:**
- [ ] Test upgraded `generate_ci_workflow()` includes Artifacts v4, permissions, concurrency
- [ ] Test SHA-pinned action references are present
- [ ] Test `workflow_dispatch` trigger with inputs
- [ ] Test `generate_codeql_workflow()` with Python project profile
- [ ] Test CodeQL language detection from project profile
- [ ] Test `generate_copilot_setup_steps()` includes TappsMCP installation
- [ ] Test setup-steps detects `uv` vs `pip` from project profile
- [ ] Test `generate_dependabot_automerge()` only auto-merges patch/minor
- [ ] Test `generate_reusable_quality_workflow()` has `workflow_call` trigger
- [ ] Test reusable workflow has correct inputs (preset, python-version, file_paths)
- [ ] Test idempotency — skip when files exist, overwrite when flag set
- [ ] Test `dry_run` mode returns plan without writing
- [ ] Test integration with `tapps_init` (mock project profile)

**Definition of Done:** ~30 new tests covering all workflow generators and integration. Zero mypy/ruff errors.

---

## Performance Targets

| Operation | SLA |
|---|---|
| All workflow generation (5 files) | < 200 ms |
| Single workflow generation | < 50 ms |
| Full `tapps_init` with workflows | < 2 s additional overhead |

## Architecture Note

New workflow generators go in `github_workflows.py` (not `platform_generators.py`), except for the existing `generate_ci_workflow()` upgrade which stays in `platform_generators.py` for backward compatibility. The new module handles CodeQL, copilot-setup-steps, auto-merge, and reusable workflows. All workflows are generated as string templates (matching the existing `_CI_WORKFLOW` pattern), NOT via PyYAML, since GitHub Actions YAML has special syntax (`${{ }}` expressions, `on:` triggers) that YAML libraries cannot produce correctly.

## Key Dependencies

- Epic 8 (Pipeline Orchestration — `tapps_init` infrastructure)
- Epic 12 (Platform Integration — `platform_generators.py` patterns)
- Epic 4 (Project Context — `project_profile` for language/ecosystem detection)
- GitHub Actions runner image labels (constants for SHA-pinned actions)
