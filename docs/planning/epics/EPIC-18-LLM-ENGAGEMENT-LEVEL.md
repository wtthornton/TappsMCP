# Epic 18: LLM Engagement Level Configuration

**Status:** Planned
**Priority:** P2 — Enables customer control over TappsMCP enforcement intensity
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** Epic 0 (Foundation), Epic 6 (Distribution), Epic 8 (Pipeline), Epic 12 (Platform Integration)
**Blocks:** None

---

## Goal

Allow customers to configure **how intensely** the LLM uses TappsMCP tools — from mandatory enforcement (high) to optional guidance (low). Customers can say "set tappsmcp to high" or "set tappsmcp to low" and have the configuration persist. Instruction files (AGENTS.md, platform rules, hooks, skills) vary their language and tool requirements by engagement level.

## Problem Statement

| Gap | Impact |
|-----|--------|
| Single enforcement tone | High-compliance teams want stronger language; exploratory teams want lighter touch |
| No engagement-level config | One-size-fits-all AGENTS.md and platform rules |
| Config requires file editing | Users cannot say "set tappsmcp to high" — must edit YAML manually |
| Checklist is task-based only | Same required tools regardless of project rigor preferences |

## Solution

Introduce `llm_engagement_level` (high | medium | low) as a first-class config option. Templates, checklist, hooks, and workflow prompts vary by level. Add `tapps_set_engagement_level` MCP tool so users can change level via natural language.

## 2026 Best Practices Applied

- **Pydantic v2** for config validation — `Literal["high", "medium", "low"]` with validation
- **Path safety** — `tapps_set_engagement_level` uses path validator; writes only within `TAPPS_MCP_PROJECT_ROOT`
- **Backward compatibility** — Default `medium` preserves current behavior; `load_agents_template()` with no arg returns medium variant
- **Deterministic** — Same engagement level yields same template output; no LLM calls in tool chain

## Engagement Level Semantics

| Level | Alias | Behavior |
|-------|-------|----------|
| **high** | always | Mandatory language (MUST, BLOCKING, REQUIRED). More tools required in checklist. All hooks active. |
| **medium** | majority | Balanced. Current defaults. Standard recommended workflow. |
| **low** | sometimes | Softer language (consider, optional). Fewer required tools. Minimal or no hooks. |

## Acceptance Criteria

- [ ] `llm_engagement_level` config option in `.tapps-mcp.yaml` and `TAPPS_MCP_LLM_ENGAGEMENT_LEVEL` env var
- [ ] `tapps_init` accepts `llm_engagement_level` and generates level-appropriate templates
- [ ] Three variants of AGENTS.md template (high / medium / low) with different language intensity
- [ ] Three variants of platform rules (platform_cursor.md, platform_claude.md) per engagement level
- [ ] Checklist `TASK_TOOL_MAP` varies by engagement level (more required at high, fewer at low)
- [ ] `tapps_set_engagement_level(level)` MCP tool writes to `.tapps-mcp.yaml` and optionally regenerates templates
- [ ] `tapps-mcp init --engagement-level high|medium|low` CLI flag
- [ ] Hooks vary content by engagement level (stronger reminders at high, lighter at low)
- [ ] `tapps_workflow` prompt optionally varies framing by level
- [ ] README and AGENTS.md document engagement levels and how to change them

## Implementation Order

Stories have dependencies; recommended sequence:

```
18.1 (Config) ─┬─► 18.2 (AGENTS.md) ─┬─► 18.5 (Init/CLI)
               │                     │
               └─► 18.3 (Platform)   └─► 18.7 (Hooks/Skills)
               │
               └─► 18.4 (Checklist) ─► independent

18.6 (tapps_set_engagement_level) ─► after 18.1, 18.5
18.8 (Workflow + docs) ─► can parallel with 18.6
```

---

## Stories

### 18.1 — Configuration Foundation

**Points:** 2

Add `llm_engagement_level` to the settings model and config surface.

**Tasks:**
- Add `llm_engagement_level: Literal["high", "medium", "low"] = "medium"` to `TappsMCPSettings` in `config/settings.py`; use `Field(description=...)` per existing pattern
- Add `TAPPS_MCP_LLM_ENGAGEMENT_LEVEL` env var support via pydantic-settings
- Add `llm_engagement_level` to `config/default.yaml`
- Update `_load_yaml_config` merge so `.tapps-mcp.yaml` can override
- Add `ENGAGEMENT_LEVELS = ("high", "medium", "low")` constant
- Unit tests: settings load correctly from YAML and env; invalid value raises `ValidationError`; default is `medium` when omitted

**Definition of Done:** `llm_engagement_level` is readable from config. Default is `medium`. Regression: existing `.tapps-mcp.yaml` without the key still loads.

---

### 18.2 — AGENTS.md Template Variants

**Points:** 3

Create three variants of the AGENTS.md template with engagement-level-specific language.

**Tasks:**
- Create `prompts/agents_template_high.md` — MUST, REQUIRED, BLOCKING language
- Create `prompts/agents_template_medium.md` — current `agents_template.md` content (balanced)
- Create `prompts/agents_template_low.md` — consider, optional, softer language
- Extend `prompt_loader.load_agents_template(engagement_level: str) -> str` to select variant
- Keep backward compatibility: `load_agents_template()` with no arg returns `medium` variant
- Update `pipeline/init.py` and `agents_md.py` merge logic to pass `engagement_level` from config
- Unit tests: all three variants load; merge produces valid AGENTS.md for each level

**Definition of Done:** `tapps_init` with `llm_engagement_level=high` generates AGENTS.md with mandatory language.

---

### 18.3 — Platform Rules Variants

**Points:** 3

Create engagement-level variants for platform rules (Cursor and Claude Code).

**Tasks:**
- Create `prompts/platform_cursor_high.md`, `platform_cursor_medium.md`, `platform_cursor_low.md`
- Create `prompts/platform_claude_high.md`, `platform_claude_medium.md`, `platform_claude_low.md`
- Extend platform generators to accept `engagement_level` and select correct template
- High: MANDATORY, BLOCKING, MUST, NEVER (current platform_cursor.md style)
- Medium: Should, recommended
- Low: Consider, optional, lighter reminders
- Update `pipeline/platform_generators.py` and `pipeline/init.py` to pass engagement level
- Unit tests: correct platform rule content for each level

**Definition of Done:** `tapps_init` with `llm_engagement_level=low` generates platform rules with softer language.

---

### 18.4 — Checklist by Engagement Level

**Points:** 2

Vary checklist required/recommended/optional tools by engagement level.

**Tasks:**
- Define `TASK_TOOL_MAP_HIGH`, `TASK_TOOL_MAP_MEDIUM`, `TASK_TOOL_MAP_LOW` in `tools/checklist.py`
- High: promote more tools from recommended → required (e.g., feature: add `tapps_security_scan` to required)
- Low: reduce required tools (e.g., feature: only `tapps_quality_gate` required)
- Extend `CallTracker.evaluate(task_type, engagement_level: str | None = None)` — when None, read from `load_settings().llm_engagement_level`
- Wire `engagement_level` from `load_settings()` into checklist evaluation
- Unit tests: checklist result varies by engagement level for same task type

**Definition of Done:** `tapps_checklist(task_type="feature")` returns different `missing_required` for high vs low.

---

### 18.5 — tapps_init and CLI Integration

**Points:** 2

Wire `llm_engagement_level` through `tapps_init` and `tapps-mcp init` CLI.

**Tasks:**
- Add `llm_engagement_level: Literal["high", "medium", "low"] = None` to `tapps_init` tool (None = use config)
- When `llm_engagement_level` provided, use it for template selection; when None, read from settings
- Add `--engagement-level high|medium|low` to `tapps-mcp init` in `distribution/setup_generator.py`
- If `--engagement-level` provided, write `llm_engagement_level` to `.tapps-mcp.yaml` during init
- Update `BootstrapConfig` in `pipeline/init.py` to include `llm_engagement_level`
- Integration tests: init with each level produces distinct AGENTS.md and platform rules

**Definition of Done:** `tapps-mcp init --engagement-level high` creates high-enforcement project files.

---

### 18.6 — tapps_set_engagement_level MCP Tool

**Points:** 3

Add MCP tool so users can say "set tappsmcp to high" or "set tappsmcp to low".

**Tasks:**
- Implement `tapps_set_engagement_level(level: Literal["high", "medium", "low"]) -> str` in `server_pipeline_tools.py`
- Tool reads/creates `.tapps-mcp.yaml` in project root
- Updates or adds `llm_engagement_level: <level>`
- Returns summary including next step: e.g. "Engagement level set to high. Run tapps_init with overwrite_agents_md=True to regenerate AGENTS.md and platform rules."
- Use path validator to ensure write is within `TAPPS_MCP_PROJECT_ROOT`
- Add tool to server.py registration
- Add to AGENTS.md template "When to use" table: `tapps_set_engagement_level` — When user requests to change enforcement intensity (e.g. "set tappsmcp to high")
- Update `pipeline/agents_md.py` EXPECTED_TOOLS list to include `tapps_set_engagement_level` for validation
- Unit tests: tool updates YAML correctly; invalid level rejected; path safety enforced (reject write outside project root)
- Consider MCP elicitation: when `level` omitted and client supports elicitation, prompt user to choose level (optional enhancement)

**Definition of Done:** User says "set tappsmcp to high"; LLM calls `tapps_set_engagement_level(level="high")`; config updated. Tool preserves other keys in `.tapps-mcp.yaml`.

---

### 18.7 — Hooks and Skills by Engagement Level

**Points:** 2

Vary hook script content and skill priority by engagement level.

**Tasks:**
- Extend `platform_generators.py` hook templates to support engagement-level variants
- High: all hooks active, strong "MUST" language in echo messages
- Medium: current behavior
- Low: fewer hooks (e.g., only SessionStart), softer "consider" language
- Skills: add engagement-level note in skill descriptions (MANDATORY vs optional)
- Update `_setup_platform` in init to pass engagement level to generators
- Unit tests: hook content differs by level

**Definition of Done:** High-engagement init produces hooks that say "MUST run tapps_quick_check"; low produces "Consider tapps_quick_check".

---

### 18.8 — tapps_workflow and Documentation

**Points:** 2

Vary workflow prompt framing by engagement level and document the feature.

**Tasks:**
- Extend `tapps_workflow(task_type, engagement_level=None)` to vary framing (optional — can defer to config)
- High: "You MUST call these tools in order"
- Medium: "Recommended tool call order"
- Low: "Optional workflow — consider these tools"
- README: add "LLM Engagement Level" section (high/medium/low, how to set)
- AGENTS.md template: add row for `tapps_set_engagement_level` in tool table
- CLAUDE.md (TappsMCP dev): add note about engagement-level template variants
- Update `tapps_doctor` to report current `llm_engagement_level` if present

**Definition of Done:** README explains engagement levels. `tapps_doctor` shows engagement level when configured.

---

## Key Dependencies (Codebase)

- `config/settings.py` — TappsMCPSettings
- `pipeline/init.py` — BootstrapConfig, template creation
- `pipeline/platform_generators.py` — hooks, rules, skills
- `tools/checklist.py` — TASK_TOOL_MAP
- `distribution/setup_generator.py` — CLI init

## Success Metrics

- User can say "set tappsmcp to high" and config updates via `tapps_set_engagement_level`
- High-enforcement project has MUST/REQUIRED language; low has consider/optional
- Checklist required tools differ by level
- All existing tests pass; new tests cover engagement-level behavior
