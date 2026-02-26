# Epic 22: GitHub Governance & Security Configuration

**Status:** Complete (Stories 22.1–22.6)
**Priority:** P2 — Important (security config completes the agent-friendly repository setup)
**Estimated LOE:** ~1.5-2 weeks (1 developer)
**Dependencies:** Epic 19 (Issue & PR Templates), Epic 20 (CI Enhancement), Epic 21 (Agent Integration)
**Blocks:** None

---

## Goal

Generate GitHub governance and security configuration files that complete the agent-friendly repository setup: security policy, ruleset recommendation scripts, CODEOWNERS template, and a post-init setup guide. This epic bridges the gap between file-based generation (what TappsMCP can do automatically) and API-based configuration (what requires manual or scripted setup via `gh` CLI).

## Why This Epic Exists

Epics 19-21 generate files that live in the repository. But a fully agent-friendly GitHub repository also needs:

1. **Repository rulesets** (GA for Team plans June 2025) — enforce required checks, required reviews, merge queues, and signed commits. Rulesets replaced branch protection rules as the modern standard. They're configurable via REST API but require org/repo admin permissions.

2. **CODEOWNERS** — defines who reviews what. Critical for Copilot code review's "required review by specific teams" feature (GA November 2025).

3. **Security policy** (`SECURITY.md`) — required for responsible disclosure. GitHub's secret scanning and push protection features reference this file.

4. **Post-init setup guide** — some configurations can't be generated as files (rulesets, Copilot MCP server registration, merge queue settings). A setup guide with runnable `gh` CLI commands bridges this gap.

5. **Copilot MCP server registration** — the Copilot coding agent needs TappsMCP registered as an MCP server in repository settings. This can't be done via a file — it requires API/UI configuration.

6. **Secret scanning push protection** (GA August 2025) — custom patterns and delegated bypass are configurable but not via repository files.

This epic generates what it can as files and provides actionable `gh` CLI commands for everything else.

## LLM Error Sources Addressed

| Error Source | How This Epic Helps |
|---|---|
| PRs merged without quality checks | Ruleset script enforces `tapps-quality` as required check |
| Agent PRs bypass review | Ruleset requires human approval even for Copilot-created PRs |
| No code ownership clarity | CODEOWNERS file defines review responsibilities |
| Security vulnerabilities unreported | SECURITY.md provides responsible disclosure channel |
| Incomplete repository setup | Post-init guide covers API-only configurations step by step |
| Force pushes destroy history | Ruleset blocks force pushes and branch deletion |

## 2026 Best Practices Applied

- **Rulesets** (not legacy branch protection rules) as the modern standard
- **Organization rulesets** available on Team plans (June 2025)
- **Required review by specific teams** via rulesets (November 2025)
- **Merge queue** configuration via rulesets
- **Push protection** with custom patterns and delegated bypass
- **`gh api`** for programmatic ruleset creation
- **CODEOWNERS** for Copilot code review integration
- **SECURITY.md** for responsible disclosure

## Acceptance Criteria

- [ ] CODEOWNERS template generated with auto-detected project structure
- [ ] SECURITY.md template generated
- [ ] Ruleset setup script generated with `gh api` commands
- [ ] Post-init setup guide generated with step-by-step instructions
- [ ] Setup guide covers: rulesets, Copilot MCP registration, merge queue, secret scanning
- [ ] All generators integrated into `tapps_init` and `tapps_upgrade`
- [ ] All changes covered by unit tests
- [ ] Zero mypy/ruff errors

## Implementation Order

```
Story 22.1 (CODEOWNERS) ──────────────► Story 22.5 (Init/Upgrade Wire)
                                                │
Story 22.2 (SECURITY.md) ─────────────────────┤
                                                │
Story 22.3 (Ruleset Script) ──────────────────┤
                                                │
Story 22.4 (Post-Init Setup Guide) ───────────┤
                                                │
                                          Story 22.6 (Tests)
```

---

## Stories

### 22.1 — CODEOWNERS Template Generator

**Points:** 3
**Priority:** Important
**Status:** Planned

Generate a `.github/CODEOWNERS` file using project structure analysis to assign review ownership.

**Source Files:**
- `src/tapps_mcp/pipeline/github_governance.py` (NEW)

**Tasks:**
- [ ] Create `github_governance.py` module in `pipeline/`
- [ ] `generate_codeowners(project_root, project_profile=None) -> dict[str, Any]` function
- [ ] Auto-detect top-level directories from project structure:
  - `src/` → default owner
  - `tests/` → default owner
  - `.github/` → default owner
  - `docs/` → default owner
- [ ] Generate `.github/CODEOWNERS` with:
  - Comment header explaining the file's purpose
  - `*` catch-all rule with `@org/team` placeholder
  - Per-directory rules with placeholder owners
  - Comment explaining how to replace placeholders with actual GitHub teams/users
- [ ] Include security-sensitive paths with explicit ownership:
  - `*.lock` files
  - `pyproject.toml` / `package.json`
  - `.github/workflows/`
  - `Dockerfile` / `docker-compose.yml`
- [ ] Skip generation if `.github/CODEOWNERS` already exists (respect `overwrite` flag)

**Implementation Notes:**
- CODEOWNERS uses `.gitignore`-style glob patterns
- Last matching pattern wins (most specific at bottom)
- Placeholder owners use `@TODO-replace-with-team` format so the file isn't silently broken
- CODEOWNERS is critical for the "required review by specific teams" ruleset feature (November 2025)
- Cannot auto-detect actual team names — always generate with placeholders

**Definition of Done:** CODEOWNERS template generated with project-structure-aware paths and placeholder owners.

---

### 22.2 — Security Policy Generator

**Points:** 2
**Priority:** Important
**Status:** Planned

Generate a `SECURITY.md` file for responsible vulnerability disclosure.

**Source Files:**
- `src/tapps_mcp/pipeline/github_governance.py`

**Tasks:**
- [ ] `generate_security_policy(project_root, project_profile=None) -> dict[str, Any]` function
- [ ] Generate `SECURITY.md` with:
  - Supported versions table (with placeholder version numbers)
  - Reporting process (email, GitHub security advisories, or private vulnerability reporting)
  - Response timeline expectations
  - Scope of security issues
  - Link to GitHub's private vulnerability reporting feature
- [ ] Auto-detect project name and version from `pyproject.toml` if available
- [ ] Skip generation if `SECURITY.md` already exists (respect `overwrite` flag)

**Implementation Notes:**
- `SECURITY.md` is recognized by GitHub and linked from the repository's Security tab
- GitHub's private vulnerability reporting is the recommended channel (no external email needed)
- Keep the template minimal — projects will customize it

**Definition of Done:** SECURITY.md template generated with responsible disclosure process.

---

### 22.3 — Ruleset Setup Script Generator

**Points:** 5
**Priority:** Critical
**Status:** Planned

Generate a shell script with `gh api` commands that create recommended repository rulesets.

**Source Files:**
- `src/tapps_mcp/pipeline/github_governance.py`

**Tasks:**
- [ ] `generate_ruleset_script(project_root, project_profile=None) -> dict[str, Any]` function
- [ ] Generate `.github/scripts/setup-rulesets.sh` with:
  - Header with usage instructions and prerequisites (`gh` CLI authenticated)
  - Variables for repo owner, repo name, default branch
  - Ruleset 1 — **Branch Protection**:
    - Target: default branch (`main` or `master`)
    - Rules: require PR, require 1 approval, dismiss stale reviews, require up-to-date branch
    - Block force pushes, block branch deletion
  - Ruleset 2 — **Required Checks**:
    - Require `tapps-quality` status check (from CI workflow)
    - Require `codeql` status check (if CodeQL workflow exists)
    - Strict status checks (require branch to be up-to-date)
  - Ruleset 3 — **Merge Queue** (commented out, opt-in):
    - Enable merge queue with squash merge method
    - Build concurrency: 5
    - Comment explaining when to enable
- [ ] Use `gh api repos/{owner}/{repo}/rulesets --method POST` with JSON payloads
- [ ] Include `--dry-run` flag that prints commands without executing
- [ ] Include rollback instructions (ruleset IDs for deletion)
- [ ] Generate PowerShell equivalent `.github/scripts/setup-rulesets.ps1` for Windows

**Implementation Notes:**
- Rulesets are the modern replacement for branch protection rules
- Rulesets are configurable via REST API: `POST /repos/{owner}/{repo}/rulesets`
- The script is NOT auto-executed — it's generated for the user to review and run manually
- Merge queue configuration is partially API-supported — include as commented-out section
- Organization rulesets (`POST /orgs/{org}/rulesets`) are available on Team plans but require org admin
- Keep the script well-commented so users understand each ruleset's purpose

**Definition of Done:** Shell and PowerShell scripts generated with `gh api` commands for branch protection, required checks, and optional merge queue rulesets.

---

### 22.4 — Post-Init Setup Guide Generator

**Points:** 5
**Priority:** Critical
**Status:** Planned

Generate a comprehensive setup guide covering configurations that can't be done via files alone.

**Source Files:**
- `src/tapps_mcp/pipeline/github_governance.py`

**Tasks:**
- [ ] `generate_setup_guide(project_root, project_profile=None, created_files=None) -> dict[str, Any]` function
- [ ] Generate `docs/GITHUB_SETUP_GUIDE.md` with sections:
  - **What was created** — list of all files generated by `tapps_init` (from `created_files` param)
  - **Next steps: Repository Settings**
    1. Enable GitHub Copilot for the repository
    2. Register TappsMCP as MCP server in Copilot settings (with JSON config example)
    3. Enable Copilot code review via rulesets
    4. Enable secret scanning and push protection
    5. Enable private vulnerability reporting
  - **Next steps: Branch Protection**
    - Run the ruleset setup script: `bash .github/scripts/setup-rulesets.sh`
    - Or manual instructions via GitHub UI
  - **Next steps: GitHub Projects** (optional)
    - Create a project board with recommended views (Table, Board, Roadmap)
    - Auto-add rules for new issues
    - Custom fields: Priority, Sprint, Quality Score
    - `gh` CLI commands for project creation
  - **Next steps: Issue Types** (optional, org-level)
    - `gh api` commands to create organization issue types (Bug, Feature, Task, Epic)
    - Only applicable if user has org admin permissions
  - **Verification**
    - Checklist of all configurations to verify
    - `tapps-mcp doctor` output to confirm MCP connectivity
- [ ] Conditionally include sections based on what was actually generated
- [ ] Include `gh` CLI commands for every manual step where possible

**Implementation Notes:**
- This is the bridge between file-based generation and API/UI-based configuration
- The guide should be actionable — every step has either a `gh` command or a direct link
- GitHub Projects REST API (GA September 2025) makes project creation scriptable
- Issue Types REST API (GA March 2025) makes type creation scriptable
- Copilot MCP server registration is currently UI-only — include screenshots or navigation path
- The guide is project-specific (references actual files created) not generic documentation

**Definition of Done:** Setup guide generated with project-specific next steps, `gh` CLI commands, and verification checklist.

---

### 22.5 — Init/Upgrade Integration

**Points:** 3
**Priority:** Critical
**Status:** Planned

Wire all governance generators into `tapps_init` and `tapps_upgrade`.

**Source Files:**
- `src/tapps_mcp/pipeline/init.py`
- `src/tapps_mcp/pipeline/upgrade.py`
- `src/tapps_mcp/server_pipeline_tools.py`
- `src/tapps_mcp/distribution/doctor.py`

**Tasks:**
- [ ] Add `create_governance: bool = True` parameter to `tapps_init`
- [ ] Call governance generators from `_setup_platform()` in `init.py`
- [ ] Generate setup guide LAST (after all other files are created) so it can reference them
- [ ] Add governance files to `tapps_upgrade` refresh logic
- [ ] Add governance checks to `tapps_doctor`:
  - Check `.github/CODEOWNERS` exists
  - Check `SECURITY.md` exists
  - Warn if setup guide exists but rulesets haven't been applied (heuristic: check if `tapps-quality` is a required check via `gh api`)
- [ ] Report created files in init/upgrade return dict under `"governance"` key
- [ ] Respect `dry_run` flag

**Implementation Notes:**
- Setup guide generation must be the LAST step since it references all created files
- Doctor check for rulesets is best-effort — requires `gh` CLI to be authenticated
- CODEOWNERS and SECURITY.md are generated once and never overwritten (they're meant to be customized)
- Ruleset script and setup guide are refreshed on upgrade (they may reference new workflows)

**Definition of Done:** `tapps_init` creates all governance files. `tapps_upgrade` refreshes scripts and guide. `tapps_doctor` verifies them.

---

### 22.6 — Tests

**Points:** 3
**Priority:** Important
**Status:** Planned

Comprehensive tests for all governance generators.

**Source Files:**
- `tests/unit/test_github_governance.py` (NEW)

**Tasks:**
- [ ] Test `generate_codeowners()` creates file with project-structure paths
- [ ] Test CODEOWNERS includes security-sensitive paths (workflows, lock files)
- [ ] Test CODEOWNERS uses placeholder owners (not hardcoded names)
- [ ] Test `generate_security_policy()` creates SECURITY.md with required sections
- [ ] Test security policy auto-detects project name from pyproject.toml
- [ ] Test `generate_ruleset_script()` creates both .sh and .ps1 scripts
- [ ] Test ruleset script includes branch protection, required checks, and merge queue sections
- [ ] Test ruleset script `gh api` commands have valid JSON payloads
- [ ] Test `generate_setup_guide()` includes all sections
- [ ] Test setup guide references actually created files (from `created_files` param)
- [ ] Test setup guide includes `gh` CLI commands
- [ ] Test idempotency — skip when files exist, overwrite when flag set
- [ ] Test `dry_run` returns plan without writing files
- [ ] Test integration with `tapps_init` (mock project profile)

**Definition of Done:** ~30 new tests covering CODEOWNERS, SECURITY.md, ruleset scripts, and setup guide. Zero mypy/ruff errors.

---

## Architecture Note

This is the capstone epic — Story 22.4 (Post-Init Setup Guide) must run LAST since it references all files created by Epics 19-21. The setup guide is the bridge between what TappsMCP can generate as files and what requires API/UI configuration. Generated shell scripts follow the existing pattern in `platform_generators.py` (lines 26-80) for hook scripts, with both `.sh` and `.ps1` variants. The `_setup_platform()` function in `init.py` should have a `_setup_github_governance()` sub-function (pattern established in Epic 20) that runs after all other generators complete.

## Key Dependencies

- Epic 19 (Issue & PR Templates — referenced in setup guide)
- Epic 20 (CI Enhancement — `tapps-quality` workflow referenced in rulesets, `_setup_platform()` refactoring)
- Epic 21 (Agent Integration — Copilot MCP registration in setup guide)
- Epic 8 (Pipeline Orchestration — `tapps_init` infrastructure)
- Epic 12 (Platform Integration — `platform_generators.py` patterns for script generation)
- `gh` CLI for ruleset creation commands
- GitHub REST API for rulesets (`/repos/{owner}/{repo}/rulesets`)
- GitHub REST API for issue types (`/orgs/{org}/issue-types`)
