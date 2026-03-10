# TappMCP Experts vs Agency-Agents Personas — What to Leverage (Summary)

**Context:** Agency-agents are ~80 full “personas” (identity, mission, critical rules, deliverables, workflow, success metrics). TappMCP experts are 17 domain experts backed by RAG knowledge + an optional one-line **persona** (only Security and Software Architecture use it today).

---

## How TappMCP Experts Work Today

| Aspect | TappMCP | Agency-agents |
|--------|---------|----------------|
| **Identity** | `expert_name` + short `description`; optional `persona` (1 line, 2 experts) | Full “Identity & Memory” (role, personality, memory) |
| **Rules / stance** | None | “Critical Rules You Must Follow” |
| **Content** | RAG over Markdown knowledge dirs (patterns, checklists, code) | Same + “Technical Deliverables” (templates, code) |
| **Process** | None | “Workflow Process” (step-by-step) |
| **Outcomes** | None | “Success Metrics” (quantitative) |
| **Voice** | Persona prepended as italic line before answer | “Communication Style” + example phrases |

Consult flow: RAG retrieval → chunks → optional `*{persona}*\n\n` + “Based on domain knowledge…” → answer. No explicit “default stance,” “critical rules,” or “success metrics” in the prompt.

---

## What TappMCP Can Leverage or Learn

### 1. **Richer persona (low effort)**

- **Today:** Only Security and Software Architecture have a non-empty persona; it’s one sentence, prepended in italics.
- **Leverage:** Give every built-in expert a 1–3 sentence **persona** (role + stance). Examples:
  - Testing: “Senior test architect; default to recommending tests and coverage; never approve untested critical paths.”
  - Accessibility: “Accessibility specialist; WCAG 2.1 AA as baseline; assume diverse abilities and assistive tech.”
- **Benefit:** More consistent, expert-like voice without changing RAG or tool contract.

### 2. **Critical rules / default stance (medium effort)**

- **Agency:** e.g. Reality Checker “default to NEEDS WORK,” “require overwhelming evidence.”
- **Leverage:** Add an optional **critical_rules** or **default_stance** (e.g. a short list or paragraph) to `ExpertConfig` (or a per-expert intro file). Engine prepends it with the persona so the model “must follow” those rules when answering.
- **Benefit:** Domain-appropriate caution (e.g. Security: “assume breach”; Testing: “prefer explicit tests over implicit behavior”).

### 3. **Success metrics in knowledge (low effort)**

- **Agency:** “Page load &lt;3s,” “Lighthouse &gt;90,” “zero console errors.”
- **Leverage:** Add a **“Success metrics”** (or “Definition of done”) section to key knowledge files per domain. RAG will then retrieve “what good looks like” and experts can cite thresholds (coverage, latency, WCAG level).
- **Benefit:** Answers become more actionable and measurable.

### 4. **Deliverable templates (low–medium effort)**

- **Agency:** Concrete report/checklist templates (e.g. Reality Checker report, Frontend deliverable template).
- **Leverage:** Add template snippets to knowledge (e.g. “Security review report template,” “Testing checklist template”) or a dedicated `_templates.md` per domain. Consult answers can reference or paste them.
- **Benefit:** Users get consistent, copy-pasteable outputs (reports, checklists).

### 5. **Communication style / example phrases (optional)**

- **Agency:** “Reference evidence,” “Be specific,” “Default to finding issues.”
- **Leverage:** Optional **communication_style** or **example_phrases** in config or in a short “voice” section in the expert’s intro file; engine could append “Respond in this style: …” when assembling the prompt.
- **Benefit:** Tonality and phrasing more aligned with the domain (e.g. Testing: “Recommend a test for…” vs Security: “Assume an attacker…”).

### 6. **When-to-use / domain hints (already strong)**

- **Agency:** “When to Use” per agent.
- **TappMCP:** AGENTS.md “Domain hints for tapps_consult_expert” already maps context → domain. Optional: add a one-line “When to use this expert” to each expert’s `description` or to the first knowledge file so it appears in RAG when relevant.

### 7. **Workflow hints (low effort)**

- **Agency:** “Step 1: Setup → Step 2: Development → Step 3: Optimization…”
- **Leverage:** Add “Typical steps” or “Recommended process” sections to knowledge (e.g. Testing: “1. Identify scope 2. Choose strategy 3. Write tests 4. Run and iterate”). No schema change; RAG retrieves and the expert can suggest a process.
- **Benefit:** Answers that suggest a sequence, not only isolated facts.

---

## Summary Table

| Leverage | Effort | Change |
|----------|--------|--------|
| Richer persona for all 17 experts | Low | Expand `persona` in registry (and optionally in business config). |
| Critical rules / default stance | Medium | New optional field + engine prepend, or intro file per expert. |
| Success metrics in knowledge | Low | Add sections to existing .md files. |
| Deliverable templates | Low–medium | New or existing knowledge files with templates. |
| Communication style | Low | Optional field or “voice” section in knowledge. |
| When-to-use (domain hints) | Low | Already in AGENTS.md; optional copy in expert description/intro. |
| Workflow hints | Low | “Typical steps” sections in knowledge. |

---

## What Not to Copy

- **Full agency “personality” as prompt bloat:** TappMCP stays deterministic and RAG-driven; we don’t need long narrative identities. Short persona + optional rules + better knowledge structure is enough.
- **Separate “agent” files per tool:** TappMCP experts are invoked via one MCP tool (`tapps_consult_expert`); no need for Cursor/Aider-specific agent files. The improvement is in expert *content* and *config*, not distribution.
- **Marketing/product/support personas:** TappMCP’s 17 domains are technical (security, testing, API, DB, etc.). Agency’s non-technical specialists are out of scope unless we add business experts later.

---

## Bottom Line

TappMCP experts can **borrow structure and intent** from agency-agents without becoming full personas:

1. **Persona:** Give every expert a short, stance-aware persona (and use it in the answer preamble).
2. **Stance/rules:** Optional “critical rules” or “default stance” so answers are domain-appropriate (e.g. skeptical for security, evidence-based for testing).
3. **Knowledge:** Add success metrics, deliverable templates, and workflow hints to existing knowledge so RAG retrieves them and answers are more actionable and process-oriented.

That keeps TappMCP’s deterministic, tool-driven model while making expert responses more consistent, cautious, and useful.
