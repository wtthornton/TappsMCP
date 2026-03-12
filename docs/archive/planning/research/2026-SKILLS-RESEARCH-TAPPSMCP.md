# 2026 Skills Research: Are We Doing It Wrong?

**Date:** 2026-03-11  
**Scope:** Compare TappsMCP skill implementation (`.claude/skills/`, `.cursor/skills/`) against the Agent Skills standard and platform docs. Identify gaps and fix recommendations.

**Sources:** agentskills.io specification, mdskills.ai, Cursor docs (cursor.com/docs/skills), Claude Code docs, prompt-engineering guides.

---

## 1. The standard: SKILL.md (Agent Skills)

- **Spec:** [agentskills.io/specification](https://agentskills.io/specification); open standard supported by Claude Code, Cursor, Codex, Gemini CLI, VS Code, GitHub Copilot, and 27+ agents.
- **Structure:** One folder per skill; folder name must match `name` in frontmatter. Minimum: `skill-name/SKILL.md` with YAML frontmatter + markdown body.
- **Progressive disclosure:** Metadata (~100 tokens) for discovery; full SKILL.md when activated (<5000 tokens / ~500 lines recommended); optional `scripts/`, `references/`, `assets/` loaded on demand.

### 1.1 Required frontmatter (spec)

| Field | Constraints |
|-------|-------------|
| **name** | Required. Max 64 chars. Lowercase letters, numbers, hyphens only. No leading/trailing hyphen, no consecutive hyphens. **Must match parent directory name.** |
| **description** | Required. 1–1024 characters. What the skill does and **when to use it**; include keywords for discovery. |

### 1.2 Optional frontmatter (spec)

| Field | Notes |
|-------|--------|
| license | SPDX or reference to license file |
| compatibility | Max 500 chars; environment requirements |
| metadata | Arbitrary key-value map |
| **allowed-tools** | **Space-delimited** list of pre-approved tools. **Experimental**; support varies by agent. |

### 1.3 Body

- No format mandate. Recommended: edge cases, examples, step-by-step instructions. Keep under ~500 lines / 5000 tokens; put long reference in `references/` or `assets/`.

---

## 2. What TappsMCP does

### 2.1 Claude Code skills (`.claude/skills/`)

- **Required:** `name`, `description` ✓
- **Extended frontmatter (Claude-specific):**
  - `user-invocable: true`
  - `model: claude-haiku-4-5-20251001` (or sonnet for review-pipeline)
  - `allowed-tools:` **space-delimited** per agentskills.io spec (e.g. `mcp__tapps-mcp__tapps_score_file mcp__tapps-mcp__tapps_quick_check`)
  - `argument-hint: "[file-path]"`
  - `disable-model-invocation: true` (for gate, validate)
  - `context: fork`, `agent: general-purpose` (review-pipeline only)
- **Body:** Short numbered steps; references MCP tools by full name (`mcp__tapps-mcp__...`).
- **Folder names:** `tapps-score`, `tapps-gate`, etc. Match `name` ✓

### 2.2 Cursor skills (`.cursor/skills/`)

- **Required:** `name`, `description` ✓
- **Tool list:** Uses **`mcp_tools:`** as a YAML list, e.g.:
  ```yaml
  mcp_tools:
    - tapps_score_file
    - tapps_quick_check
  ```
  Tool names **without** `mcp__tapps-mcp__` prefix.
- **No** `allowed-tools`, `user-invocable`, `model`, `argument-hint` in Cursor skills (by design in tests: "Cursor skills should NOT use allowed-tools").
- **Body:** Same procedural content as Claude, but tool names without prefix (e.g. `tapps_quick_check`).
- **Folder names:** Same as Claude ✓

---

## 3. Where we’re aligned

| Aspect | Status |
|--------|--------|
| One folder per skill, `SKILL.md` inside | ✓ |
| `name` matches directory (e.g. `tapps-score`) | ✓ |
| `name` lowercase, hyphens, no bad patterns | ✓ |
| `description` present and task/when-to-use | ✓ |
| `description` length 1–1024 enforced (test + validator) | ✓ Epic 76.1 |
| Body: steps, examples, focused content | ✓ |
| Body length well under 500 lines | ✓ |
| No mandatory use of scripts/references/assets | ✓ (optional) |
| Claude: `disable-model-invocation` for “only when I invoke” | ✓ Matches Cursor/Claude docs |

---

## 4. Where we might be wrong or non-standard

### 4.1 `allowed-tools` format (Claude)

- **Spec:** “Space-delimited list.”
- **TappsMCP:** **Space-delimited** in CLAUDE_SKILLS per agentskills.io. Validator rejects comma-separated.
- **Status:** Implemented; tests and `tapps-mcp validate-skills` enforce (Epic 76.2).

### 4.2 Cursor: `mcp_tools` vs `allowed-tools`

- **Spec:** Only defines optional `allowed-tools` (space-delimited). Cursor’s own docs list only: name, description, license, compatibility, metadata, disable-model-invocation. **Cursor does not document `allowed-tools` or `mcp_tools`.**
- **TappsMCP:** Uses **`mcp_tools`** (YAML list) for Cursor; tests enforce “Cursor uses mcp_tools, not allowed-tools.”
- **Risk:** If Cursor implements the standard and only reads `allowed-tools`, our Cursor skills would have **no** tool allowlist. If Cursor supports `mcp_tools` as an extension, we’re fine. Not verifiable from public Cursor docs.
- **Recommendation:** (1) Prefer **`allowed-tools`** for Cursor as well (space-delimited, tool names in whatever form Cursor expects, e.g. `tapps_score_file` or `mcp__tapps-mcp__tapps_score_file`) for spec compliance and portability. (2) If Cursor is known to require `mcp_tools`, document that and keep it; add a short comment in code/tests.

### 4.3 Claude-only frontmatter

- **Spec:** Only name, description, license, compatibility, metadata, allowed-tools. No `user-invocable`, `model`, `argument-hint`, `context`, `agent`.
- **TappsMCP:** Uses these for Claude Code behavior (slash commands, model choice, subagent).
- **Verdict:** **Not wrong.** These are **platform extensions**. The spec allows agents to support extra fields. Claude Code documents or supports them. Keeping them under a single platform (Claude) is correct; Cursor correctly omits them.

### 4.4 Description length

- **Spec:** description 1–1024 **characters**.
- **TappsMCP:** Some descriptions are multi-line (`>-`). Enforced in test_platform_skills.py and skills_validator; all skills pass (Epic 76.1).
- **Recommendation:** Add a test or validation that each skill’s `description` is ≤1024 characters (after stripping/joining as needed).

### 4.5 Tool naming (Cursor)

- **TappsMCP Cursor:** Body and `mcp_tools` use short names (`tapps_quick_check`). Claude uses full names (`mcp__tapps-mcp__tapps_quick_check`).
- **Verdict:** Reasonable: Cursor may resolve tools by short name when one MCP server is in use. No change needed unless Cursor docs require a specific format.

---

## 5. Summary: are we doing it wrong?

| Item | Verdict | Action |
|------|--------|--------|
| Structure (folder + SKILL.md, name = dir) | ✓ Correct | None |
| Required fields (name, description) | ✓ Correct | None |
| Body length and content | ✓ Correct | None |
| Claude extended fields (user-invocable, model, etc.) | ✓ OK (platform extension) | None |
| **allowed-tools: comma vs space (Claude)** | ✓ Done | Space-delimited in CLAUDE_SKILLS (Epic 76.2) |
| **Cursor: mcp_tools vs allowed-tools** | ✓ Documented | Keep mcp_tools; documented as Cursor extension (Epic 76.3) |
| **Description ≤1024 chars** | ✓ Done | Test + validator (Epic 76.1, 76.4) |

**Bottom line:** We follow the standard for structure, required fields, description length, and Claude allowed-tools format. Cursor uses `mcp_tools` by design; documented.

---

## 6. Recommended next steps

1. ~~**Validate description length**~~ — Done (Epic 76.1): test + validator.
2. ~~**Claude allowed-tools**~~ — Done (Epic 76.2): space-delimited.
3. ~~**Cursor tool field**~~ — Documented (Epic 76.3): keep mcp_tools.
4. ~~**Optional validator**~~ — Done (Epic 76.4): `validate_skill_frontmatter()`, tests, `tapps-mcp validate-skills`.
