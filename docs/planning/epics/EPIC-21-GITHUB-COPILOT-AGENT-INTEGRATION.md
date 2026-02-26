# Epic 21: GitHub Copilot Agent Integration

**Status:** Complete (Stories 21.1–21.7)
**Priority:** P0 — Critical (MCP is now GitHub's standard for AI tool integration; Copilot coding agent is GA)
**Estimated LOE:** ~2.5-3 weeks (1 developer)
**Dependencies:** Epic 8 (Pipeline Orchestration), Epic 12 (Platform Integration), Epic 20 (CI Enhancement)
**Blocks:** None

---

## Goal

Make TappsMCP-initialized repositories fully compatible with GitHub's AI agent ecosystem: Copilot coding agent, Copilot code review, custom agent profiles, path-scoped instructions, and the new agentic workflows (technical preview). Generate all configuration files so that AI agents working on the repository automatically have access to TappsMCP quality tools and follow the TAPPS pipeline.

## Why This Epic Exists

GitHub's AI agent ecosystem underwent a fundamental shift in 2025-2026:

1. **MCP is the standard** — GitHub deprecated App-based Copilot Extensions (sunset November 2025) in favor of MCP. TappsMCP's architecture as an MCP server is exactly the right pattern. MCP is GA across VS Code, JetBrains, Eclipse, Xcode, and Visual Studio.

2. **Copilot coding agent is GA** — Assign a GitHub issue to Copilot and it autonomously creates a branch, writes code, commits, and opens a PR. It runs in a GitHub Actions environment and reads `AGENTS.md`, `CLAUDE.md`, and `.github/copilot-instructions.md` for guidance.

3. **Custom agent profiles** (October 2025) — Teams can define specialized agents (`.github/agents/*.md`) with YAML frontmatter specifying name, description, prompt, available tools, and MCP server configurations.

4. **Path-scoped instructions** (September 2025) — `.github/instructions/*.instructions.md` files with YAML frontmatter apply different AI rules to different parts of the codebase.

5. **Copilot code review is GA** — Automatic reviews via rulesets with full project context, CodeQL integration, and custom review standards via instruction files.

6. **Agentic Workflows** (technical preview February 2026) — AI agents run as part of CI, written in Markdown instead of YAML. Supports Claude Code, Copilot, and OpenAI Codex.

7. **Copilot Spaces** (GA September 2025) — Curated context repositories that Copilot uses for grounded answers.

TappsMCP already generates `AGENTS.md` and `.github/copilot-instructions.md`, but these need enhancement to leverage the new features, and several new file types need generation.

## LLM Error Sources Addressed

| Error Source | How This Epic Helps |
|---|---|
| Copilot coding agent ignores quality checks | Custom agent profile includes TappsMCP MCP server, ensuring quality tools are available |
| Copilot code review misses project conventions | Path-scoped instructions teach review to check TappsMCP-scored patterns |
| Agent-created PRs lack quality validation | Agentic workflow template runs TappsMCP gate before merge |
| Different agents get inconsistent instructions | Unified instruction hierarchy ensures all agents follow the same quality standards |
| Copilot coding agent lacks quality tools | copilot-setup-steps.yml (Epic 20) + MCP config ensures tools are available |
| New agents don't discover TappsMCP | Custom agent profiles explicitly wire TappsMCP as an MCP dependency |

## 2026 Best Practices Applied

- **`.github/agents/*.md`** custom agent profiles with YAML frontmatter
- **`.github/instructions/*.instructions.md`** path-scoped instructions
- **Enhanced `.github/copilot-instructions.md`** with TappsMCP workflow steps
- **`AGENTS.md`** as first-class citizen (supported by Copilot since August 2025)
- **Agentic Workflows** Markdown-based CI automation (technical preview)
- **Copilot code review instructions** via `excludeAgent` property
- **MCP server registration** for Copilot coding agent

## Acceptance Criteria

- [ ] Custom agent profile generated: `.github/agents/tapps-quality.md`
- [ ] Path-scoped instructions generated for quality review patterns
- [ ] Enhanced `copilot-instructions.md` with TappsMCP pipeline stages
- [ ] Agentic workflow template generated for quality-check automation
- [ ] All instruction files follow GitHub's 2025-2026 format specifications
- [ ] Agent profile includes MCP server configuration for TappsMCP
- [ ] New `github` domain expert registered with 10+ knowledge files
- [ ] Domain detection keywords cover Actions, Issues, PRs, rulesets, Copilot, agentic workflows
- [ ] `tapps_consult_expert(domain="github")` and `tapps_research` return GitHub-specific guidance
- [ ] All generators integrated into `tapps_init` and `tapps_upgrade`
- [ ] All changes covered by unit tests
- [ ] Zero mypy/ruff errors

## Implementation Order

```
Story 21.1 (Custom Agent Profile) ──────────► Story 21.5 (Init/Upgrade Wire)
                                                      │
Story 21.2 (Path-Scoped Instructions) ──────────────┤
                                                      │
Story 21.3 (Enhanced Copilot Instructions) ─────────┤
                                                      │
Story 21.4 (Agentic Workflow Templates) ────────────┤
                                                      │
Story 21.7 (GitHub Domain Expert) ─────────────────┤
                                                      │
                                                Story 21.6 (Tests)
```

---

## Stories

### 21.1 — Custom Agent Profile Generator

**Points:** 5
**Priority:** Critical
**Status:** Planned

Generate custom Copilot agent profiles in `.github/agents/` that define quality-focused agents backed by TappsMCP's MCP tools.

**Source Files:**
- `src/tapps_mcp/pipeline/github_agents.py` (NEW)

**Tasks:**
- [ ] Create `github_agents.py` module in `pipeline/`
- [ ] `generate_agent_profiles(project_root, project_profile=None) -> dict[str, Any]` function
- [ ] Generate `.github/agents/tapps-quality.md` with YAML frontmatter:
  ```yaml
  ---
  name: "quality-reviewer"
  description: "Reviews code quality, security, and maintainability using TappsMCP"
  tools:
    - "tapps_score_file"
    - "tapps_quality_gate"
    - "tapps_security_scan"
    - "tapps_quick_check"
    - "tapps_validate_changed"
    - "tapps_dependency_scan"
    - "tapps_dependency_graph"
    - "tapps_dead_code"
  ---
  ```
- [ ] Body content: detailed instructions for the quality agent's behavior
  - Run `tapps_session_start` first
  - Score files after changes with `tapps_quick_check`
  - Run `tapps_validate_changed` before completing
  - Check for security issues with `tapps_security_scan`
  - Report quality metrics in PR comments
- [ ] Generate `.github/agents/tapps-researcher.md` for documentation/expert consultation:
  - Tools: `tapps_lookup_docs`, `tapps_consult_expert`, `tapps_research`, `tapps_list_experts`
  - Instructions: research libraries before using them, consult domain experts for architectural decisions
- [ ] Skip generation if files exist (respect `overwrite` flag)

**Implementation Notes:**
- Agent profiles are Markdown files with YAML frontmatter — GitHub's custom agents specification
- The Copilot coding agent reads these when invoked from github.com, Copilot CLI, or VS Code
- `tools:` lists available tools — the Copilot coding agent only supports MCP tools (not resources or prompts)
- MCP server must be registered in repository Copilot settings (not auto-configurable via files alone)
- Secrets for MCP servers come from the "copilot" environment in repository settings

**Definition of Done:** Two agent profiles generated that provide quality and research capabilities via TappsMCP.

---

### 21.2 — Path-Scoped Instruction Generator

**Points:** 5
**Priority:** Critical
**Status:** Planned

Generate path-scoped instruction files in `.github/instructions/` that teach Copilot code review and the coding agent to apply different quality rules to different parts of the codebase.

**Source Files:**
- `src/tapps_mcp/pipeline/github_agents.py`

**Tasks:**
- [ ] `generate_path_instructions(project_root, project_profile=None) -> dict[str, Any]` function
- [ ] Generate `.github/instructions/quality.instructions.md` with YAML frontmatter:
  ```yaml
  ---
  applyTo: "**/*.py"
  ---
  ```
  - Body: Python quality rules — run ruff, type-check with mypy, no print() statements, use structlog for logging, handle exceptions properly, avoid bare except
- [ ] Generate `.github/instructions/security.instructions.md`:
  ```yaml
  ---
  applyTo: "**/*.py"
  ---
  ```
  - Body: Security rules — no hardcoded secrets, validate all file paths, sanitize user input, use parameterized queries, no `eval()` or `exec()`
- [ ] Generate `.github/instructions/testing.instructions.md`:
  ```yaml
  ---
  applyTo: "tests/**/*.py"
  ---
  ```
  - Body: Testing rules — use pytest fixtures, descriptive test names, cover happy path and edge cases, mock external dependencies, assert specific values not just truthiness
- [ ] Auto-detect primary language from project profile for instruction content
- [ ] Skip generation if files exist (respect `overwrite` flag)

**Implementation Notes:**
- Path-scoped instructions were GA September 2025
- `applyTo:` supports glob patterns (same as `.gitignore` syntax)
- Instructions are used by both Copilot code review AND the Copilot coding agent
- The `excludeAgent:` property can restrict which agent sees the instructions (review vs coding)
- Keep instructions concise — GitHub's analysis of 2,500+ AGENTS.md files shows concrete examples work better than verbose rules

**Definition of Done:** Three path-scoped instruction files generated covering quality, security, and testing patterns.

---

### 21.3 — Enhanced Copilot Instructions

**Points:** 3
**Priority:** Important
**Status:** Planned

Upgrade the existing `generate_copilot_instructions()` to include TappsMCP pipeline stages, tool references, and the full quality workflow.

**Source Files:**
- `src/tapps_mcp/pipeline/platform_generators.py`

**Tasks:**
- [ ] Update `generate_copilot_instructions()` in `platform_generators.py`
- [ ] Add TappsMCP pipeline stages (Discover → Research → Develop → Validate → Verify)
- [ ] Add explicit tool call sequence:
  1. Start: `tapps_session_start()`
  2. After edits: `tapps_quick_check(file_path)`
  3. For domain questions: `tapps_research(question)`
  4. Before completion: `tapps_validate_changed()`
  5. Final check: `tapps_checklist(task_type)`
- [ ] Add reference to custom agent profiles (`.github/agents/`)
- [ ] Add reference to path-scoped instructions (`.github/instructions/`)
- [ ] Include version marker comment for `tapps_upgrade` tracking
- [ ] Backward compatible — existing installs updated via `tapps_upgrade`

**Implementation Notes:**
- This file already exists in TappsMCP — this story enhances it, not replaces it
- The coding guidelines feature is deprecated (July 2025) — all customization now goes through `copilot-instructions.md` and `*.instructions.md`
- Keep the file concise — Copilot works better with clear, short instructions
- Include concrete code examples where possible (GitHub's recommendation)

**Definition of Done:** Enhanced `copilot-instructions.md` includes full TappsMCP workflow with concrete tool call examples.

---

### 21.4 — Agentic Workflow Templates

**Points:** 5
**Priority:** Important
**Status:** Planned

Generate Markdown-based agentic workflow templates for the GitHub Agentic Workflows system (technical preview February 2026). These let AI agents run TappsMCP quality checks as part of CI.

**Source Files:**
- `src/tapps_mcp/pipeline/github_agents.py`

**Tasks:**
- [ ] `generate_agentic_workflows(project_root) -> dict[str, Any]` function
- [ ] Generate `.github/workflows/tapps-quality-review.md` — agentic workflow for PR quality review:
  - YAML frontmatter with trigger: `pull_request`
  - Agent: configurable (Claude Code, Copilot, or Codex)
  - Markdown body describing the task: "Review the PR for code quality issues using TappsMCP tools"
  - Steps: run `tapps_session_start`, score changed files, run quality gate, post findings as PR comment
- [ ] Generate `.github/workflows/tapps-issue-triage.md` — agentic workflow for issue triage:
  - Trigger: `issues.opened`
  - Task: classify issue, suggest labels, check for duplicates
- [ ] Add prominent comment noting these require the `gh aw` CLI extension (technical preview)
- [ ] Make agent backend configurable via YAML frontmatter field
- [ ] Skip generation if files exist (respect `overwrite` flag)
- [ ] Gate behind a `create_agentic_workflows: bool = False` flag (opt-in since technical preview)

**Implementation Notes:**
- Agentic Workflows are in **technical preview** (February 2026) — gate behind opt-in flag
- The `gh aw` CLI compiles Markdown into `.lock.yml` GitHub Actions workflows with SHA-pinned dependencies
- Supported agents: GitHub Copilot, Claude Code, OpenAI Codex
- Security model: read-only access, firewall-restricted, content sanitization, safe outputs for writes
- These complement (not replace) traditional YAML workflows — they're for tasks that benefit from AI flexibility
- Mark generated files clearly as "Agentic Workflow (Technical Preview)" to set expectations

**Definition of Done:** Two agentic workflow templates generated (quality review and issue triage) gated behind opt-in flag.

---

### 21.7 — GitHub Domain Expert

**Points:** 8
**Priority:** Critical
**Status:** Planned

Add a 17th built-in domain expert for GitHub — covering Actions, Issues, PRs, rulesets, Copilot agent integration, agentic workflows, and repository governance. This ensures `tapps_consult_expert` and `tapps_research` can give GitHub-specific guidance grounded in RAG knowledge files, not just generic advice.

**Source Files:**
- `src/tapps_mcp/experts/registry.py`
- `src/tapps_mcp/experts/domain_detector.py`
- `src/tapps_mcp/experts/knowledge/github/` (NEW — 10 knowledge files)
- `tests/unit/test_github_expert.py` (NEW)

**Tasks:**
- [ ] Register `github` domain in `TECHNICAL_DOMAINS` set in `registry.py`
- [ ] Add `ExpertConfig` entry in `BUILTIN_EXPERTS`:
  ```python
  ExpertConfig(
      expert_id="expert-github",
      expert_name="GitHub Platform Expert",
      primary_domain="github",
      description="GitHub Actions, Issues, PRs, rulesets, Copilot agent integration, and repository governance.",
  )
  ```
- [ ] Add domain keywords to `DOMAIN_KEYWORDS` in `domain_detector.py`:
  ```python
  "github": [
      "github", "github actions", "workflow", "github workflow",
      "pull request", "merge queue", "branch protection", "ruleset",
      "issue template", "issue form", "sub-issue",
      "dependabot", "codeql", "code scanning", "secret scanning",
      "push protection", "codeowners",
      "copilot", "coding agent", "copilot agent", "copilot review",
      "agentic workflow", "copilot setup steps",
      "artifact attestation", "slsa", "github runner",
      "github mcp", "github project", "github api",
  ]
  ```
- [ ] Create `src/tapps_mcp/experts/knowledge/github/` directory with 10 knowledge files:

**Knowledge files to create:**

1. **`github-actions-best-practices.md`** (~300 lines)
   - SHA-pinning actions, minimal permissions, concurrency groups
   - Artifacts v4 patterns, timeout configuration
   - Reusable workflows (10 nested, 50 total)
   - Arm64 runners (37% cheaper), cost optimization
   - `workflow_dispatch` with 25 inputs
   - Secret management (OIDC vs long-lived secrets)

2. **`github-actions-ci-patterns.md`** (~250 lines)
   - Python CI workflow patterns (setup-python, uv, pip, caching)
   - Matrix strategies for multi-version testing
   - Conditional jobs and job outputs
   - Parallel test execution patterns
   - Upload/download artifact patterns (v4)

3. **`github-issues-and-forms.md`** (~300 lines)
   - Issue forms YAML syntax (all body element types)
   - Issue types (Bug, Feature, Task — org-level REST API)
   - Sub-issues (8 levels, GraphQL mutations, progress tracking)
   - Template config (`config.yml`, disabling blank issues)
   - Labels, milestones, projects auto-assignment

4. **`github-pull-requests.md`** (~250 lines)
   - PR templates (single-file and multi-file patterns)
   - Auto-merge configuration and patterns
   - Merge queues (configuration, `merge_group` trigger)
   - Draft PRs, stacked PRs, PR review workflows
   - Dependabot PR management and grouped updates

5. **`github-rulesets-and-governance.md`** (~350 lines)
   - Rulesets vs legacy branch protection rules
   - Repository rulesets (REST API: `POST /repos/{owner}/{repo}/rulesets`)
   - Organization rulesets (Team plan+, June 2025)
   - Required checks, required reviews, merge queue rules
   - Bypass actors, enforcement levels
   - CODEOWNERS patterns and required review by specific teams

6. **`github-copilot-agent-setup.md`** (~300 lines)
   - Copilot coding agent overview (GA, issue-to-PR workflow)
   - `copilot-setup-steps.yml` environment configuration
   - `copilot-instructions.md` and path-scoped `*.instructions.md`
   - Custom agent profiles (`.github/agents/*.md` with YAML frontmatter)
   - Copilot code review (automatic via rulesets, custom standards)
   - AGENTS.md best practices (from GitHub's analysis of 2,500+ repos)
   - MCP server registration for the coding agent

7. **`github-agentic-workflows.md`** (~250 lines)
   - Agentic Workflows overview (technical preview February 2026)
   - Markdown-based workflow authoring with YAML frontmatter
   - `gh aw` CLI compilation to `.lock.yml`
   - Supported agents (Copilot, Claude Code, OpenAI Codex)
   - Security model (read-only, safe outputs, sandboxed execution)
   - Use cases: triage, docs, CI failure investigation, quality hygiene

8. **`github-security-features.md`** (~300 lines)
   - CodeQL code scanning (incremental analysis, Action v4, Copilot autofix)
   - Secret scanning and push protection (custom patterns, delegated bypass)
   - Dependabot (uv support, grouped updates, auto-merge)
   - Artifact attestations and SLSA (Level 2 with attestations, Level 3 with reusable workflows)
   - GitHub Secret Protection and Code Security (standalone products)
   - Security overview dashboard

9. **`github-projects-api.md`** (~250 lines)
   - GitHub Projects v2 (50,000 item limit)
   - REST API for Projects (GA September 2025)
   - Built-in automations (auto-status, auto-add, auto-archive)
   - Custom fields, views (Table, Board, Roadmap)
   - Webhooks for project events
   - Issue Types REST API (org-level, March 2025)

10. **`github-mcp-integration.md`** (~250 lines)
    - GitHub's official MCP server (50+ tools)
    - Toolsets: context, issues, pull_requests, repos, users, projects
    - Lockdown mode and content sanitization (December 2025)
    - Tool-specific configuration via `X-MCP-Tools` header
    - Prompt injection protection patterns
    - Building MCP servers for GitHub integration

- [ ] Ensure all knowledge files use consistent markdown structure: H1 title, H2 sections, code examples, best practices lists, checklists
- [ ] Verify RAG retrieval works for GitHub queries (knowledge files auto-discovered via `rglob("*.md")`)

**Tests (in `test_github_expert.py`):**
- [ ] Test `github` domain is registered in `TECHNICAL_DOMAINS`
- [ ] Test `ExpertConfig` entry exists with correct `expert_id` and `primary_domain`
- [ ] Test domain detection: "How do I set up GitHub Actions?" → `github` domain detected
- [ ] Test domain detection: "Configure branch protection rulesets" → `github` domain detected
- [ ] Test domain detection: "Set up Copilot coding agent" → `github` domain detected
- [ ] Test domain detection does NOT false-match: "git commit" should not trigger `github` (git != github)
- [ ] Test knowledge directory exists with 10 `.md` files
- [ ] Test RAG retrieval: query "github actions best practices" returns relevant chunks
- [ ] Test RAG retrieval: query "copilot setup steps" returns relevant chunks
- [ ] Test `tapps_consult_expert(question="...", domain="github")` returns non-empty response with confidence > 0

**Implementation Notes:**
- The expert system auto-discovers knowledge files via `rglob("*.md")` — no code changes needed beyond registration and keywords
- Domain detection uses `\b` word-boundary regex — "github" won't false-match on "git" alone
- Multi-word keywords like "github actions" get higher weight (1.5 vs 1.0) for better precision
- The 10 knowledge files total ~2,750 lines of curated, 2026-current GitHub guidance
- Content is sourced from the research performed for Epics 19-22 — all features verified against official GitHub docs and changelogs
- RAG chunking handles files up to 10 MB — these files are well within limits
- Expert RAG warming (`warm_expert_rag_from_tech_stack`) will auto-build the index for projects that use GitHub Actions

**Definition of Done:** `tapps_consult_expert(domain="github")` returns RAG-backed guidance. Domain detection routes GitHub-related questions correctly. 10 knowledge files cover Actions, Issues, PRs, rulesets, Copilot, agentic workflows, security, Projects, and MCP. ~15 new tests verify registration, detection, and retrieval.

---

### 21.5 — Init/Upgrade Integration

**Points:** 3
**Priority:** Critical
**Status:** Planned

Wire all agent-related generators into `tapps_init` and `tapps_upgrade`.

**Source Files:**
- `src/tapps_mcp/pipeline/init.py`
- `src/tapps_mcp/pipeline/upgrade.py`
- `src/tapps_mcp/server_pipeline_tools.py`
- `src/tapps_mcp/distribution/doctor.py`

**Tasks:**
- [ ] Add `create_agent_profiles: bool = True` parameter to `tapps_init`
- [ ] Add `create_agentic_workflows: bool = False` parameter to `tapps_init` (opt-in)
- [ ] Call agent generators from `_setup_platform()` in `init.py`
- [ ] Add agent files to `tapps_upgrade` refresh logic
- [ ] Add agent checks to `tapps_doctor`:
  - Check `.github/agents/tapps-quality.md` exists
  - Check `.github/instructions/quality.instructions.md` exists
  - Warn if `copilot-instructions.md` is outdated (version marker check)
- [ ] Report created files in init/upgrade return dict under `"github_agents"` key
- [ ] Respect `dry_run` flag

**Implementation Notes:**
- Agent profiles and instructions are platform-agnostic (not Claude/Cursor specific) — generate for all platforms
- Agentic workflows gated behind opt-in flag since they're in technical preview
- Enhanced copilot-instructions.md replaces the existing generated version

**Definition of Done:** `tapps_init` creates all agent configuration. `tapps_upgrade` refreshes them. `tapps_doctor` verifies them.

---

### 21.6 — Tests

**Points:** 5
**Priority:** Important
**Status:** Planned

Comprehensive tests for all agent generators, instruction generators, and the GitHub domain expert.

**Source Files:**
- `tests/unit/test_github_agents.py` (NEW)
- `tests/unit/test_github_expert.py` (NEW — see Story 21.7 for expert-specific test tasks)

**Tasks:**
- [ ] Test `generate_agent_profiles()` creates quality and researcher agent files
- [ ] Test agent profile YAML frontmatter has correct `name`, `tools`, `description` fields
- [ ] Test agent profile body includes TappsMCP tool call sequence
- [ ] Test `generate_path_instructions()` creates quality, security, and testing instruction files
- [ ] Test instruction YAML frontmatter has correct `applyTo` glob patterns
- [ ] Test instruction content includes language-specific rules
- [ ] Test enhanced `generate_copilot_instructions()` includes pipeline stages
- [ ] Test `generate_agentic_workflows()` creates Markdown workflows with YAML frontmatter
- [ ] Test agentic workflows are not generated when `create_agentic_workflows=False`
- [ ] Test agentic workflows are generated when `create_agentic_workflows=True`
- [ ] Test idempotency — skip when files exist, overwrite when flag set
- [ ] Test `dry_run` returns plan without writing files
- [ ] Test integration with `tapps_init` (mock project profile)
- [ ] GitHub expert tests (in `test_github_expert.py` — detailed in Story 21.7)

**Definition of Done:** ~45 new tests covering agent profiles, instructions, agentic workflows, GitHub domain expert, and integration. Zero mypy/ruff errors.

---

## Architecture Note

Agent profiles (`.github/agents/`) and path-scoped instructions (`.github/instructions/`) are Markdown files with YAML frontmatter — generated as string templates, not via PyYAML. The enhanced `generate_copilot_instructions()` stays in `platform_generators.py` (line ~1677) since it already exists there. All new generators go in `github_agents.py`. The `generate_copilot_instructions()` function currently writes the `_COPILOT_INSTRUCTIONS` string constant — Story 21.3 replaces that constant with the enhanced version and adds a version marker comment for `tapps_upgrade` tracking.

Context7 lookup for "github copilot" returned the Neovim copilot.lua plugin, not GitHub's Copilot platform docs — this validates the need for Story 21.7 (GitHub Domain Expert) to fill the knowledge gap.

## Key Dependencies

- Epic 8 (Pipeline Orchestration — `tapps_init` infrastructure)
- Epic 12 (Platform Integration — `platform_generators.py` patterns)
- Epic 20 (CI Enhancement — `copilot-setup-steps.yml` for agent environment)
- Epic 3 (Expert System — registry, domain detector, knowledge file infrastructure for Story 21.7)
- GitHub Copilot custom agents specification (October 2025)
- GitHub path-scoped instructions format (September 2025)
- GitHub Agentic Workflows `gh aw` CLI (technical preview February 2026)
