# 2026 Deep Research: LLM Prompt & Context Best Practices

**Status:** Research summary  
**Date:** 2026-03-11  
**Scope:** Best practices, token length, prompt engineering, and context length for **LLM-facing artifacts** (prompts, instructions, context docs). Not traditional human-oriented epics/stories; these guidelines apply to content consumed by models.

**Sources:** 2025–2026 publications, Anthropic/OpenAI/Google docs, MCP protocol guidance, prompt engineering guides, and context-window research.

---

## 1. Context windows and token limits (2026)

### 1.1 Current model context sizes

| Provider | Model | Context window (tokens) | Notes |
|----------|--------|---------------------------|--------|
| **Anthropic** | Claude Sonnet 4 / 4.5 | 200K–1M | 200K typical for reliability; 1M on select tiers |
| **OpenAI** | GPT-4o, GPT-4 Turbo | 128K | Ecosystem integration focus |
| **Google** | Gemini 1.5 Pro | 2M | Largest raw capacity; full manuals/repos |
| **Google** | Gemini 1.5 Flash | 1M | High capacity, lower cost |
| **Google** | Gemini 2.5 (2026) | 1M+ | Available in 2026 |

**Takeaway:** Raw context is large (128K–2M), but **usable** context is much smaller due to attention degradation, cost, and “lost in the middle.” Design for **effective** use, not maximum window.

### 1.2 Tokens vs words (rule of thumb)

- **English:** ~1.3–1.5 tokens per word (~4 characters per token).
- **150 words** ≈ ~200 tokens; **300 words** ≈ ~400 tokens; **1,000 words** ≈ ~1,300 tokens.

---

## 2. Optimal prompt and instruction length

### 2.1 Sweet spot for reasoning and instructions

- **Target:** **150–300 words** (~200–400 tokens) for core task instructions; **~1,400–1,800 tokens** reported as a practical upper bound for single-shot reasoning tasks before quality drops.
- **Degradation:** Reasoning and instruction-following degrade meaningfully beyond **~3,000 tokens** of prompt; accuracy can drop from ~95% (short) to ~80% at 2K tokens; hallucinations rise (e.g. +34% beyond 2,500 tokens).
- **Principle:** “Clearer specs, not longer prompts.” Start minimal; add only what fixes specific gaps.

### 2.2 Lost in the middle

- **Effect:** Models weight **beginning and end** of context heavily; **middle** (roughly 40–60% of context) gets much less attention (e.g. ~12–18% vs ~95–100% at start/end). Accuracy for info in the middle can be **30%+ worse**.
- **Causes:** Causal attention (earlier tokens get more weight); training that favors recent vs uniform recall.
- **Implications for LLM-facing artifacts:**
  - Put **critical instructions and constraints at the start** (role, task, success criteria, rules).
  - Put **output format, “stop and tell me,” and alignment gate at the end**.
  - **Avoid** putting must-follow rules or success criteria only in the middle.
  - For long context: use **hierarchical summaries at the top**, **query-anchored placement**, or **repetition** of key rules; consider **chunking** with retrieval instead of one giant blob.

### 2.3 Attention and cost

- Attention over context scales with **O(n²)** in transformers; every extra token makes it harder to focus on what matters and can yield vaguer outputs.
- **Token budgeting:** Reserve space for **model output**; treat context as a finite budget. Put only what the model needs to fulfill the task.

---

## 3. Prompt engineering best practices (2026)

### 3.1 Shift: “Prompt engineering” → “Context engineering”

- Focus is on **designing cognitive architecture**: what goes in system vs user, what’s cached, what’s retrieved, and in what order—not only wording of a single prompt.

### 3.2 Four essential components (for any LLM-facing instruction set)

1. **Role** — Who the model should act as (e.g. “You are a code quality assistant.”).
2. **Task** — Exactly what to do (“I want to [TASK] so that [SUCCESS CRITERIA].”).
3. **Constraints** — Boundaries, scope, “don’t do X,” standards.
4. **Output format** — Structure, length, tone (JSON, markdown, sections).

### 3.3 Five principles

1. **Iterate with feedback and tests** — Treat prompts as a loop; validate with real runs.
2. **Give permission to think** — Use “think step by step” (or equivalent) for reasoning-heavy tasks.
3. **Constrain format and style** — Pin output shape for reliable parsing (JSON, markdown, tables).
4. **Show, don’t tell** — **2–3 concrete examples** beat long prose descriptions.
5. **Be explicit** — State edge cases and success criteria; avoid ambiguity.

### 3.4 Checklist for instruction design

- Define **success criteria** upfront (what “done” looks like).
- Create an **output contract**: format, length, tone, required sections.
- **Separate instructions from inputs** (e.g. 4-block: Instructions | Inputs | Constraints | Output format).
- Prefer **examples over adjectives** for consistent behavior.
- Add a **lightweight self-check** (e.g. “Before responding, verify: …”) to catch failures.

### 3.5 Model-specific notes

- **GPT-style:** Often benefits from **detailed instructions** and **numeric constraints** (“exactly 3 bullets”).
- **Claude:** Often benefits from **concise, focused** prompts with **context/motivation**; avoid stuffing the middle with critical rules.
- **Structured formatting:** Section markers (###), layered structure, and explicit format specs improve reliability across models.

---

## 4. System vs user prompt and token budget

### 4.1 Roles

- **System prompt:** “Constitution”—role, boundaries, safety, formatting rules, **persistent** constraints for the session. Sent once (or with caching).
- **User prompt:** “The bill”—specific request for this turn. Varies per interaction.

### 4.2 What to put where

| System (stable, reusable) | User (per turn) |
|----------------------------|------------------|
| Identity / role | Task-specific request |
| Priority rules | This turn’s inputs (files, query) |
| Safety / compliance constraints | One-off clarifications |
| **Strict output contract** (e.g. JSON schema) | |
| Rules that apply to every task | |

### 4.3 Cost and caching

- **Output tokens** cost **3–6×** input tokens (generation is sequential).
- **Prompt caching (e.g. Anthropic):** Cached prefix reads at **~10%** of input price (~90% discount); first write at **~125%**. After ~2 requests with same prefix, caching pays off. Cache read tokens may not count toward rate limits (model-dependent).
- **Implication:** Put **stable, reusable** instruction blocks (role, rules, format) in **system** and use caching; keep **variable** content in user messages.

---

## 5. MCP and agent-specific guidance (2026)

### 5.1 MCP design and token efficiency

- **Tools, resources, prompts** are first-class; avoid pasting huge tool/API dumps into prompts—**declare intent, let schemas carry the weight.** Tool discovery is dynamic.
- **Token efficiency:** Exposing thousands of tools can consume **1M+ tokens** just for the tool list. Prefer **fewer, broader tools** (e.g. “Code Mode”–style APIs in ~1K tokens).
- **Prompts in MCP:** Pre-defined prompt **templates** that agents invoke by name. Keep template content **lean** and aligned with the sweet spot (e.g. 150–300 words for core instructions).

### 5.2 Implications for “prompt” artifacts (for LLMs)

- **Prompt artifacts** (e.g. .md consumed as LLM context) should be **structured and short**: task + success + constraints + format at top and end; avoid long narrative in the middle.
- **Context files** (“read these first”) should be **listed explicitly** with one-line descriptions; actual content can be retrieved on demand or injected in order (critical first/last).
- **Rules and “stop and tell me”** belong in system or in a **short, cached** block, not buried in the middle of a long doc.

---

## 6. Long context: chunking and retrieval

### 6.1 When context exceeds effective length

- **Chunk sizes (guidance):**  
  - Q&A / retrieval: **200–600 tokens** per chunk.  
  - Summarization / synthesis: **800–2,048 tokens** to preserve flow.  
  - Embeddings: **256–1,024 tokens** as a common range.
- **Overlap:** **10–30%** (e.g. 50–200 tokens for 500-token chunks) to preserve continuity across boundaries.
- **Principle:** One **coherent idea per chunk**; respect semantic boundaries (e.g. recursive splitting on paragraphs/sentences) over naive fixed-size splits.

### 6.2 Placement in context

- Put **most relevant** chunks near **start or end** of the assembled context to avoid “lost in the middle.”
- Use **hierarchical summaries** at the top when feeding long docs; link to detail or retrieve on demand.

---

## 7. Recommendations for LLM-facing artifacts (epic/story/prompt as context)

These apply to **any** artifact (epic, story, or “prompt” doc) that is **consumed by an LLM** as context—not to human-only agile docs.

### 7.1 Structure

- **Lead with:** Role/task + success criteria + key constraints (first ~150–300 words / ~200–400 tokens).
- **End with:** Output format, “stop and tell me” rule, alignment gate.
- **Middle:** Optional detail, examples, references—but **do not** put critical must-follow rules only in the middle.
- Use **clear section headings** (###) and, where possible, **bullet lists and numbered steps** instead of long paragraphs.

### 7.2 Length

- **Per artifact:** Aim for **≤ ~1,500 tokens** for the core instruction set; if longer, provide a **short summary at top** and treat the rest as reference.
- **Total context:** Budget system + user + tools; leave room for model output. Prefer **multiple small, focused artifacts** over one giant doc.

### 7.3 Content

- **Explicit success criteria** (“done when …”).
- **Output contract** (format, length, required keys/sections).
- **2–3 examples** of desired output or behavior where it helps.
- **Constraints** as “Always” / “Never” or short bullets.
- **Context files** as a short list with one-line descriptions; load order matters (critical first/last).

### 7.4 Tool and data usage (TappsMCP / DocsMCP)

- **Project profile and experts:** Use for **rules and constraints**; inject as a **concise** block (summarized if needed), not raw dumps.
- **Generated epic/story/prompt .md:** Keep sections **short**; consider a **compact “LLM view”** (e.g. goal + criteria + steps + rules in &lt; 1.5K tokens) in addition to a full human-readable version.
- **MCP prompts:** Register **short** templates; put detailed guidance in **resources** or **retrieved context** so the main prompt stays under the sweet spot.

### 7.5 Compact LLM view (Epic 75.4)

DocsMCP’s **prompt** generator supports an optional **compact LLM view** for token-efficient context. Use it when feeding an epic, story, or prompt artifact into the model and you need to stay within ~1.5K tokens. Format: identity (title), purpose/goal (single paragraph), success criteria (bulleted), steps (bulleted), rules (bulleted), don’t (bulleted). No narrative. Call `docs_generate_prompt(..., compact_llm_view=True)` to emit only the compact view; the full .md remains the source of truth for humans. Token budget is documented and tested (sample under 2K tokens).

---

## 8. Summary table: numbers to remember

| Topic | 2026 guidance |
|-------|----------------|
| **Optimal instruction length** | 150–300 words (~200–400 tokens) for core; &lt; ~1.8K tokens before noticeable degradation |
| **Critical content placement** | Start and end; avoid middle for must-follow rules |
| **Context window (effective)** | Design for much less than 128K–2M; attention and cost matter |
| **System vs user** | Stable rules/format in system (cache); variable task in user |
| **Output contract** | Explicit format, length, structure; examples over prose |
| **MCP** | Fewer, broader tools; short prompt templates; schemas carry weight |
| **Chunking (when needed)** | 200–600 (retrieval), 800–2K (synthesis); 10–30% overlap; semantic boundaries |

---

## 9. References (conceptual; see web search results for URLs)

- Anthropic: Context windows, prompt caching, Claude API docs.
- OpenAI: Prompt engineering, GPT context.
- Google: Gemini long context, chunking/summarization.
- “Lost in the Middle” (Stanford/UC Berkeley; MIT 2025 follow-up).
- MCP: Model Context Protocol docs, MCP prompting playbook, token efficiency.
- Prompt engineering guides: AI Engineer Lab, Prompt Builder, Zylos Research, Thomas Wiegold (2026).
- Token budgeting: MyEngineeringPath, Medium (tokenization, production patterns).
- Chunking: ByteTools, synthmetric, RAG strategies 2026.
