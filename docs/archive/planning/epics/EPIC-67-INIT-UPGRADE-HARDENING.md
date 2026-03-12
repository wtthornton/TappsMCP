# Epic 67: Init & Upgrade Hardening

<!-- docsmcp:start:metadata -->
- **Status:** Complete
- **Priority:** P2
- **Estimated LOE:** ~1 week (1 developer)
- **Dependencies:** None (builds on existing init/upgrade infrastructure)
- **Blocks:** None
- **Source:** Internal code review of `pipeline/init.py`, `pipeline/upgrade.py`, `server_pipeline_tools.py`
<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:goal -->
## Goal

Harden the `tapps_init` and `tapps_upgrade` pipelines by fixing dead code, closing artifact parity gaps between init and upgrade, adding version markers for idempotent upgrades, and reducing parameter duplication. All changes are internal — no new MCP tools or user-facing API changes.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

A thorough review of the init/upgrade system identified 6 concrete issues ranging from dead code (Docker companion detection is a no-op) to parity gaps (upgrade skips GitHub templates/governance that init generates). None are user-facing bugs today, but they represent technical debt that will compound as consuming projects grow.
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Docker companion detection honestly reports configured status (not fake "installed")
- [ ] `tapps_upgrade` regenerates GitHub templates and governance files (init/upgrade parity)
- [ ] Generated Markdown artifacts include version markers for idempotent upgrades
- [ ] `bootstrap_pipeline` parameter forwarding simplified via `BootstrapConfig` construction at call site
- [ ] `_replace_tapps_section` uses structured heading split instead of fragile regex
- [ ] All existing tests pass; new tests cover each story's changes
<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

### Story 67.1: Fix Docker Companion Detection No-Op

> **As a** TappsMCP maintainer, **I want** Docker companion detection to honestly report configured status, **so that** upgrade results do not mislead users into thinking companions are installed when their status is unknown.

**Points:** 2 | **Size:** S | **Priority:** P1

**Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py` (lines 326-333)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` (`_recommend_companions`)
- `packages/tapps-mcp/tests/unit/test_upgrade_tool.py`
- `packages/tapps-mcp/tests/unit/test_docker_upgrade.py`

#### Problem

In `upgrade_pipeline()`, the Docker companion status loop unconditionally appends every companion to `installed_companions` without checking anything:

```python
for companion in settings.docker.companions:
    installed_companions.append(companion)  # Always "installed"
```

`missing_companions` is always empty. The `_recommend_companions` helper in `init.py` checks against `docker_result["installed_servers"]` but that list is always empty because `_detect_docker()` doesn't enumerate installed servers.

#### Tasks

- [ ] Remove fake companion detection loop from `upgrade_pipeline()`
- [ ] Replace with `"status": "configured"` report that honestly states runtime availability depends on Docker Desktop
- [ ] Fix `_recommend_companions` in `init.py` to match — report companions as "configured" not "installed"
- [ ] Update tests to validate honest reporting
- [ ] Ensure no regression in Docker detection for non-Docker users

#### Acceptance Criteria

- [ ] Fake companion loop removed from `upgrade_pipeline()`
- [ ] Companion status reported as `"configured"` not `"installed"`
- [ ] `_recommend_companions` in `init.py` fixed to match
- [ ] Tests updated to validate honest reporting
- [ ] Result dict still contains `docker` key for backward compat

#### Test Cases

1. `upgrade_pipeline` with Docker disabled reports no companion section
2. `upgrade_pipeline` with Docker enabled reports companions as `"configured"`
3. `_recommend_companions` returns honest status when `docker_result` has no `installed_servers`
4. Backward compat — result dict still contains `docker` key

#### Implementation Notes

Report `"status": "configured"` instead of `"installed"`. Real probing via `docker mcp profile server list --json` adds subprocess overhead and Docker Desktop dependency — not worth it for a status report.

---

### Story 67.2: Add GitHub Templates & Governance to Upgrade Path

> **As a** TappsMCP consuming project maintainer, **I want** `tapps_upgrade` to regenerate GitHub templates and governance files, **so that** all artifacts created by `tapps_init` are also refreshed during upgrade instead of becoming stale.

**Points:** 3 | **Size:** M | **Priority:** P2

**Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py` (lines 364-383)
- `packages/tapps-mcp/tests/unit/test_upgrade_tool.py`
- `packages/tapps-mcp/tests/unit/test_upgrade_integration.py`

#### Problem

`upgrade_pipeline()` regenerates CI workflows and Copilot config but skips:
- GitHub issue/PR templates (`github_templates.py`)
- GitHub governance files (`github_governance.py`)

These are generated by `tapps_init` via `_setup_github_templates()` and `_setup_github_governance()`, but `tapps_upgrade` never refreshes them.

#### Tasks

- [ ] Add `generate_all_github_templates()` call to `upgrade_pipeline()` (same pattern as existing CI/Copilot calls)
- [ ] Add `generate_all_governance()` call to `upgrade_pipeline()`
- [ ] Add dry-run reporting (`"would-regenerate"`) for both new components
- [ ] Add error handling matching existing CI/Copilot `try/except` pattern
- [ ] Add tests verifying templates and governance appear in upgrade results

#### Acceptance Criteria

- [ ] `upgrade_pipeline()` calls `generate_all_github_templates()` and `generate_all_governance()`
- [ ] Results stored in `result["components"]["github_templates"]` and `result["components"]["governance"]`
- [ ] Dry-run reports `"would-regenerate"` for both
- [ ] Errors appended to `result["errors"]` without blocking other upgrades
- [ ] Tests verify templates and governance in upgrade results

#### Dependencies

- Story 67.3 (version markers) should ideally land first for idempotent upgrades

---

### Story 67.3: Add Version Markers to Generated Markdown Artifacts

> **As a** TappsMCP consuming project maintainer, **I want** generated Markdown artifacts to include version markers, **so that** init and upgrade can detect staleness and skip regeneration when artifacts are already current.

**Points:** 3 | **Size:** M | **Priority:** P2

**Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/github_templates.py`
- `packages/tapps-mcp/src/tapps_mcp/pipeline/github_copilot.py`
- `packages/tapps-mcp/src/tapps_mcp/pipeline/github_governance.py`
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_generators.py`
- `packages/tapps-mcp/tests/unit/test_upgrade_integration.py`

#### Problem

GitHub artifacts have no version tracking. Running init or upgrade always regenerates them even if already current. Unlike AGENTS.md which has `<!-- tapps-agents-version: X.Y.Z -->`, these files have no staleness detection.

#### Scope Decisions (from research)

Per tapps-research consultation, different file types warrant different strategies:

| File type | Marker strategy | Rationale |
|-----------|----------------|-----------|
| **Markdown** | `<!-- tapps-generated: vX.Y.Z -->` at line 1, regex-parsed | Supports smart skip/update like AGENTS.md |
| **YAML** (CI workflows) | Write-once by default, `--force` to overwrite | YAML CI files are frequently user-edited; write-once is safer |
| **JSON** (MCP config) | No inline marker; structural validation | JSON schemas may reject unknown keys |

This story focuses on **Markdown artifacts only** (PR templates, issue templates, governance docs, Copilot instructions). YAML CI workflows already use write-once semantics, and JSON configs use structural validation — both are correct as-is.

#### Tasks

- [ ] Create shared `_check_version_marker(path) -> str | None` helper in `platform_generators.py`
- [ ] Add `<!-- tapps-generated: vX.Y.Z -->` to Markdown generators in `github_templates.py`, `github_copilot.py`, `github_governance.py`
- [ ] Wire version check into generators: skip if matching version, update if stale
- [ ] Report `"up-to-date"` or `"updated"` in generator return dicts
- [ ] Add tests for skip-when-current and update-when-stale behavior

#### Acceptance Criteria

- [ ] All generated Markdown artifacts include `<!-- tapps-generated: vX.Y.Z -->` at line 1
- [ ] Shared `_check_version_marker` helper extracts version from first N lines
- [ ] Files with matching version skipped (reported as `"up-to-date"`)
- [ ] Files with older version regenerated (reported as `"updated"`)
- [ ] YAML and JSON files are NOT modified (they use different strategies)
- [ ] Tests verify skip-when-current and update-when-stale behavior

---

### Story 67.4: Simplify `tapps_init` Parameter Forwarding via BootstrapConfig

> **As a** TappsMCP developer, **I want** `bootstrap_pipeline` to accept `BootstrapConfig` directly, **so that** adding new init parameters requires changing only one place instead of three.

**Points:** 3 | **Size:** M | **Priority:** P3

**Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` (lines 1293-1464)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` (lines 119-251)
- `packages/tapps-mcp/src/tapps_mcp/cli.py`
- `packages/tapps-mcp/tests/unit/test_pipeline_init.py`
- `packages/tapps-mcp/tests/unit/test_init_bootstrap.py`

#### Problem

The `tapps_init` MCP tool handler has 18 parameters that are individually forwarded to `bootstrap_pipeline()`, which has the same 18 parameters, which constructs a `BootstrapConfig` with the same 18 fields. This triple declaration makes it easy to add a parameter to one place and forget the others.

#### Scope Decisions (from research)

Per tapps-research consultation:
- **MCP handler must keep flat params** — FastMCP generates JSON schema from type annotations; nested dataclasses produce nested objects which MCP clients handle poorly
- **The dual-signature pattern** (`config: BootstrapConfig | None = None, *, param1=...`) on `bootstrap_pipeline` is the correct pattern — it lets tests pass a pre-built config while the MCP handler uses kwargs
- **Change is: construct `BootstrapConfig` in the MCP handler** instead of forwarding 18 individual kwargs

#### Tasks

- [ ] Update MCP tool handler to construct `BootstrapConfig` and pass it to `bootstrap_pipeline`
- [ ] Update CLI `init` command to construct `BootstrapConfig` and pass it
- [ ] Keep `bootstrap_pipeline` dual-signature (`config | None` + kwargs) for backward compat — no deprecation needed
- [ ] Update tests to prefer `BootstrapConfig` construction pattern
- [ ] Verify all existing tests pass

#### Acceptance Criteria

- [ ] MCP tool handler constructs `BootstrapConfig` and passes via `config=` parameter
- [ ] CLI `init` command constructs `BootstrapConfig` and passes via `config=` parameter
- [ ] `bootstrap_pipeline` keeps dual-signature (no breaking change)
- [ ] Old kwargs calling convention still works (no deprecation warning — just not preferred)
- [ ] All existing tests pass

#### Implementation Notes

The MCP handler still needs individual parameters for the MCP JSON schema. The change is purely in how it calls `bootstrap_pipeline`: construct `BootstrapConfig(create_handoff=create_handoff, ...)` and pass via `config=cfg` instead of forwarding 18 kwargs. Consider a `BootstrapConfig.from_params()` classmethod for readability.

---

### Story 67.5: Replace Fragile TAPPS Section Regex with Structured Split

> **As a** TappsMCP maintainer, **I want** `_replace_tapps_section` to use a structured heading split approach, **so that** CLAUDE.md TAPPS section replacement is robust against unusual user formatting.

**Points:** 2 | **Size:** S | **Priority:** P3

**Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` (lines 1133-1154)
- `packages/tapps-mcp/tests/unit/test_pipeline_init.py`

#### Problem

`_replace_tapps_section()` uses `(?m)^# TAPPS Quality Pipeline.*?(?=\n# (?!TAPPS)|\Z)` with `re.DOTALL` to find and replace the TAPPS section in CLAUDE.md. This only recognizes H1 (`# `) headings as section boundaries. If a user's CLAUDE.md has unusual formatting, the regex may overshoot or undershoot.

#### Tasks

- [ ] Create `_split_by_h1_headings` helper (similar to `agents_md._split_into_sections` but for `^# ` headings)
- [ ] Rewrite `_replace_tapps_section` to use structured split
- [ ] Add edge case tests: TAPPS at start, end, middle, no other H1 headings
- [ ] Test with nested headings (H2/H3) inside user sections
- [ ] Test replacement preserves trailing newlines exactly

#### Acceptance Criteria

- [ ] `_replace_tapps_section` uses structured heading split (no raw regex for section boundary detection)
- [ ] User content before and after TAPPS section preserved exactly
- [ ] Edge cases handled: TAPPS section at start, end, middle, no other H1 headings
- [ ] Tests cover all edge cases including unusual formatting

#### Test Cases

1. TAPPS section at start of file
2. TAPPS section at end of file
3. TAPPS section in middle between user H1 sections
4. File with no other H1 headings besides TAPPS
5. File with nested headings (H2/H3) inside user sections
6. Replacement preserves trailing newlines exactly

<!-- docsmcp:end:stories -->

---

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. **Story 67.1** (Fix Docker companion no-op) — independent, quick P1 fix
2. **Story 67.3** (Version markers for Markdown artifacts) — enables idempotent upgrades
3. **Story 67.2** (GitHub templates & governance in upgrade) — benefits from 67.3
4. **Story 67.4** (BootstrapConfig simplification) — independent refactor
5. **Story 67.5** (Structured TAPPS section split) — independent refactor
<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Acceptance criteria met | 0/6 | 6/6 | Checklist review |
| Stories completed | 0/5 | 5/5 | Sprint board |
| Upgrade parity (init artifacts also in upgrade) | 4/6 generators | 6/6 generators | Code audit |
| Test coverage on init/upgrade paths | Existing | +30 tests | `pytest --co -q` count |
<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:non-goals -->
## Non-Goals

- **Smart merge for hooks/skills/agents** — these are fully generated artifacts; overwrite is correct
- **User-modified file detection** — would require a separate tracking mechanism; out of scope
- **New MCP tools or CLI commands** — all changes are internal to existing init/upgrade
- **Cache warming configurability** — the hardcoded cap of 20 libraries is adequate for now
- **Converting `_detect_docker` to sync** — per research, the existing `asyncio.run()` + `RuntimeError` guard pattern is correct for `asyncio.to_thread()` contexts; converting to sync would lose `wait_for` timeout control
- **Version markers for YAML/JSON files** — YAML CI workflows use write-once semantics; JSON configs use structural validation; both are correct as-is
<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| `BootstrapConfig` construction changes break tests | Medium | Low | Keep dual-signature on `bootstrap_pipeline`; no breaking change |
| Version markers in Markdown artifacts cause merge conflicts | Low | Low | Marker is at line 1; easy to resolve; only in TappsMCP-generated files |
| Upgrade now touching more files causes unexpected overwrites | Low | Medium | All generators already have write-once/skip-existing logic internally |
<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Stories | Action |
|------|---------|--------|
| `packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py` | 67.1, 67.2 | Modify |
| `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` | 67.1, 67.4, 67.5 | Modify |
| `packages/tapps-mcp/src/tapps_mcp/pipeline/github_templates.py` | 67.3 | Modify |
| `packages/tapps-mcp/src/tapps_mcp/pipeline/github_copilot.py` | 67.3 | Modify |
| `packages/tapps-mcp/src/tapps_mcp/pipeline/github_governance.py` | 67.3 | Modify |
| `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_generators.py` | 67.3 | Modify |
| `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` | 67.4 | Modify |
| `packages/tapps-mcp/src/tapps_mcp/cli.py` | 67.4 | Modify |
| `packages/tapps-mcp/tests/unit/test_upgrade_tool.py` | 67.1, 67.2 | Modify |
| `packages/tapps-mcp/tests/unit/test_upgrade_integration.py` | 67.2, 67.3 | Modify |
| `packages/tapps-mcp/tests/unit/test_docker_upgrade.py` | 67.1 | Modify |
| `packages/tapps-mcp/tests/unit/test_pipeline_init.py` | 67.4, 67.5 | Modify |
| `packages/tapps-mcp/tests/unit/test_init_bootstrap.py` | 67.4 | Modify |
<!-- docsmcp:end:files-affected -->

## Test Plan

Each story has its own acceptance criteria with test requirements. Additionally:

- Run full test suite: `uv run pytest packages/tapps-mcp/tests/ -v`
- Manual integration test: run `tapps_init(dry_run=True)` and `tapps_upgrade(dry_run=True)` on a sample project
- Verify backward compatibility: existing consuming projects can upgrade without breaking
