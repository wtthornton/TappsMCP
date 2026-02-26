# Epic 19: GitHub Issue & PR Templates

**Status:** Complete (Stories 19.1–19.6)
**Priority:** P1 — High (structured issue/PR templates make repos agent-parseable and reduce noise)
**Estimated LOE:** ~1.5-2 weeks (1 developer)
**Dependencies:** Epic 8 (Pipeline Orchestration), Epic 12 (Platform Integration)
**Blocks:** Epic 22 (Governance & Security)

---

## Goal

Generate structured GitHub Issue form templates, PR templates, and Dependabot configuration as part of `tapps_init`. These files make repositories machine-parseable for AI agents (Copilot coding agent, Claude Code, agentic workflows) and establish consistent contribution patterns from day one.

## Why This Epic Exists

GitHub's 2025-2026 feature evolution has made Issues and PRs fundamentally more structured:

1. **Issue Forms (GA 2025)** replace freeform Markdown templates with YAML-defined structured forms — dropdowns, checkboxes, validated inputs. AI agents can parse these programmatically.
2. **Issue Types (GA 2025)** allow org-level classification (Bug, Feature, Task). Issue forms can auto-set the type via the `type:` key.
3. **Sub-Issues (GA 2025)** enable parent-child hierarchies up to 8 levels deep with progress tracking via `subIssuesSummary`.
4. **PR templates** standardize what information accompanies every pull request — critical when AI agents are autonomously creating PRs via Copilot coding agent or agentic workflows.
5. **Dependabot now supports `uv`** (GA 2025) — TappsMCP projects use `uv`, so generating the right ecosystem config is essential.
6. **Grouped Dependabot updates** (GA July 2025) reduce PR noise by combining security updates across ecosystems into a single PR.

Without structured templates, AI agents create issues and PRs with inconsistent formatting that humans must manually triage. TappsMCP can eliminate this by generating best-practice templates during `tapps_init`.

## LLM Error Sources Addressed

| Error Source | How This Epic Helps |
|---|---|
| Unstructured issue reports | Issue forms force required fields (reproduction steps, environment, expected behavior) |
| Missing PR context | PR template enforces Summary, Test Plan, Breaking Changes sections |
| Agent-created PRs lack testing info | PR template includes a "Test plan" section that agents must fill |
| Outdated dependencies go unnoticed | Dependabot config auto-creates PRs for vulnerable packages |
| Inconsistent issue classification | Issue forms auto-apply labels and types |
| Blank issues with no context | Template config disables blank issues, provides contact links |

## 2026 Best Practices Applied

- **Issue Forms YAML syntax** (not legacy Markdown templates) with structured `body` elements
- **`type:` key** in issue forms to auto-set organization issue types
- **`projects:` key** in issue forms to auto-add to GitHub Projects
- **Dependabot `uv` ecosystem** support (GA March 2025)
- **Multi-ecosystem grouped updates** via `groups` with `applies-to: security-updates`
- **Template config** (`config.yml`) to disable blank issues and add contact links

## Acceptance Criteria

- [ ] `generate_issue_templates(project_root, project_profile)` creates `.github/ISSUE_TEMPLATE/` directory
- [ ] Bug report form: structured YAML with reproduction steps, environment, expected behavior
- [ ] Feature request form: structured YAML with problem description, proposed solution, alternatives
- [ ] Task form: lightweight YAML for internal work tracking
- [ ] Template config: `config.yml` disabling blank issues
- [ ] `generate_pr_template(project_root)` creates `.github/PULL_REQUEST_TEMPLATE.md`
- [ ] `generate_dependabot_config(project_root, project_profile)` creates `.github/dependabot.yml`
- [ ] Dependabot config auto-detects ecosystems from project profile (pip/uv, npm, docker, github-actions)
- [ ] All generators integrated into `tapps_init` flow and `tapps_upgrade` refresh
- [ ] All generators are idempotent (skip if files exist, overwrite flag available)
- [ ] All changes covered by unit tests
- [ ] Zero mypy/ruff errors

## Implementation Order

```
Story 19.1 (Issue Forms) ──► Story 19.3 (Template Config)
                                    │
Story 19.2 (PR Template) ──────────┤
                                    │
Story 19.4 (Dependabot) ───────────┤
                                    │
                              Story 19.5 (Init/Upgrade Integration)
                                    │
                              Story 19.6 (Tests)
```

---

## Stories

### 19.1 — Issue Form Template Generator

**Points:** 5
**Priority:** Critical
**Status:** Planned

Generate structured GitHub Issue form templates (YAML) in `.github/ISSUE_TEMPLATE/`. Templates use the 2025 issue forms syntax with typed body elements, validation, labels, and optional issue type/project assignment.

**Source Files:**
- `src/tapps_mcp/pipeline/github_templates.py` (NEW)

**Tasks:**
- [ ] Create `github_templates.py` module in `pipeline/`
- [ ] `generate_issue_templates(project_root, project_profile=None) -> dict[str, Any]` function
- [ ] Generate `bug-report.yml`:
  - `name`, `description`, `title` prefix `[Bug]: `
  - `labels: ["bug", "triage"]`
  - `type: "Bug"` (organization issue type)
  - Body elements: markdown greeting, textarea for description (required), textarea for reproduction steps (required), input for expected behavior, dropdown for severity (Critical/High/Medium/Low), textarea for environment (render: shell), checkboxes for "searched existing issues"
- [ ] Generate `feature-request.yml`:
  - `name`, `description`, `title` prefix `[Feature]: `
  - `labels: ["enhancement"]`
  - `type: "Feature"`
  - Body elements: textarea for problem/motivation (required), textarea for proposed solution (required), textarea for alternatives considered, dropdown for scope (Small/Medium/Large), checkboxes for "willing to contribute"
- [ ] Generate `task.yml`:
  - `name`, `description`, `title` prefix `[Task]: `
  - `labels: ["task"]`
  - `type: "Task"`
  - Body elements: textarea for description (required), textarea for acceptance criteria, dropdown for priority (P0-P3)
- [ ] Auto-detect project name from `pyproject.toml` or directory name for template descriptions
- [ ] Templates written via `yaml.dump()` with `default_flow_style=False` for clean output
- [ ] Skip generation if `.github/ISSUE_TEMPLATE/` already exists (respect `overwrite` flag)

**Implementation Notes:**
- Use PyYAML (`pyyaml>=6.0.3` already a project dependency — used in `config/settings.py`)
- `yaml.safe_dump(data, default_flow_style=False, sort_keys=False)` for clean block-style output
- Issue forms require `.yml` extension (not `.yaml`)
- The `type:` key only works if the organization has issue types configured — include a comment noting this
- `projects:` key requires `org/project-number` format — omit by default, document how to add

**Definition of Done:** Three issue form templates generated with structured YAML syntax, typed body elements, and auto-labeling.

---

### 19.2 — PR Template Generator

**Points:** 3
**Priority:** Critical
**Status:** Planned

Generate a structured pull request template that AI agents (Copilot coding agent, Claude Code) and humans can fill consistently.

**Source Files:**
- `src/tapps_mcp/pipeline/github_templates.py`

**Tasks:**
- [ ] `generate_pr_template(project_root) -> dict[str, Any]` function
- [ ] Generate `.github/PULL_REQUEST_TEMPLATE.md` with sections:
  - `## Summary` — brief description of changes
  - `## Changes` — bulleted list of what changed
  - `## Test plan` — how changes were tested
  - `## Breaking changes` — any breaking changes (or "None")
  - `## Related issues` — `Closes #` or `Fixes #` references
  - `## Checklist` — checkboxes: tests pass, no new warnings, docs updated if needed
- [ ] Template uses HTML comments (`<!-- ... -->`) for section guidance that disappears when filled
- [ ] Skip generation if `.github/PULL_REQUEST_TEMPLATE.md` already exists (respect `overwrite` flag)

**Implementation Notes:**
- PR templates are Markdown (not YAML) — simple string generation
- Copilot coding agent auto-fills PR descriptions using the repo's template, so structure matters
- Keep sections minimal — agents work better with clear, short prompts than verbose instructions
- GitHub supports multiple PR templates in `.github/PULL_REQUEST_TEMPLATE/`, but single-file is the standard pattern

**Definition of Done:** PR template generated with agent-friendly sections that Copilot coding agent can auto-fill.

---

### 19.3 — Issue Template Config Generator

**Points:** 2
**Priority:** Important
**Status:** Planned

Generate the `.github/ISSUE_TEMPLATE/config.yml` that controls the template chooser behavior.

**Source Files:**
- `src/tapps_mcp/pipeline/github_templates.py`

**Tasks:**
- [ ] `generate_template_config(project_root, project_profile=None) -> dict[str, Any]` function
- [ ] Generate `config.yml` with:
  - `blank_issues_enabled: false` — force use of structured templates
  - `contact_links:` — optional external links (discussions, docs)
- [ ] Auto-detect if project has GitHub Discussions URL from project profile
- [ ] Skip generation if `config.yml` already exists in `.github/ISSUE_TEMPLATE/` (respect `overwrite` flag)

**Implementation Notes:**
- `config.yml` is optional but recommended — disabling blank issues forces structured input
- Contact links are helpful for routing support questions away from the issue tracker

**Definition of Done:** Template config generated that disables blank issues and optionally adds contact links.

---

### 19.4 — Dependabot Configuration Generator

**Points:** 5
**Priority:** Critical
**Status:** Planned

Generate `.github/dependabot.yml` with ecosystem-aware configuration, including `uv` support (GA March 2025) and grouped security updates (GA July 2025).

**Source Files:**
- `src/tapps_mcp/pipeline/github_templates.py`

**Tasks:**
- [ ] `generate_dependabot_config(project_root, project_profile=None) -> dict[str, Any]` function
- [ ] Auto-detect ecosystems from project profile:
  - `pyproject.toml` with `uv.lock` → `package-ecosystem: "uv"`
  - `pyproject.toml` with `requirements.txt` → `package-ecosystem: "pip"`
  - `package.json` → `package-ecosystem: "npm"`
  - `Dockerfile` → `package-ecosystem: "docker"`
  - `.github/workflows/` → `package-ecosystem: "github-actions"`
- [ ] Configure weekly schedule for each detected ecosystem
- [ ] Add grouped security updates:
  ```yaml
  groups:
    production-dependencies:
      applies-to: security-updates
      dependency-type: "production"
    development-dependencies:
      applies-to: version-updates
      dependency-type: "development"
  ```
- [ ] Set `open-pull-requests-limit: 10` per ecosystem
- [ ] Add `labels: ["dependencies"]` for all ecosystems
- [ ] Add `labels: ["security"]` for security update groups
- [ ] Skip generation if `.github/dependabot.yml` already exists (respect `overwrite` flag)

**Implementation Notes:**
- Dependabot `uv` support is GA for both version updates (March 2025) and security updates (December 2025)
- The `groups` feature with `applies-to: security-updates` was GA July 2025
- `directory` defaults to `"/"` — adjust if project profile detects monorepo structure
- GitHub Actions ecosystem catches outdated action versions (important for SHA-pinning)

**Definition of Done:** Dependabot config generated with auto-detected ecosystems, `uv` support, and grouped security updates.

---

### 19.5 — Init/Upgrade Integration

**Points:** 3
**Priority:** Critical
**Status:** Planned

Wire all generators into the `tapps_init` bootstrap flow and `tapps_upgrade` refresh flow.

**Source Files:**
- `src/tapps_mcp/pipeline/init.py`
- `src/tapps_mcp/pipeline/upgrade.py`
- `src/tapps_mcp/server_pipeline_tools.py`

**Tasks:**
- [ ] Add `create_github_templates: bool = True` parameter to `tapps_init` MCP tool
- [ ] Call `generate_issue_templates()`, `generate_pr_template()`, `generate_template_config()`, `generate_dependabot_config()` from `_setup_platform()` in `init.py`
- [ ] Pass `project_profile` to generators that use ecosystem detection
- [ ] Add GitHub templates to `tapps_upgrade` refresh logic — regenerate with `overwrite` when `force=True`
- [ ] Add GitHub templates to `tapps_doctor` checks — verify `.github/ISSUE_TEMPLATE/` exists
- [ ] Report created files in init/upgrade return dict under `"github_templates"` key
- [ ] Respect `dry_run` flag — report what would be created without writing

**Implementation Notes:**
- GitHub templates should be generated for ALL platforms (not just Claude/Cursor) since they're GitHub-specific, not IDE-specific
- Run after platform-specific setup but before cache warming
- Template generation is fast (pure string/YAML output) — no impact on init duration

**Definition of Done:** `tapps_init` and `tapps_upgrade` create/refresh all GitHub templates. `tapps_doctor` checks for their existence.

---

### 19.6 — Tests

**Points:** 3
**Priority:** Important
**Status:** Planned

Comprehensive tests for all GitHub template generators.

**Source Files:**
- `tests/unit/test_github_templates.py` (NEW)

**Tasks:**
- [ ] Test `generate_issue_templates()` creates 3 YAML files with correct structure
- [ ] Test bug report form has required fields (description, reproduction steps)
- [ ] Test feature request form has required fields (problem, proposed solution)
- [ ] Test task form has required fields (description)
- [ ] Test all forms have valid YAML syntax (parse output with yaml.safe_load)
- [ ] Test `generate_pr_template()` creates Markdown with all required sections
- [ ] Test `generate_template_config()` creates valid YAML with `blank_issues_enabled: false`
- [ ] Test `generate_dependabot_config()` detects ecosystems from project profile
- [ ] Test `uv` ecosystem detection when `uv.lock` exists
- [ ] Test `pip` ecosystem fallback when only `requirements.txt` exists
- [ ] Test `github-actions` ecosystem detected from `.github/workflows/`
- [ ] Test grouped security updates in Dependabot config
- [ ] Test idempotency — skip when files exist, overwrite when flag set
- [ ] Test integration with `tapps_init` (mock project profile)
- [ ] Test `dry_run` returns plan without writing files

**Definition of Done:** ~35 new tests covering all template generators, ecosystem detection, and init/upgrade integration. Zero mypy/ruff errors.

---

## Architecture Note

The existing `platform_generators.py` is already 1,700+ lines. Epics 19-22 collectively add 4 new generator modules (`github_templates.py`, `github_workflows.py`, `github_agents.py`, `github_governance.py`) rather than extending `platform_generators.py` further. This split follows single-responsibility: platform generators handle IDE-specific files (hooks, agents, skills, rules), while the new modules handle GitHub-specific files (`.github/` directory contents). The `_setup_platform()` function in `init.py` should be refactored into sub-functions (`_setup_github_templates()`, `_setup_github_workflows()`, etc.) to keep it maintainable as more generators are added.

## Key Dependencies

- Epic 8 (Pipeline Orchestration — `tapps_init` infrastructure)
- Epic 12 (Platform Integration — `platform_generators.py` patterns)
- Epic 4 (Project Context — `project_profile` for ecosystem detection)
- PyYAML (`pyyaml>=6.0.3` — already a project dependency)
