# Epic 50: Consumer Requirements & Verification

**Status:** Open
**Priority:** P1
**Estimated LOE:** ~1–1.5 weeks
**Dependencies:** Epic 48 (MCP Host Visibility & Agent Fallbacks), Epic 49 (Doctor Robustness)
**Blocks:** None
**Source:** Consuming project requirements — `OpenClawAgents/docs/TAPPS_MCP_REQUIREMENTS.md` (2026-03-05)

---

## Goal

Make the **“what you need to use most TappsMCP tools”** checklist first-class in TappMCP. Adopt the consumer requirements document as canonical documentation, link it from README/AGENTS.md and troubleshooting, align `tapps-mcp doctor` with the seven requirements where applicable, and ensure init/upgrade flows point consumers to it so agents and users have one clear place to verify readiness.

## Problem Statement

OpenClawAgents produced a concise requirements checklist (TAPPS_MCP_REQUIREMENTS.md) that summarizes:

1. **TappsMCP server available to the agent** — server must appear in the host’s available MCP servers list.
2. **MCP config in the project** — host must load a config that defines the tapps-mcp server (command, args, env).
3. **Tool permissions (Claude Code)** — `permissions.allow` must include `mcp__tapps-mcp` and `mcp__tapps-mcp__*`.
4. **Bootstrap (init)** — run init once so project profile, tech stack, experts, and memory have context.
5. **Python (for scoring tools)** — scoring/quality-gate tools target Python; other tools work without Python.
6. **CLI fallback** — when MCP tools aren’t available, use CLI for init/upgrade/doctor.
7. **Quick verification checklist** — table mapping each requirement to “how to verify.”

This aligns with TappMCP’s existing behavior and with Epic 48 (visibility + CLI fallback). The gap is that this checklist lives only in a consuming repo; TappMCP itself does not yet own a canonical “requirements” doc or tie doctor/docs to it.

### Impact

| Gap | Severity | Benefit of addressing |
|-----|----------|------------------------|
| No single “what you need” doc in TappMCP | Medium | One canonical checklist for all consumers and agents |
| Doctor not explicitly mapped to the 7 requirements | Low | Clearer “requirements view” in doctor output |
| Init/upgrade don’t point to requirements | Low | New users see the checklist early |

---

## Stories

### Story 50.1: Adopt canonical Consumer Requirements doc in TappMCP

**LOE:** S (~2–3 hours)
**Files:** `docs/TAPPS_MCP_REQUIREMENTS.md` (new), `README.md`, `AGENTS.md`

Create (or adapt from OpenClawAgents) a canonical **TAPPS_MCP_REQUIREMENTS.md** in the TappMCP repo under `docs/`, covering the seven requirements:

1. TappsMCP server available to the agent  
2. MCP config in the project  
3. Tool permissions (Claude Code)  
4. Bootstrap (init) so project context exists  
5. Python for scoring/quality-gate tools  
6. CLI fallback when MCP tools aren’t available  
7. Quick verification checklist (table)

- Keep wording consistent with existing AGENTS.md “Troubleshooting: MCP server not available” and “Tool permissions” sections; avoid duplication by having the requirements doc be the source of truth and AGENTS.md linking to it (or summarizing briefly and linking).
- Add a short “What you need” or “Requirements” section in README that links to `docs/TAPPS_MCP_REQUIREMENTS.md`.
- In AGENTS.md (or generated content), add a pointer to the requirements doc in troubleshooting and/or “Session start” so agents can discover it.

**Acceptance Criteria:**

- `docs/TAPPS_MCP_REQUIREMENTS.md` exists and contains all seven requirements plus the summary and verification table.
- README links to the requirements doc from an obvious place (e.g. “What you need” or “Requirements”).
- AGENTS.md (or pipeline-generated troubleshooting) references the requirements doc where relevant.
- Content is accurate for Cursor, VS Code, and Claude Code.

---

### Story 50.2: Map doctor checks to the seven requirements

**LOE:** S (~2–3 hours)
**Files:** `packages/tapps-mcp/src/tapps_mcp/distribution/doctor.py`, `docs/TAPPS_MCP_REQUIREMENTS.md`

Document how each of the seven consumer requirements maps to existing (or future) doctor checks. Optionally add a **“Requirements summary”** section to doctor output that reports pass/fail or N/A per requirement.

- **Requirement 1 (server available):** Not directly checkable by doctor (agent/host responsibility). Doctor can report “MCP config present” and suggest verifying in-session.
- **Requirement 2 (MCP config):** Already covered by `check_cursor_config`, `check_vscode_config`, `check_claude_code_project` / `check_claude_code_user`.
- **Requirement 3 (permissions):** Already covered by `check_claude_settings` (mcp__tapps-mcp, mcp__tapps-mcp__*).
- **Requirement 4 (bootstrap):** Partially covered by `check_agents_md`, `check_cursor_rules`, hooks; init-run is not directly detectable.
- **Requirement 5 (Python):** Covered by `check_quality_tools()`; doc can state “optional for scoring tools.”
- **Requirement 6 (CLI fallback):** Doc-only; doctor itself is the CLI fallback.
- **Requirement 7 (verification table):** Implement as a short “Requirements” block in doctor output (e.g. a compact table with Check / How / Status), or as a pointer to `docs/TAPPS_MCP_REQUIREMENTS.md` in doctor’s final output.

**Acceptance Criteria:**

- `docs/TAPPS_MCP_REQUIREMENTS.md` (or a short “Doctor and requirements” section in docs) explains the mapping from each requirement to doctor checks.
- Doctor output either includes a compact “Requirements” summary (e.g. 7 rows with status) or ends with a line pointing to the requirements doc for the full checklist.
- No regression in existing doctor behavior; new content is additive.

---

### Story 50.3: Reference requirements in init and upgrade flows

**LOE:** XS (~1 hour)
**Files:** `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`, `packages/tapps-mcp/src/tapps_mcp/distribution/setup_generator.py` (or upgrade path), docs/skills

After a successful `tapps_init` (and optionally after `tapps-mcp upgrade`), surface a short message or link so users know where to find the full “what you need” checklist.

- **Init:** Add an optional post-init message (or append to existing success message) such as: “For a full checklist of what you need to use most tools (server visibility, permissions, CLI fallback), see docs/TAPPS_MCP_REQUIREMENTS.md” (or the in-repo path when run from a consuming project: e.g. “See TappMCP docs: Consumer requirements”).
- **Upgrade:** If upgrade prints a success summary, add a one-line pointer to the requirements doc.
- **Skills:** Ensure tapps-init skill (and tapps-validate/tool-reference where relevant) mention the requirements doc or quick verification table when discussing “first-time setup” or “troubleshooting.”

**Acceptance Criteria:**

- Init success path (MCP tool and/or CLI) references the consumer requirements doc or quick verification checklist.
- Upgrade success path (CLI) references the requirements doc where appropriate.
- Generated or in-repo skill content for init/validate includes a pointer to the requirements doc for first-time setup and troubleshooting.
- No breaking changes to init/upgrade output; additions are concise (one line or bullet).

---

## Out of Scope

- Changing host behavior (how Cursor/Claude Code/VS Code expose MCP servers or enforce permissions).
- Adding new MCP tools; this epic is documentation, doctor output alignment, and init/upgrade/skill messaging only.
- Implementing Epic 49 (doctor quick mode) inside this epic; Epic 50 can reference “quick mode” in the requirements doc once Epic 49 is done.

---

## Success Criteria

- TappMCP has a single canonical “what you need” document (`docs/TAPPS_MCP_REQUIREMENTS.md`) covering all seven requirements and the verification table.
- README and AGENTS.md (or generated troubleshooting) link to that doc.
- Doctor output is explicitly mapped to the requirements (and optionally includes a compact requirements summary or link).
- Init and upgrade (and relevant skills) point users and agents to the requirements doc so “minimum to use most tools” is discoverable from within the product.
