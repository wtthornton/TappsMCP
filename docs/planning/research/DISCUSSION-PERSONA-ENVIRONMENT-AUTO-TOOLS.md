# Discussion: Persona / Environment → Auto On/Off Tools

**Date:** 2026-03-11  
**Status:** Discussion only — no commitment to implement  
**Purpose:** Explore whether we should support “set the person or agent for a given environment” so that tools auto turn on/off (e.g. one Claude for “reviewer,” another for Epics/Stories/planning, another for frontend/UX). Review open epics around agents and persona and provide ideas and recommendations.

---

## 1. The idea (user framing)

- **Multiple “environments” or “windows”**, each with a clear **role**:
  - Window A: **Reviewer** — code review, quality gates, security.
  - Window B: **Epics & Stories / Planning** — planning docs, epic/story generation, checklist, validate_changed.
  - Window C: **Frontend / UX** — UI work, maybe score_file + lookup_docs, lighter quality set.
- **Desired behavior:** For a given environment, the **right tools are on** and the rest are off (or de-emphasized) **automatically**, so the model isn’t overwhelmed and doesn’t pick the wrong tool.

So the question is: **should we have something that lets you set the person/agent for an environment and have that drive which tools are enabled?**

---

## 2. How this fits with existing epics

### 2.1 Epic 18 — LLM Engagement Level (complete)

- **What it does:** `llm_engagement_level` (high / medium / low) changes **how many** tools are *required* in the checklist and the tone of rules (MUST vs consider). It does **not** change which tools are *exposed* by the server; it changes **instructions** (AGENTS.md, platform rules, checklist required/recommended sets).
- **Relevance:** We already have a **single dimension** (engagement) that drives “expected tool usage” per task type. A **second dimension** could be “role/persona” that drives **which** tools are exposed (not just required vs optional).

### 2.2 Epic 77 — Agency-Agents Integration (proposed)

- **What it does:** Documents coexistence of TappsMCP’s 4 subagents with agency-agents’ ~120 personas (Frontend Developer, Reality Checker, etc.); optional hint in init/AGENTS.md. No tool list changes.
- **Relevance:** Agency-agents gives you **many personas** (reviewer-like, planner-like, frontend-like). Those personas are **prompts**, not tool sets. So today: “Frontend Developer” and “Reviewer” are different **instructions**, but both sessions could still see **all** TappsMCP tools. Your idea would **add**: when I’m “Frontend Developer,” only a subset of tools is visible or encouraged.

### 2.3 Epic 78 — Canonical Persona Injection (proposed)

- **What it does:** Injects **trusted persona content** (from init/agency-agents files) when the user requests a persona by name, to defend against prompt injection. Does **not** change which tools are on/off.
- **Relevance:** Persona = **who** (definition text). Your idea = **what this session can do** (tool set). They’re complementary: canonical persona defines “who”; role/persona could also select “which tools this who gets.”

### 2.4 Epic 48 — MCP Host Visibility & Agent Fallbacks (complete)

- **What it does:** Docs and fallbacks when the MCP server isn’t visible to the agent (CLI fallback, verification steps). Doesn’t control which tools are exposed.
- **Relevance:** Reminds us that **tool visibility** is determined by (1) which MCP servers the host attaches to the session and (2) which tools those servers (or the gateway) expose. So “environment” could mean “which MCP config / which profile this window uses.”

### 2.5 Epic 79 — MCP Tool Count & Curation (proposed)

- **What it does:** Server-side `enabled_tools` / `disabled_tools` (or presets like `core` / `full`); Docker MCP “core tools” profile and example `tools.yaml`; docs for recommended subsets.
- **Relevance:** This is **exactly** “auto turn on/off tools” at the **mechanism** level. What’s **missing** is a **selector**: who or what decides *which* preset or list applies? Today we have “user sets enabled_tools in config” or “user picks a Docker profile.” Your idea adds: **persona or environment** as that selector.

---

## 3. Ideas and options

### 3.1 Option A: Environment = different connection (profile / MCP config)

**Idea:** Don’t add “persona” inside TappsMCP. Instead, **one environment = one connection profile**. Each Claude/Cursor window uses a **different** MCP config:

- **Reviewer window:** `docker mcp gateway run --profile tapps-reviewer` (or mcp.json pointing to a “reviewer” profile).
- **Planning window:** `docker mcp gateway run --profile tapps-planning`.
- **Frontend window:** `docker mcp gateway run --profile tapps-frontend`.

Each profile has a **curated tools.yaml** (or server list) so that window only sees the right tools. “Setting the person” = **choosing which profile to connect with** when opening that window.

**Pros:** Uses existing Docker MCP profiles + tool filtering; no TappsMCP server changes; clear mental model (one profile per role).  
**Cons:** User must create/import multiple profiles and remember to connect each window to the right one; no single “set role” in chat.

**Recommendation:** Do this **first** as part of Epic 79: ship **persona-named profiles** (e.g. `tapps-reviewer`, `tapps-planning`, `tapps-frontend`) with preconfigured tool lists, and document “use profile X for role Y.” No new concept in the server; just more profiles + docs.

---

### 3.2 Option B: Session-level “role” or “persona” setting (server-side)

**Idea:** User (or the main agent) calls something like `tapps_set_session_role(role="reviewer")` at session start. The server stores “this session = reviewer” and, for the rest of the session, **only advertises** the reviewer tool set in `tools/list`. So the same MCP connection can “switch” tool set by role.

**Pros:** Single connection; user can say “this chat is for review” and get the right tools without changing profile.  
**Cons:** Requires **stateful** tool list per session (MCP servers are often stateless); session identity may be host-dependent (stdio reconnects can look like a new session). More complex to implement and test.

**Recommendation:** Consider only if (1) hosts don’t support multiple profiles per window easily, or (2) we want “switch role mid-session” without reconnecting. Otherwise Option A is simpler.

---

### 3.3 Option C: Config-based default role per project/directory

**Idea:** In `.tapps-mcp.yaml` (or a new file), set `default_role: reviewer` for a given project or directory. When the server starts with that project root, it loads `enabled_tools` (or `tool_preset`) from the **role’s** preset (e.g. “reviewer” → list of review tools). So “environment” = **directory/project**: opening a repo that has `default_role: planner` automatically gets planner tools.

**Pros:** No per-window profile choice; project “remembers” its primary use (e.g. this repo is always opened for planning).  
**Cons:** One project might be used for multiple roles (review one day, plan another); then you’d need override (e.g. `tapps_set_session_role`) or different workspaces with different configs.

**Recommendation:** Good **optional** addition: `default_role` in config that maps to a named tool preset. Epic 79’s `enabled_tools` / `tool_preset` could accept a preset name like `reviewer` | `planner` | `frontend` | `full`, and we document “set default_role in .tapps-mcp.yaml for this project.”

---

### 3.4 Option D: Host tells the server “current agent/persona” (future)

**Idea:** The host (Cursor, Claude Code) passes “current agent” or “persona” at connection time (e.g. via MCP initialize params or a new convention). The server uses that to choose the tool set. No user action.

**Pros:** Fully automatic: open “Frontend Developer” agent → that connection gets frontend tools.  
**Cons:** Not standardized; would require host support and likely MCP spec extension. Out of scope for TappsMCP alone.

**Recommendation:** Track as a **future/ideation** item; if Cursor/Claude ever add “session context” or “agent id” to MCP, we could consume it.

---

## 4. Recommended mapping: persona/role → tool set

If we introduce “role” or “persona” as a selector (in config or in profile names), a reasonable first mapping is:

| Role / Persona   | Primary use              | Suggested tools (TappsMCP)                                                                 | DocsMCP (if combined) |
|------------------|--------------------------|---------------------------------------------------------------------------------------------|-------------------------|
| **reviewer**     | Code review, security    | session_start, quick_check, validate_changed, quality_gate, checklist, security_scan, score_file, dead_code, dependency_scan | —                       |
| **planner**      | Epics, stories, planning | session_start, checklist, validate_changed, quality_gate, score_file, memory, consult_expert | session_start, project_scan, generate_readme, generate_epic, generate_story, check_drift |
| **frontend / UX**| UI, components, design   | session_start, quick_check, score_file, lookup_docs, consult_expert (e.g. user-experience)  | — or minimal            |
| **full**         | General dev              | All tools (or current default)                                                             | All or standard set     |

These can be implemented as:

- **Docker MCP:** One profile per row (e.g. `tapps-reviewer`, `tapps-planning`, `tapps-frontend`) with tools.yaml that enables only those tools.
- **Server config:** `tool_preset: reviewer | planner | frontend | full` and/or `default_role: reviewer` in `.tapps-mcp.yaml`, with a mapping from role → tool list in code or config.

**Full list of role presets to implement first (priority order, tool sets, implementation checklist):** see **[ROLE-PRESETS-IMPLEMENT-FIRST.md](ROLE-PRESETS-IMPLEMENT-FIRST.md)**. It defines nine presets in two phases: Phase 1 — reviewer, planner, frontend, developer, full; Phase 2 — security, refactor, docs, release. Each preset has an exact TappsMCP (and DocsMCP where relevant) tool list and Docker MCP profile name.

---

## 5. Summary recommendations

1. **Use “environment = profile” first (Option A).** Extend Epic 79 (or a follow-on) to ship **persona-named Docker MCP profiles** (reviewer, planner, frontend) with preconfigured tool lists, plus a short doc: “Use profile X for role Y.” No server-side “persona” concept yet; the profile name is the persona.
2. **Add optional `default_role` / `tool_preset` (Option C).** In Epic 79.1 (or a small extension), support presets like `reviewer`, `planner`, `frontend` in addition to `core` | `full`. Allow `default_role: planner` in `.tapps-mcp.yaml` so that when the server starts in that project, it exposes the planner set by default. Gives “this project is for planning” without multiple profiles.
3. **Document the mental model.** In AGENTS.md or a “Roles and tools” doc: “For different kinds of work (review, planning, frontend), use different Docker MCP profiles or set default_role so only the relevant tools are exposed.” Link to Epic 77 (personas) and Epic 78 (canonical persona) so it’s clear: **persona** = who (definition); **role** = which tool set (what this session can do).
4. **Leave session-level role switch (Option B) and host-driven persona (Option D) for later.** Implement only if users ask for “switch role without reconnecting” or when hosts provide session/agent context.

---

## 6. References

- [EPIC-18-LLM-ENGAGEMENT-LEVEL.md](../epics/EPIC-18-LLM-ENGAGEMENT-LEVEL.md) — engagement drives required/recommended tools
- [EPIC-77-AGENCY-AGENTS-INTEGRATION.md](../epics/EPIC-77-AGENCY-AGENTS-INTEGRATION.md) — TappsMCP + agency-agents coexistence
- [EPIC-78-CANONICAL-PERSONA-INJECTION-PROMPT-INJECTION-DEFENSE.md](../epics/EPIC-78-CANONICAL-PERSONA-INJECTION-PROMPT-INJECTION-DEFENSE.md) — canonical persona content injection
- [EPIC-79-MCP-TOOL-COUNT-CURATION.md](../epics/EPIC-79-MCP-TOOL-COUNT-CURATION.md) — enabled_tools, presets, Docker core-tools profile
- [2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md](2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md) — agents, personas, canonical injection
- [TOOL-TIER-RANKING.md](../TOOL-TIER-RANKING.md) — Tier 1/2/3/4 for mapping role → tools
