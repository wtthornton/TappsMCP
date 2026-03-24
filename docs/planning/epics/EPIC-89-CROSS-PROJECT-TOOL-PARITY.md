# Epic 89: Cross-Project Tool Parity

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~1 week (1 developer)
**Dependencies:** None
**GitHub Issue:** https://github.com/wtthornton/TappsMCP/issues/76

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this because TappsMCP is designed to serve **any MCP-connected project**, not just itself, but critical tools either fail outright or degrade silently when the target project differs from the MCP server's own directory. The Ralph PLANOPT session (2026-03-24) exposed that `tapps_impact_analysis` is the **only tool** without a `project_root` parameter, making it completely unusable for cross-project MCP usage. Secondary gaps include missing context about which environment `installed_checkers` reflects and the absence of shell/bash project type detection. Fixing these brings every tool to the same cross-project parity standard established by `tapps_project_profile`, `tapps_dependency_graph`, and `tapps_score_file`.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Ensure all TappsMCP tools that accept file paths or report project context work correctly when the target project is NOT the MCP server's own directory. Every tool should accept `project_root` where relevant, resolve paths against it, and report context (like checker availability) relative to the target project.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

- **Production failure observed:** During the Ralph PLANOPT epic review, all 4 calls to `tapps_impact_analysis` failed with "Path outside project root" or "File not found". The tool hardcodes `settings.project_root` (the MCP server directory) and does not accept an override. This is the **only tool** with this gap.
- **Cross-project MCP is the primary use case:** TappsMCP is consumed by external projects via MCP. Tools that only work on TappsMCP's own files defeat the purpose of being an MCP server.
- **`installed_checkers` confusion:** Session start reports checker availability for the MCP server's environment (e.g., ruff, bandit installed in TappsMCP's venv), not the target project's environment. Agents can't tell whether "unavailable" means the checker is missing globally or just not installed in the target project.
- **Shell/bash project detection gap:** `project_profile` classified a shell-heavy CLI tool repo (ralph-claude-code: 85% bash scripts, `install.sh`, `bin/` directory) as "documentation" at 0.6 confidence. The `cli-tool` type detector only checks Python CLI indicators (`cli.py`, click, typer), completely missing shell/bash patterns.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `tapps_impact_analysis` accepts optional `project_root` parameter, defaulting to `settings.project_root`
- [ ] Impact analysis works correctly when called with an external project's root and file paths
- [ ] `tapps_session_start` response includes the resolved `project_root` path in both quick and full modes
- [ ] `installed_checkers` in session start response includes an `environment` field indicating whether availability was checked in the MCP server env or the target project env
- [ ] `project_profile` correctly detects shell/bash-heavy projects as `cli-tool` type (not "documentation")
- [ ] All existing tests pass; new tests cover each new parameter and edge case
- [ ] `mypy --strict` passes on all changed files
- [ ] `ruff check` and `ruff format --check` pass on all changed files

<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

### [89.1](EPIC-89/story-89.1-impact-analysis-project-root.md) -- Add project_root to tapps_impact_analysis

**Points:** 5

The blocking issue. `tapps_impact_analysis` in `server_analysis_tools.py` (line 245) does not accept a `project_root` parameter. The underlying `analyze_impact()` function in `project/impact_analyzer.py` already accepts `project_root: Path`, but the MCP tool wrapper hardcodes `settings.project_root` (line 264). Add the parameter to the MCP tool signature and thread it through to all internal calls.

**Tasks:**
- [ ] Add `project_root: str = ""` parameter to `tapps_impact_analysis()` in `server_analysis_tools.py`
- [ ] When non-empty, resolve to `Path` and use instead of `settings.project_root`
- [ ] Update `_validate_file_path_lazy()` call to accept the overridden root (or validate against the provided root)
- [ ] Thread `project_root` to `build_impact_memory_context()` call
- [ ] Update docstring to document the parameter
- [ ] Add tests: default (uses settings), explicit project_root, path outside overridden root errors correctly
- [ ] Update AGENTS.md tool documentation

**Definition of Done:** `tapps_impact_analysis(file_path="lib/foo.sh", project_root="C:/other/project")` works and returns correct impact data for the external project.

---

### [89.2](EPIC-89/story-89.2-session-start-project-root.md) -- Include resolved project_root in session_start response

**Points:** 2

`tapps_session_start` returns server info, checkers, and diagnostics, but does NOT include the resolved `project_root` in its response. Agents connecting to the MCP server cannot verify which directory the server considers "project root" without calling another tool. This is especially important in quick mode where minimal info is returned.

**Tasks:**
- [ ] Add `project_root` field to the session start response data dict (line ~340 in `server.py`)
- [ ] Include in both quick=true and full modes
- [ ] Add test verifying `project_root` appears in response
- [ ] Update output schema if applicable

**Definition of Done:** Session start response always includes `"project_root": "/path/to/resolved/root"`.

---

### [89.3](EPIC-89/story-89.3-installed-checkers-environment-context.md) -- Annotate installed_checkers with environment context

**Points:** 3

`installed_checkers` in session start reports whether tools like ruff, bandit, mypy are available, but doesn't indicate whether this reflects the MCP server's environment or the target project's environment. When TappsMCP runs in Docker or a separate venv, all checkers may appear unavailable even though the target project has them installed. Add metadata to clarify.

**Tasks:**
- [ ] Add `environment` field to `InstalledChecker` model (or to the `installed_checkers` section of the response)
- [ ] Value should indicate "mcp_server" (checked in server's env) or describe the env
- [ ] Add a `note` field: "Checker availability reflects the MCP server environment, not the target project"
- [ ] Consider adding a `project_root` parameter to `detect_installed_tools()` for future project-env checking
- [ ] Add tests for the new fields
- [ ] Update output schema docs

**Definition of Done:** Agents can distinguish whether checker availability reflects the MCP server environment or the target project.

---

### [89.4](EPIC-89/story-89.4-shell-bash-project-detection.md) -- Shell/Bash project type detection

**Points:** 3

`type_detector.py`'s `cli-tool` detection only checks Python CLI indicators: `_has_cli_entrypoint()` looks for `cli.py`, `main.py`, `command.py`, `__main__.py`; `_has_click_or_typer()` checks for Python framework imports. Shell/bash-heavy projects with `*.sh` files, `bin/` directories, shebangs, and `install.sh` are not detected. Ralph-claude-code (85% bash) was classified as "documentation" at 0.6 confidence.

**Tasks:**
- [ ] Add `_has_shell_entrypoint()` indicator: check for `bin/` directory, `install.sh`, `*.sh` files in root
- [ ] Add `_has_shebang_scripts()` indicator: check for `#!/bin/bash` or `#!/usr/bin/env bash` in files
- [ ] Add shell indicators to the `cli-tool` type definition in `TYPE_DEFINITIONS`
- [ ] Consider adding a new `shell-tool` project type if shell-specific scoring differs from CLI
- [ ] Weight executable `.sh` files higher than `.md` files for type confidence
- [ ] Add tests: shell-only project, mixed shell+python, shell with install.sh
- [ ] Test that ralph-claude-code-like structure detects as `cli-tool` (not "documentation")

**Definition of Done:** A project with 85% bash scripts, `install.sh`, and `bin/` directory is classified as `cli-tool` with >0.7 confidence.

<!-- docsmcp:end:stories -->

---

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- **Story 89.1 is straightforward:** The underlying `analyze_impact()` already accepts `project_root: Path`. The fix is wiring the parameter through the MCP tool wrapper and adjusting path validation.
- **Path validation pattern:** Other tools with `project_root` (e.g., `tapps_project_profile`, `tapps_dependency_graph`) resolve it to `Path` and pass it through. Follow the same pattern.
- **`_validate_file_path_lazy()`** resolves against `settings.project_root`. When a custom `project_root` is provided, either bypass this helper or make it accept an optional root parameter.
- **Shell detection heuristics:** Count `.sh` files, check for shebangs, look for `Makefile` with shell commands, check `bin/` directory. The `documentation` type likely won out because markdown files had higher count/weight.
- **Backward compatibility:** All new parameters are optional with sensible defaults. No breaking changes.

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- **Remote project-env checker detection** -- Actually running checkers in the target project's environment (e.g., via SSH or container) is a much larger feature. This epic only adds metadata about which environment was checked.
- **Per-project checker configuration** -- Allowing projects to specify which checkers they use in `.tapps-mcp.yaml` is useful but separate from indicating the current detection environment.
- **Full polyglot type detection** -- Adding types for Rust, Go, Java projects is valuable but beyond the shell/bash gap identified here.

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| impact_analysis cross-project success rate | 0% (all calls fail) | 100% | Call with external project_root, verify success |
| Shell project detection accuracy | 0% (classified as "documentation") | >70% confidence as cli-tool | Test with ralph-claude-code file structure |
| Tools with project_root support | All except impact_analysis | 100% | Audit all file-path-accepting tools |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. **Story 89.1** -- impact_analysis project_root (P1 blocker, most value)
2. **Story 89.2** -- session_start project_root (quick win, helps all sessions)
3. **Story 89.3** -- installed_checkers environment (metadata, low risk)
4. **Story 89.4** -- shell/bash detection (independent, can parallelize with 89.2-89.3)

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Path validation bypass with custom project_root | Medium | High | Validate custom root is an existing directory; apply same security checks |
| Shell detection false positives (repos with a few .sh scripts) | Medium | Low | Require minimum threshold (e.g., >3 .sh files or bin/ directory) |
| Breaking existing impact_analysis callers | Very Low | Low | New parameter is optional; default behavior unchanged |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| `packages/tapps-mcp/src/tapps_mcp/server_analysis_tools.py` | 89.1 | Update -- add project_root parameter |
| `packages/tapps-mcp/src/tapps_mcp/server.py` | 89.2, 89.3 | Update -- session_start response fields |
| `packages/tapps-mcp/src/tapps_mcp/project/type_detector.py` | 89.4 | Update -- add shell detection indicators |
| `packages/tapps-mcp/src/tapps_mcp/common/output_schemas.py` | 89.2, 89.3 | Update -- response schema changes |
| `packages/tapps-mcp/src/tapps_mcp/tools/tool_detection.py` | 89.3 | Update -- environment metadata |
| `packages/tapps-mcp/tests/unit/test_impact_analysis.py` | 89.1 | Update -- new tests |
| `packages/tapps-mcp/tests/unit/test_session_start.py` | 89.2, 89.3 | Update -- new tests |
| `packages/tapps-mcp/tests/unit/test_type_detector.py` | 89.4 | Update -- shell detection tests |

<!-- docsmcp:end:files-affected -->
