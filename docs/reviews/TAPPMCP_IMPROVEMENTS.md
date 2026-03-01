# TappsMCP Improvements - Informed by AI OS Concepts & 2026 Claude Code Platform

> **Companion to:** [AIOS_REVIEW.md](AIOS_REVIEW.md), [AIOS_RECOMMENDATIONS.md](AIOS_RECOMMENDATIONS.md)
> **Date:** 2026-02-28
> **Scope:** Concrete, code-level improvements to TappsMCP based on cross-referencing AI OS architectural patterns against the TappsMCP codebase and 2026 Claude Code platform documentation
> **Validation:** All platform features validated against official 2026 Claude Code docs (skills, hooks, subagents, plugins, memory, MCP, permissions)

---

## Table of Contents

1. [Methodology](#1-methodology)
2. [Memory Subsystem](#2-memory-subsystem)
3. [Expert System](#3-expert-system)
4. [Skills Generation](#4-skills-generation)
5. [Hooks Generation](#5-hooks-generation)
6. [Subagent Generation](#6-subagent-generation)
7. [Pipeline & Onboarding](#7-pipeline--onboarding)
8. [Knowledge & Documentation Backend](#8-knowledge--documentation-backend)
9. [Scoring & Quality Gates](#9-scoring--quality-gates)
10. [Platform Distribution](#10-platform-distribution)
11. [Summary Matrix](#11-summary-matrix)

---

## 1. Methodology

This document was produced by:

1. **Deep code review** of all TappsMCP subsystems (memory: 12 files, experts: 18 files, pipeline: 17 files, scoring/security/knowledge: 20 files)
2. **Cross-referencing** with AI OS concepts from [AIOS_REVIEW.md](AIOS_REVIEW.md) -- a 12,700-line Claude Code workspace template with 17 skills, 3-tier memory, hybrid search, and progressive onboarding
3. **Validating** every recommendation against the 2026 Claude Code official documentation covering all 17 hook events, 4 hook types, skill frontmatter fields, subagent configuration, plugin system, memory architecture, and MCP integration

Each improvement is rated:

| Priority | Meaning |
|----------|---------|
| **P0** | Critical gap -- TappsMCP generates incorrect or outdated platform artifacts |
| **P1** | High impact -- significant capability or quality improvement |
| **P2** | Medium impact -- measurable improvement for consuming projects |
| **P3** | Nice-to-have -- polish and future-proofing |

---

## 2. Memory Subsystem

### Current State

TappsMCP's memory subsystem (`memory/`) provides persistent cross-session knowledge sharing via SQLite with WAL mode, FTS5 full-text search, and a write-through in-memory cache. 12 source files implement models, persistence, store, decay, reinforcement, contradictions, GC, retrieval, injection, seeding, and I/O.

**Key architecture:**
- `persistence.py`: SQLite + WAL + FTS5 + JSONL audit trail, schema versioning
- `store.py`: In-memory dict cache, write-through, 500-entry hard limit, thread lock
- `retrieval.py`: Composite scoring (0.40 relevance + 0.30 confidence + 0.15 recency + 0.15 frequency)
- `decay.py`: Exponential decay with tier-specific half-lives (architectural: 180d, pattern: 60d, context: 14d)

### 2.1 Upgrade Retrieval from Word Overlap to BM25

**Priority: P1** | **Files:** `memory/retrieval.py`

**AI OS concept:** AI OS's `smart_search.py` implements hybrid BM25 + vector + temporal decay + MMR diversity re-ranking (Jaccard-based, lambda=0.7). TappsMCP's retrieval uses simple word overlap (`_word_overlap_score` at line 202 of `retrieval.py`) which splits on whitespace and counts set intersection. This produces poor recall for morphological variants (e.g., "testing" won't match "test"), lacks IDF weighting, and treats all words as equally important.

**Current code (`retrieval.py:202-210`):**
```python
@staticmethod
def _word_overlap_score(query: str, entry: MemoryEntry) -> float:
    query_words = set(query.lower().split())
    entry_text = f"{entry.key} {entry.value} {' '.join(entry.tags)}".lower()
    entry_words = set(entry_text.split())
    overlap = len(query_words & entry_words)
    return overlap / len(query_words)
```

**Improvement:**
- Implement proper BM25 scoring (k1=1.2, b=0.75) using document frequency statistics from the memory store
- Add basic stemming via suffix stripping (no external dependency needed -- Porter-like suffix rules are ~50 lines)
- Add stop word filtering for common English words ("the", "is", "a", etc.)
- Consider MMR diversity re-ranking from AI OS when multiple memories cover similar topics

**2026 platform validation:** Claude Code's native auto memory uses `MEMORY.md` with first-200-lines loading. TappsMCP's `tapps_memory` serves a different purpose (structured cross-agent knowledge), so upgrading its retrieval quality is valuable regardless of native memory availability.

**Estimated effort:** 1-2 days. BM25 is well-documented and needs only document-level statistics (already available from `store.list_all()`).

---

### 2.2 Expose Reinforcement via MCP Tool

**Priority: P2** | **Files:** `server_memory_tools.py`, `memory/reinforcement.py`

**AI OS concept:** AI OS's memory system automatically captures facts from conversation transcripts via its `auto_capture.py` Stop hook. Each captured memory gets reinforced when accessed. TappsMCP has the reinforcement logic (`memory/reinforcement.py` with `boost_confidence()`) but no MCP tool action exposes it. The `tapps_memory` tool supports `save`, `get`, `list`, `delete`, `search` -- but no `reinforce` or `access` action.

**Improvement:**
- Add a `reinforce` action to `tapps_memory` that calls `boost_confidence()` on the specified memory key
- This lets consuming agents explicitly reinforce memories they find useful, improving future retrieval ranking
- The reinforcement multiplier (1.05x default, configurable) is already implemented; it just needs a tool surface

**Estimated effort:** 2-4 hours. The logic exists; only the MCP tool dispatch needs a new branch.

---

### 2.3 Add Auto-Capture Hook for Consuming Projects

**Priority: P2** | **Files:** `pipeline/platform_hook_templates.py`

**AI OS concept:** AI OS's `auto_capture.py` runs as a Stop hook and parses the Claude Code conversation transcript (JSONL at `~/.claude/projects/{project}/{sessionId}.jsonl`) to extract facts and persist them. TappsMCP generates Stop hooks (`tapps-stop.sh`) that only remind about `tapps_validate_changed` -- they do not capture session learnings.

**Improvement:**
- Generate an optional Stop hook (`tapps-memory-capture.sh`) that:
  1. Reads the session transcript JSONL
  2. Extracts tool call patterns (which TappsMCP tools were used, scores achieved)
  3. Calls `tapps_memory save` with key patterns like `session-quality-summary` and `common-issues`
  4. This creates a feedback loop: past session quality data informs future sessions

**2026 platform validation:** The Stop hook event fires when Claude finishes responding. It can run async (non-blocking). The transcript path is available via `$CLAUDE_PROJECT_DIR/.claude/projects/`.

**Estimated effort:** 1-2 days. Requires a new hook script template and JSON parsing logic.

---

### 2.4 Automated GC Scheduling

**Priority: P3** | **Files:** `memory/gc.py`, `pipeline/platform_hook_templates.py`

**AI OS concept:** AI OS's daily log rotation happens via the Stop hook. TappsMCP's GC (`memory/gc.py`) implements `gc_collect()` with stale pruning and capacity eviction, but requires external orchestration -- nothing triggers it automatically.

**Improvement:**
- Generate a SessionStart hook that runs `tapps_memory` GC on first session start of the day (use a marker file to avoid running repeatedly)
- Alternative: run GC automatically inside `tapps_session_start` when memory count exceeds 80% of `max_memories` (400/500)
- The latter is simpler and doesn't require a new hook

**Estimated effort:** 2-4 hours for the session_start integration approach.

---

### 2.5 Complementary Native Memory Strategy

**Priority: P2** | **Files:** `prompts/agents_template*.md`, `pipeline/agents_md.py`

**AI OS concept (Recommendation 12):** AI OS was advised to adopt Claude Code's native auto memory for Tiers 1-2, reserving custom mem0 for Tier 3 (cross-platform, hybrid search). TappsMCP's `tapps_memory` and Claude Code's auto memory serve complementary purposes, but generated AGENTS.md doesn't explain the distinction.

**2026 platform validation:** Claude Code auto memory lives at `~/.claude/projects/<project>/memory/MEMORY.md` (first 200 lines loaded every session). TappsMCP's memory lives at `{project_root}/.tapps-mcp/memory/`. They don't conflict but could confuse users.

**Improvement:**
- Update generated AGENTS.md to explain the two memory systems:
  - **Claude Code auto memory**: Session learnings, user preferences, debugging insights (auto-managed)
  - **TappsMCP memory**: Quality patterns, architecture decisions, expert findings (structured, cross-agent)
- Add guidance to generated rules: "Use MEMORY.md for workflow preferences. Use `tapps_memory save` for quality patterns and architecture decisions that should persist across agent boundaries."

**Estimated effort:** 2-4 hours. Documentation update to templates.

---

## 3. Expert System

### Current State

TappsMCP's expert system (`experts/`) provides 17 domain experts with 140 curated markdown knowledge files. The `engine.py` orchestrates RAG lookup, domain detection, and confidence scoring. An `adaptive_domain_detector.py` exists but is NOT wired into the main consultation flow.

### 3.1 Integrate Adaptive Domain Detector

**Priority: P1** | **Files:** `experts/engine.py`, `experts/adaptive_domain_detector.py`

**AI OS concept:** AI OS's skills use model routing to optimize cost/quality tradeoffs. Similarly, adaptive routing of questions to the best expert domain improves answer quality. TappsMCP built the `AdaptiveDomainDetector` (learning from feedback which domains produce good results for which query patterns) but `engine.py:180-193` uses the static `DomainDetector` exclusively:

```python
def _resolve_domain(question: str, domain: str | None) -> _ResolvedDomain:
    detected: list[DomainMapping] = []
    if domain:
        resolved_domain = domain
    else:
        mappings = DomainDetector.detect_from_question(question)  # <-- static only
        resolved_domain = mappings[0].domain if mappings else "software-architecture"
        detected = mappings[:3]
```

**Improvement:**
- When `adaptive.enabled` is True in settings, use `AdaptiveDomainDetector` as the primary detector in `_resolve_domain()`, falling back to the static detector when insufficient training data exists
- The adaptive detector already has the interface: `detect(question)` returns ranked domains with scores
- This creates a feedback loop: `tapps_feedback` outcomes train the adaptive detector, which improves future domain routing

**Estimated effort:** 4-8 hours. The code exists; it needs wiring and a settings check.

---

### 3.2 Add Query Expansion / Synonym Matching

**Priority: P2** | **Files:** `experts/domain_detector.py`, `experts/rag.py`

**AI OS concept:** AI OS's `smart_search.py` uses both vector similarity and BM25 keyword matching to handle lexical mismatch. TappsMCP's `DomainDetector` uses static keyword lists with regex word boundaries (`\b`). If a user asks about "authentication" but the keyword is "auth", it won't match.

**Current pattern (`domain_detector.py`):**
```python
_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "security": ["security", "auth", "vulnerability", "owasp", ...],
    ...
}
```

**Improvement:**
- Add a synonym/expansion map: `{"authentication": "auth", "authorization": "auth", "testing": "test", "optimizing": "optimization", ...}`
- Expand the query before keyword matching to improve domain detection recall
- This is distinct from stemming (improvement 2.1) -- these are domain-specific semantic equivalences
- Keep it simple: a hardcoded dict of ~50 common synonyms, not an NLP pipeline

**Estimated effort:** 4-8 hours. Straightforward dict lookup + expanded matching.

---

### 3.3 Knowledge Freshness Checking During Queries

**Priority: P3** | **Files:** `experts/engine.py`, `experts/knowledge_freshness.py`

**AI OS concept:** AI OS's daily log rotation ensures recent context is available. TappsMCP has `knowledge_freshness.py` that can assess whether knowledge files are outdated, but it's not invoked during expert consultations. Stale knowledge produces stale answers.

**Improvement:**
- During `_retrieve_knowledge()`, check the age of the top-ranked knowledge chunks via `knowledge_freshness.py`
- If the best chunks are over 1 year old, add a caveat to the consultation result: "Note: Some retrieved knowledge may be outdated. Consider verifying with tapps_lookup_docs."
- This is a lightweight check (file modification time) with high value for consumers

**Estimated effort:** 2-4 hours.

---

## 4. Skills Generation

### Current State

TappsMCP generates 7 skills via `pipeline/platform_skills.py`: `tapps-score`, `tapps-gate`, `tapps-validate`, `tapps-review-pipeline`, `tapps-research`, `tapps-memory`, `tapps-security`. Each is a SKILL.md with frontmatter and step-by-step instructions.

### 4.1 Add Missing Frontmatter Fields

**Priority: P0** | **Files:** `pipeline/platform_skills.py`

**2026 platform validation:** The official 2026 skill frontmatter supports these fields that TappsMCP-generated skills do not use:

| Field | Status in TappsMCP | Should Use? |
|-------|-------------------|-------------|
| `name` | Used | Yes (correct) |
| `description` | Used | Yes (correct) |
| `tools` | Used (as `tools:`) | **INCORRECT** -- should be `allowed-tools` per the 2026 spec |
| `model` | NOT used | **Yes** -- research/review skills should specify `model: haiku` for cost |
| `context` | NOT used | **Yes** -- `tapps-research` should use `context: fork` to isolate |
| `agent` | NOT used | Optional -- specify agent type when using `context: fork` |
| `disable-model-invocation` | NOT used | **Yes** -- `tapps-validate` and `tapps-gate` should be user-triggered only |
| `user-invocable` | NOT used | Optional |
| `argument-hint` | NOT used | **Yes** -- improve autocomplete UX |
| `hooks` | NOT used | Optional for skill-scoped hooks |

**AI OS concept:** AI OS uses `model:` routing on 6 of 17 skills to optimize cost. Skills that do only read-only analysis use `model: haiku`, while creative/complex skills use `model: sonnet`. AI OS also uses `context: fork` for isolation and `allowed-tools` for restriction.

**Current (`platform_skills.py:18-33`):**
```yaml
---
name: tapps-score
description: Score a Python file across 7 quality categories...
tools: mcp__tapps-mcp__tapps_score_file, mcp__tapps-mcp__tapps_quick_check
---
```

**Corrected:**
```yaml
---
name: tapps-score
description: Score a Python file across 7 quality categories...
argument-hint: "[file-path]"
allowed-tools: mcp__tapps-mcp__tapps_score_file, mcp__tapps-mcp__tapps_quick_check
---
```

**Specific recommendations per skill:**
- `tapps-score`: Add `argument-hint: "[file-path]"`, rename `tools` to `allowed-tools`
- `tapps-gate`: Add `disable-model-invocation: true` (workflow skill, user-triggered), add `argument-hint: "[file-path]"`
- `tapps-validate`: Add `disable-model-invocation: true`, rename `tools` to `allowed-tools`
- `tapps-review-pipeline`: Add `context: fork` (heavy parallel operation should be isolated), add `agent: general-purpose`
- `tapps-research`: Add `context: fork`, `model: haiku` (read-only research), add `argument-hint: "[question]"`
- `tapps-memory`: Add `argument-hint: "[action] [key]"`
- `tapps-security`: Add `argument-hint: "[file-path]"`

**Estimated effort:** 4-8 hours. Template string updates across all 7 skills.

---

### 4.2 Add Progressive Skill Tiers (Starter vs Power)

**Priority: P2** | **Files:** `pipeline/platform_skills.py`, `pipeline/init.py`

**AI OS concept:** AI OS splits skills into 8 "starter" skills (zero API keys) and 9 "power" skills (require external APIs). This progressive disclosure reduces cognitive overhead for new users. TappsMCP generates all 7 skills unconditionally during `tapps_init`.

**Improvement:**
- Split skills into two tiers:
  - **Core** (always generated): `tapps-score`, `tapps-gate`, `tapps-validate`, `tapps-security`
  - **Advanced** (generated when `engagement_level >= medium`): `tapps-review-pipeline`, `tapps-research`, `tapps-memory`
- Add a parameter to `tapps_init`: `skills_tier: "core" | "full"` (default: "full")
- For `skills_tier: "core"`, only generate the 4 essential quality skills, reducing skill description context overhead

**2026 platform validation:** Skills consume context budget (2% of context window, ~16K chars fallback). Fewer skills = more context for actual work.

**Estimated effort:** 4-8 hours. Conditional generation in `generate_skills()`.

---

## 5. Hooks Generation

### Current State

TappsMCP generates 7 Claude Code hooks via `pipeline/platform_hook_templates.py`:
- `tapps-session-start.sh` (SessionStart)
- `tapps-session-compact.sh` (SessionStart with `compact` matcher)
- `tapps-post-edit.sh` (PostToolUse for Edit/Write)
- `tapps-stop.sh` (Stop)
- `tapps-task-completed.sh` (TaskCompleted)
- `tapps-pre-compact.sh` (PreCompact)
- `tapps-subagent-start.sh` (SubagentStart)

All are `type: "command"` hooks.

### 5.1 Add Prompt-Type Hook for Quality Judgment

**Priority: P1** | **Files:** `pipeline/platform_hook_templates.py`, `pipeline/platform_generators.py`

**AI OS concept (Recommendation 1):** The highest-impact recommendation for AI OS was replacing its substring-matching guardrail with a `type: "prompt"` hook. Prompt hooks send input to a Haiku model for judgment-based evaluation. TappsMCP can generate a prompt-type hook for quality judgment.

**2026 platform validation:** Prompt hooks are confirmed in 2026 docs:
```json
{
  "type": "prompt",
  "prompt": "Based on this tool output: $ARGUMENTS\n\nDid the agent properly handle quality issues? Answer yes or no.",
  "model": "haiku",
  "timeout": 30
}
```
The hook returns yes/no. If it returns "no" and the event supports blocking (exit 2), it can block.

**Improvement:**
- Generate an optional PostToolUse prompt hook for Write/Edit tools that asks Haiku: "A Python file was just modified. Based on the tool output, does it appear that quality checks (linting, type checking) should be run? Answer yes if any Python code was changed, no otherwise."
- If Haiku answers "yes", the hook stderr reminds Claude to run `tapps_quick_check`
- This is more intelligent than the current pattern-matching approach in `tapps-post-edit.sh` which only checks if the file path ends with `.py`
- Make this opt-in via a `prompt_hooks: true` parameter in `tapps_init`

**Estimated effort:** 4-8 hours. New hook template + settings.json config generation.

---

### 5.2 Expand Hook Event Coverage

**Priority: P1** | **Files:** `pipeline/platform_hook_templates.py`

**AI OS concept (Recommendation 4):** AI OS was advised to expand from 3 to 8 hook events. TappsMCP already uses 7 events (better than AI OS's 3). However, TappsMCP doesn't generate hooks for these valuable events:

| Missing Event | Value for Consuming Projects |
|--------------|------------------------------|
| `UserPromptSubmit` | Could validate that task descriptions include enough context for quality-aware development |
| `PostToolUseFailure` | Could log failed MCP tool calls for debugging TappsMCP connectivity |
| `SubagentStop` | Could trigger `tapps_quick_check` on files modified by a subagent before accepting results |
| `SessionEnd` | Could trigger final `tapps_validate_changed` + save quality summary to memory |

**Improvement:**
- Add `tapps-subagent-stop.sh` (SubagentStop): When a subagent finishes, check if any Python files were modified in its worktree and remind about quality validation
- Add `tapps-session-end.sh` (SessionEnd): Final quality reminder + optional memory capture
- Add `tapps-post-failure.sh` (PostToolUseFailure): Log TappsMCP tool failures for diagnostics

**Estimated effort:** 4-8 hours. Three new hook script templates.

---

### 5.3 Generate Blocking Hooks for High Engagement

**Priority: P2** | **Files:** `pipeline/platform_hook_templates.py`

**AI OS concept:** AI OS's `guardrail_check.py` uses exit code 2 to block dangerous commands. TappsMCP's generated hooks all exit 0 (non-blocking), even at `engagement_level: high`. This is a missed opportunity.

**2026 platform validation:** Exit code 2 = blocking error for events that support it. TaskCompleted and Stop both support blocking.

**Improvement:**
- At `engagement_level: high`, generate blocking variants:
  - `tapps-task-completed.sh`: Exit 2 if `tapps_validate_changed` hasn't been called (check via a marker file the validate tool creates)
  - `tapps-stop.sh`: Exit 2 on first Stop if no quality tools were called during the session
- At `engagement_level: medium` (default): Keep non-blocking (current behavior)
- At `engagement_level: low`: Skip hooks entirely or generate minimal ones

**Estimated effort:** 8-16 hours. Requires engagement-level conditional logic in hook generation + marker file mechanism.

---

## 6. Subagent Generation

### Current State

TappsMCP generates 4 subagents via `pipeline/platform_subagents.py`: `tapps-researcher`, `tapps-reviewer`, `tapps-validator`, `tapps-review-fixer`.

### 6.1 Add Missing Frontmatter Fields

**Priority: P1** | **Files:** `pipeline/platform_subagents.py`

**2026 platform validation:** Subagent frontmatter supports fields TappsMCP doesn't generate:

| Field | Status | Recommendation |
|-------|--------|---------------|
| `name` | Used | Correct |
| `description` | Used | Correct |
| `tools` | Used | Correct |
| `model` | NOT used | **Add:** `tapps-researcher` should be `model: haiku`, `tapps-reviewer` should be `model: sonnet` |
| `permissionMode` | NOT used | **Add:** `tapps-researcher` should be `permissionMode: plan` (read-only) |
| `maxTurns` | NOT used | **Add:** prevent runaway agents. `tapps-researcher: 15`, `tapps-reviewer: 20`, `tapps-validator: 10` |
| `skills` | NOT used | **Add:** preload relevant TappsMCP skills (e.g., `tapps-reviewer` gets `tapps-score` and `tapps-gate`) |
| `mcpServers` | NOT used | **Critical:** subagents need MCP server access. Add `mcpServers: { tapps-mcp: {} }` |
| `memory` | NOT used | **Add for tapps-reviewer:** `memory: project` for persistent quality patterns |
| `isolation` | NOT used | **Add for tapps-review-fixer:** `isolation: worktree` |
| `background` | NOT used | Optional |

**AI OS concept:** AI OS's agents specify model routing (`code-reviewer` uses Opus for deep analysis, `researcher` uses Sonnet for web research). TappsMCP's generated agents inherit the parent model, which is wasteful for read-only research tasks.

**Most critical missing field:** `mcpServers`. Without it, spawned subagents cannot call TappsMCP tools at all. The current workaround (subagents inheriting parent MCP connections) works in some Claude Code versions but is not guaranteed.

**Improvement:**
```yaml
---
name: tapps-reviewer
description: Review Python files for quality issues...
model: sonnet
maxTurns: 20
permissionMode: acceptEdits
mcpServers:
  tapps-mcp: {}
skills:
  - tapps-score
  - tapps-gate
memory: project
---
```

**Estimated effort:** 8-16 hours. Template updates + testing MCP server inheritance.

---

### 6.2 Quality Watchdog Subagent

**Priority: P2** | **Files:** `pipeline/platform_subagents.py`

**AI OS concept:** AI OS has a `code-reviewer` agent for read-only analysis. TappsMCP could generate a specialized "quality watchdog" subagent for Agent Teams.

**2026 platform validation:** Agent Teams use `TeammateIdle` and `TaskCompleted` hooks. A quality watchdog teammate can enforce quality gates within a team workflow.

**Improvement:**
- Generate a `tapps-quality-watchdog` subagent with:
  - `model: haiku` (lightweight, cost-effective)
  - `permissionMode: plan` (read-only, cannot edit)
  - `mcpServers: { tapps-mcp: {} }`
  - `skills: [tapps-score, tapps-gate, tapps-validate]`
  - `memory: project` (accumulate quality patterns over time)
  - Description: "Monitor code quality for agent team tasks. Score changed files, enforce gates, and report quality issues."
- Generate corresponding `TeammateIdle` and `TaskCompleted` hooks that wake the watchdog

**Estimated effort:** 1-2 days. New agent template + hook integration.

---

## 7. Pipeline & Onboarding

### Current State

`tapps_init` bootstraps TappsMCP in consuming projects: creates AGENTS.md, TECH_STACK.md, platform rules, hooks, agents, skills. It's fully programmatic with no interactive prompts.

### 7.1 Interactive First-Run Experience

**Priority: P2** | **Files:** `pipeline/init.py`, `server_pipeline_tools.py`

**AI OS concept:** AI OS's `business-setup` skill runs a 5-phase conversational wizard that populates context files based on user answers. This is the product's "killer feature" -- it transforms a generic template into a personalized workspace. TappsMCP's `tapps_init` generates everything from settings alone, with no user interaction.

**Improvement:**
- When `tapps_init` is called for the first time (no existing `.claude/` config), present an optional wizard via MCP elicitation:
  1. "What quality preset do you want?" (standard / strict / framework)
  2. "What engagement level?" (high / medium / low)
  3. "Generate agent team hooks?" (yes / no)
  4. "Include advanced skills?" (yes / no)
- Store answers in `.tapps-mcp.yaml` so they persist
- This does NOT replace the current API (all parameters remain available programmatically)
- Skip the wizard if any init parameters are explicitly provided

**2026 platform validation:** MCP supports elicitation (sampling) for interactive prompts. TappsMCP already has `common/elicitation.py` infrastructure but doesn't use it in init.

**Estimated effort:** 1-2 days. Elicitation integration + conditional prompting.

---

### 7.2 Project Context Injection (Context Files)

**Priority: P2** | **Files:** `pipeline/init.py`, `pipeline/platform_generators.py`

**AI OS concept:** AI OS generates `context/my-business.md` and `context/my-voice.md` as contextual files loaded by skills. These give the AI assistant domain-specific knowledge. TappsMCP generates `TECH_STACK.md` but no equivalent context injection for consuming projects.

**Improvement:**
- During `tapps_init`, generate `.claude/rules/quality-context.md` with path-scoped rules:
  ```yaml
  ---
  paths:
    - "**/*.py"
  ---
  # Python Quality Context
  - Run tapps_quick_check after editing Python files
  - Use tapps_research before using unfamiliar library APIs
  - Call tapps_validate_changed before declaring work complete
  ```
- This leverages 2026's `.claude/rules/` path frontmatter for conditional loading -- rules only activate when Claude reads Python files
- Complements AGENTS.md (always loaded) with targeted, context-aware reminders

**2026 platform validation:** `.claude/rules/*.md` files with `paths:` frontmatter confirmed in 2026 docs. Rules without paths load unconditionally; rules with paths trigger when Claude reads matching files. Supports glob patterns.

**Estimated effort:** 4-8 hours. New rule template + init integration.

---

### 7.3 Rollback Mechanism for Upgrades

**Priority: P3** | **Files:** `pipeline/upgrade.py`

**AI OS concept:** AI OS has no upgrade mechanism at all (one of its weaknesses). TappsMCP has `tapps_upgrade` but no rollback if an upgrade breaks something.

**Improvement:**
- Before overwriting files during upgrade, create a backup in `.tapps-mcp/backups/{timestamp}/`
- Store a manifest of changed files
- Add a `tapps_rollback` tool or CLI command that restores from the latest backup
- This is defensive design for a tool that modifies other projects' configurations

**Estimated effort:** 1-2 days. Backup logic + restore mechanism.

---

## 8. Knowledge & Documentation Backend

### Current State

`knowledge/` provides documentation lookup via LookupEngine with Context7 + LlmsTxt providers, a stale-while-revalidate cache, circuit breaker, and fuzzy matching.

### 8.1 Cache Eviction Policy

**Priority: P2** | **Files:** `knowledge/cache.py`

**AI OS concept:** AI OS's Pinecone vector storage has no size limits (cloud-managed). TappsMCP's `KBCache` stores documentation on disk with per-library TTL and stale-while-revalidate, but has no total size limit or eviction policy.

**Current behavior:** Cache grows unboundedly at `{project_root}/.tapps-mcp-cache/`. Over time, for projects that look up many libraries, this can grow to hundreds of MB.

**Improvement:**
- Add a configurable `cache_max_mb` setting (default: 100MB)
- Implement LRU eviction: when total cache size exceeds the limit, evict least-recently-accessed entries
- Track access timestamps in a cache metadata file
- Run eviction check during `tapps_session_start`

**Estimated effort:** 4-8 hours. Metadata tracking + eviction logic.

---

### 8.2 Expand LlmsTxt Provider URL List

**Priority: P3** | **Files:** `knowledge/providers/llms_txt_provider.py`

**Current state:** The LlmsTxt provider has 12 hardcoded URLs. Any library not in this list gets no LlmsTxt coverage.

**Improvement:**
- Expand to ~30 popular Python libraries
- Add a configuration option to specify custom LlmsTxt URLs in `.tapps-mcp.yaml`
- Consider auto-discovery: when a library isn't in the hardcoded list, try `https://{library}.readthedocs.io/llms.txt` and `https://docs.{library}.dev/llms.txt` as heuristic URLs

**Estimated effort:** 4-8 hours. URL list expansion + optional auto-discovery.

---

## 9. Scoring & Quality Gates

### Current State

`scoring/scorer.py` orchestrates 7-category scoring. Full mode runs ruff, mypy, bandit, radon concurrently. Quality gates evaluate pass/fail against presets.

### 9.1 Gate Failure Weighting

**Priority: P2** | **Files:** `gates/evaluator.py`

**AI OS concept:** AI OS doesn't have quality gates (one of its weaknesses). But TappsMCP's gate evaluator treats all category failures equally. A file scoring 69/70 overall but 9/10 on security should not fail the same way as a file scoring 69/70 overall with 2/10 on security.

**Improvement:**
- Add severity-weighted gate evaluation: security failures are more critical than devex failures
- Use the existing `ScoringWeights` (security=0.27, devex=0.05) to weight gate failure messages
- When a gate fails, order the failing categories by scoring weight, not alphabetically
- Add a `critical_categories` concept: if security or maintainability are below a floor, the gate fails regardless of overall score

**Estimated effort:** 4-8 hours. Evaluator logic update.

---

### 9.2 Test Coverage Data Integration

**Priority: P3** | **Files:** `scoring/scorer.py`

**Current state:** The `test_coverage` scoring category uses heuristics (checks for `test_` files, `conftest.py` presence, import patterns). It does not read actual coverage data.

**Improvement:**
- If a `.coverage` or `coverage.xml` file exists in the project root, parse it for the scored file's actual coverage percentage
- This converts a heuristic estimate into a real measurement
- Fall back to the current heuristic when no coverage data is available
- Mark the result with `source: "coverage.xml"` vs `source: "heuristic"` for transparency

**Estimated effort:** 1-2 days. Coverage file parsing + scorer integration.

---

## 10. Platform Distribution

### 10.1 Plugin Packaging

**Priority: P1** | **Files:** new `distribution/plugin_builder.py`

**AI OS concept (Recommendation 8):** AI OS was advised to repackage as a Claude Code plugin. TappsMCP could distribute as a plugin, bundling its MCP server + skills + agents + hooks + rules into a single installable unit.

**2026 platform validation:** Plugin structure is confirmed:
```
tapps-mcp-plugin/
+-- .claude-plugin/
|   +-- plugin.json           # Manifest
+-- skills/                   # 7 TappsMCP skills
+-- agents/                   # 4 TappsMCP agents
+-- hooks/
|   +-- hooks.json            # 7+ TappsMCP hooks
+-- .mcp.json                 # TappsMCP MCP server config
```

**Improvement:**
- Add a `tapps-mcp build-plugin` CLI command that:
  1. Generates the plugin directory structure
  2. Creates `plugin.json` with version, description, author
  3. Copies generated skills/agents into the plugin
  4. Creates `hooks.json` from hook templates
  5. Creates `.mcp.json` referencing the TappsMCP binary/server
- This replaces `tapps_init` for Claude Code users -- one command installs everything
- Marketplace distribution enables one-click installation for consuming projects

**Why this matters:** Currently, `tapps_init` must be run manually in each project and generates files that need version control. A plugin is installed once and applies to all projects, with automatic updates.

**Estimated effort:** 2-3 days. New module + CLI command + plugin manifest generation.

---

### 10.2 Generate Permission Rules

**Priority: P2** | **Files:** `pipeline/platform_generators.py`

**2026 platform validation:** Permission rules use specific syntax for MCP tools:
```json
{
  "allow": [
    "mcp__tapps-mcp__*",
    "Bash(uv run ruff *)",
    "Bash(uv run mypy *)"
  ]
}
```

**Current state:** TappsMCP generates `.claude/settings.json` with hooks but does not generate permission rules. Users must manually approve each TappsMCP tool call.

**Improvement:**
- During `tapps_init`, add TappsMCP permission rules to settings.json:
  - `"allow": ["mcp__tapps-mcp__*"]` -- auto-approve all TappsMCP MCP tools
  - Optionally at high engagement: `"deny": ["Bash(git push *)"]` until validation passes
- This reduces permission fatigue for consuming projects

**Estimated effort:** 2-4 hours. Settings.json generation update.

---

## 11. Summary Matrix

| # | Improvement | Priority | Area | Effort | AI OS Concept |
|---|-----------|----------|------|--------|---------------|
| 2.1 | BM25 retrieval upgrade | P1 | Memory | 1-2 days | smart_search.py hybrid search |
| 2.2 | Reinforce action in tapps_memory | P2 | Memory | 2-4 hrs | auto_capture.py feedback loop |
| 2.3 | Auto-capture Stop hook | P2 | Memory | 1-2 days | auto_capture.py transcript parsing |
| 2.4 | Automated GC in session_start | P3 | Memory | 2-4 hrs | Daily log rotation |
| 2.5 | Native memory documentation | P2 | Memory | 2-4 hrs | Tier 1-2 native adoption |
| 3.1 | Adaptive domain detector integration | P1 | Experts | 4-8 hrs | Model routing per skill |
| 3.2 | Query expansion / synonyms | P2 | Experts | 4-8 hrs | Hybrid search lexical coverage |
| 3.3 | Knowledge freshness during queries | P3 | Experts | 2-4 hrs | Daily log freshness |
| 4.1 | Fix skill frontmatter fields | **P0** | Skills | 4-8 hrs | AI OS skill best practices |
| 4.2 | Progressive skill tiers | P2 | Skills | 4-8 hrs | Starter vs power split |
| 5.1 | Prompt-type quality hook | P1 | Hooks | 4-8 hrs | Prompt-based guardrail (Rec 1) |
| 5.2 | Expand to 10 hook events | P1 | Hooks | 4-8 hrs | 8-event coverage (Rec 4) |
| 5.3 | Blocking hooks at high engagement | P2 | Hooks | 8-16 hrs | Exit code 2 enforcement |
| 6.1 | Fix subagent frontmatter fields | P1 | Subagents | 8-16 hrs | Model routing + mcpServers |
| 6.2 | Quality watchdog agent | P2 | Subagents | 1-2 days | code-reviewer agent |
| 7.1 | Interactive first-run wizard | P2 | Pipeline | 1-2 days | business-setup skill |
| 7.2 | Path-scoped quality rules | P2 | Pipeline | 4-8 hrs | Context file injection |
| 7.3 | Upgrade rollback mechanism | P3 | Pipeline | 1-2 days | (AI OS lacks, defensive design) |
| 8.1 | Cache eviction policy | P2 | Knowledge | 4-8 hrs | Cloud storage limits |
| 8.2 | Expand LlmsTxt URLs | P3 | Knowledge | 4-8 hrs | (Coverage expansion) |
| 9.1 | Gate failure weighting | P2 | Scoring | 4-8 hrs | (AI OS lacks gates entirely) |
| 9.2 | Real test coverage data | P3 | Scoring | 1-2 days | (Deterministic measurement) |
| 10.1 | Plugin packaging | P1 | Distribution | 2-3 days | Plugin repackaging (Rec 8) |
| 10.2 | Permission rule generation | P2 | Distribution | 2-4 hrs | Permission best practices |

### Priority Summary

**P0 (1 item):** Fix skill frontmatter (`tools` -> `allowed-tools`, add missing fields). This is a correctness bug -- TappsMCP generates skills with a non-standard field name.

**P1 (6 items):** BM25 retrieval, adaptive domain detector, prompt-type hooks, hook event expansion, subagent frontmatter, plugin packaging. These are the highest-impact improvements that leverage AI OS concepts to make TappsMCP significantly better for consuming projects.

**P2 (11 items):** Reinforcement endpoint, auto-capture hook, native memory docs, query expansion, progressive skill tiers, blocking hooks, quality watchdog, interactive wizard, path-scoped rules, cache eviction, gate weighting, permission rules. Each provides measurable value.

**P3 (5 items):** Automated GC, knowledge freshness, rollback, LlmsTxt expansion, test coverage data. Nice-to-have polish items.

### Estimated Total Effort

| Priority | Items | Estimated Hours |
|----------|-------|----------------|
| P0 | 1 | 4-8 |
| P1 | 6 | 60-100 |
| P2 | 11 | 60-110 |
| P3 | 5 | 30-50 |
| **Total** | **23** | **~150-270 hours** |

### Recommended Implementation Order

1. **4.1** Fix skill frontmatter (P0 -- correctness bug)
2. **6.1** Fix subagent frontmatter (P1 -- correctness + capability)
3. **3.1** Integrate adaptive domain detector (P1 -- code exists, needs wiring)
4. **5.1** + **5.2** Prompt-type hook + expanded events (P1 -- platform alignment)
5. **2.1** BM25 retrieval upgrade (P1 -- quality improvement)
6. **10.1** Plugin packaging (P1 -- distribution breakthrough)
7. **7.2** + **10.2** Path-scoped rules + permissions (P2 -- quick wins)
8. Remaining P2 items in any order
9. P3 items as time permits

---

*Generated from cross-referencing TappsMCP codebase against AI OS architectural patterns and 2026 Claude Code platform documentation. All platform features validated against official docs.*
