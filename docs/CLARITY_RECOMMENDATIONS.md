# TappsMCP clarity recommendations

Recommendations to make it clearer **when** and **how** an LLM (or human) should use TappsMCP tools. Focus: tool names, tool descriptions, server discovery, checklist feedback, and documentation.

---

## 1. Tool names

**Current:** `tapps_server_info`, `tapps_score_file`, `tapps_security_scan`, `tapps_quality_gate`, `tapps_lookup_docs`, `tapps_validate_config`, `tapps_consult_expert`, `tapps_list_experts`, `tapps_checklist`.

**Recommendations:**

- **Keep the `tapps_` prefix** — Good for namespacing and avoiding clashes with other MCP tools.
- **Keep existing names** — Renaming would break clients and checklist task maps; clarity gains are better achieved via descriptions and docs.
- **Optional future:** If adding new tools, prefer **action-oriented** names (e.g. `tapps_check_quality_gate` rather than `tapps_quality_gate`) so the verb is obvious. Not worth a breaking rename for current tools.

---

## 2. Tool descriptions (docstrings)

**Current:** Descriptions are accurate but often start with *what* the tool does, not *when* to use it. LLMs tend to weight the first sentence heavily when choosing tools.

**Recommendations:**

- **Lead with "When to use" or "Call this when..."** in the first line of each tool docstring, then keep the current technical details.
- **Example (tapps_quality_gate):**  
  - Before: *"Evaluate a Python file against quality gate thresholds."*  
  - After: *"Call before declaring work complete. Evaluates a Python file against quality gate thresholds (pass/fail) for the given preset."*
- Apply the same pattern to all tools so the model sees the trigger condition first.

**Status:** Implemented in `server.py` docstrings.

---

## 3. Server discovery: `tapps_server_info`

**Current:** Returns version, `available_tools`, `installed_checkers`, and config. No workflow guidance.

**Recommendations:**

- **Add a `recommended_workflow` (or `usage_hint`) field** to the JSON so the first tool call teaches the LLM the intended flow, e.g.:
  - *"Call tapps_server_info at session start; use tapps_score_file (quick) during edits, tapps_score_file (full) and tapps_quality_gate before done; call tapps_checklist before declaring work complete."*
- Keep it short (one or two sentences) so it doesn’t bloat context.

**Status:** Implemented: `data.recommended_workflow` in `tapps_server_info` response.

---

## 4. Checklist: explain *why* a tool is missing

**Current:** Checklist returns `missing_required`, `missing_recommended`, `missing_optional` as **lists of tool names** only. The LLM sees "tapps_quality_gate" is missing but not *why* it matters.

**Recommendations:**

- **Return a short reason/hint per missing tool**, e.g.:
  - `missing_required`: `[{"tool": "tapps_quality_gate", "reason": "Call before declaring work complete to ensure the file passes the configured quality preset."}]`
  - Same idea for recommended/optional with softer wording.
- **Backward compatibility:** Add a new field (e.g. `missing_required_hints`) so existing clients that only use `missing_required` still work; document the new field in the tools reference.

**Status:** Implemented: checklist returns `missing_required_hints`, `missing_recommended_hints`, `missing_optional_hints` with `{ "tool", "reason" }` objects.

---

## 5. Documentation

**Current:** README and setup docs are human-oriented. No single place that says "If you are an AI assistant, use these tools in this order."

**Recommendations:**

- **Add AGENTS.md (or docs/FOR_AI_ASSISTANTS.md):** A short, LLM-facing doc that:
  - States what TappsMCP is (one sentence).
  - Lists each tool with one line: *when* to use it.
  - Gives the recommended workflow (session start → during edits → before done → checklist).
  - Mentions that tools are only available when the TappsMCP MCP server is configured in the host.
- **README:** Add a small "For AI assistants" section that either inlines the workflow or points to AGENTS.md.
- **Optional:** If the MCP SDK supports it, expose a **prompt template** (e.g. `@mcp.prompt()`) that injects the same workflow so the host can offer "Insert TappsMCP workflow" to the user.

**Status:** AGENTS.md added; README updated with "For AI assistants" and link to AGENTS.md.

---

## 6. Parameter descriptions

**Current:** Parameters have descriptions in the docstring Args section; MCP may surface these as parameter descriptions.

**Recommendations:**

- **task_type (tapps_checklist):** Clarify: *"Task context: 'feature' | 'bugfix' | 'refactor' | 'security' | 'review'. Use 'review' for general code review, 'feature' for new code, 'security' for security-focused changes."*
- **preset (tapps_quality_gate):** Already clear; optional: *"standard (70+), strict (80+), framework (75+ with higher security bar)."*
- **library (tapps_lookup_docs):** Add: *"Call before writing code that uses this library to avoid hallucinated APIs."*

**Status:** Reflected in server.py docstrings where relevant.

---

## 7. Optional: MCP resources/prompts

**Current:** No MCP resources or prompts are exposed.

**Recommendations (future):**

- **Resource:** Expose a read-only "workflow" resource (e.g. `tapps://workflow`) that returns the same recommended workflow text. Clients that support MCP resources could show it in a sidebar or context.
- **Prompt:** If the SDK supports `@mcp.prompt()`, register a prompt template like "TappsMCP workflow" so users can insert the workflow into the conversation in one click.

---

## Summary of implemented changes

| Area              | Change |
|-------------------|--------|
| Tool docstrings   | First line of each tool now leads with "When to use" / "Call when". |
| tapps_server_info | Response includes `data.recommended_workflow` with short workflow text. |
| tapps_checklist   | Response includes `missing_required_hints`, `missing_recommended_hints`, `missing_optional_hints` with `{ "tool", "reason" }`. |
| AGENTS.md         | New file: what TappsMCP is, when to use each tool, recommended workflow. |
| README            | New "For AI assistants" subsection with workflow and link to AGENTS.md. |

These are backward-compatible: no tool renames, no removal of existing response fields.
