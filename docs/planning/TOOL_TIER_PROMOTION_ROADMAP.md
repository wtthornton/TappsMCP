# TappsMCP Tool Tier Promotion Roadmap

> **Date:** 2026-02-25
> **Purpose:** Identify enhancements to promote lower-tier MCP tools to Tier 1 usefulness for LLM AI code assistants, grounded in 2026 best practices.

---

## Current Tool Tier Rankings (for LLM AI Assistants)

### Tier 1 -- Core Workflow (used nearly every session)

| Rank | Tool | Why |
|------|------|-----|
| 1 | `tapps_quick_check` | Go-to after every edit. Fast score + gate + security in one call. |
| 2 | `tapps_validate_changed` | Final validation before declaring work done. Catches what was missed. |
| 3 | `tapps_score_file` | Deep 7-category scoring when quick_check flags something. |
| 4 | `tapps_session_start` | Required first call -- sets up project context for everything else. |
| 5 | `tapps_quality_gate` | Pass/fail verdict. The "are we done?" check. |

### Tier 2 -- Frequently Useful

| Rank | Tool | Why |
|------|------|-----|
| 6 | `tapps_security_scan` | Essential when touching auth, config, secrets, or user input. |
| 7 | `tapps_lookup_docs` | Prevents hallucinated library APIs. Real docs > LLM memory. |
| 8 | `tapps_research` | Expert + docs in one call. Best for "how should I approach this?" |
| 9 | `tapps_impact_analysis` | Before refactoring or deleting -- shows blast radius. |
| 10 | `tapps_checklist` | Final step sanity check. Easy to forget edge cases without it. |

### Tier 3 -- Situationally Valuable

| Rank | Tool | Why |
|------|------|-----|
| 11 | `tapps_consult_expert` | Good for architecture/security/testing decisions. Overlaps with `tapps_research`. |
| 12 | `tapps_dead_code` | Useful during refactors to find what can be deleted safely. |
| 13 | `tapps_dependency_graph` | Circular import detection -- critical when needed, rarely needed. |
| 14 | `tapps_report` | Nice for project-wide health overview. More useful for humans. |
| 15 | `tapps_dependency_scan` | Vulnerability scanning. Important but dependencies rarely change. |
| 16 | `tapps_validate_config` | Only when editing Dockerfiles or docker-compose. Niche but accurate. |
| 17 | `tapps_session_notes` | Persisting context across tool calls. Helpful in long sessions. |

### Tier 4 -- Administrative / Setup

| Rank | Tool | Why |
|------|------|-----|
| 18 | `tapps_init` | One-time project bootstrap. Powerful but used once per project. |
| 19 | `tapps_upgrade` | After version bumps only. |
| 20 | `tapps_doctor` | Troubleshooting when tools misbehave. |
| 21 | `tapps_project_profile` | Bundled into `session_start` -- rarely need standalone. |
| 22 | `tapps_server_info` | Also bundled into `session_start`. |
| 23 | `tapps_list_experts` | Metadata about experts. Domains already known. |

### Tier 5 -- Meta / Analytics

| Rank | Tool | Why |
|------|------|-----|
| 24 | `tapps_dashboard` | Trends and metrics. More for project managers than mid-task AI. |
| 25 | `tapps_stats` | Usage stats on the tools themselves. Interesting, not actionable. |
| 26 | `tapps_feedback` | Reporting if a tool helped. Improves adaptive weights over time. |

### Resources

| Rank | Resource | Why |
|------|----------|-----|
| 27 | `get_quality_presets` | Reference data -- presets are usually already known. |
| 28 | `get_scoring_weights` | Niche debugging of scoring behavior. |
| 29 | `list_knowledge_domains` | Already documented in tool descriptions. |

---

## CLI Commands Ranked by LLM Usefulness

### Tier 1 -- Essential (used almost every session)

1. **`uv run pytest tests/ -v`** -- Run all tests. Primary way to verify changes work.
2. **`uv run ruff check src/`** -- Lint check. Fast feedback before full test suite.
3. **`uv run ruff format --check src/`** -- Format check. Catches style issues.
4. **`uv run pytest tests/ --cov=tapps_mcp --cov-report=term-missing`** -- Tests with coverage.

### Tier 2 -- Important (quality assurance)

5. **`uv run mypy --strict src/tapps_mcp/`** -- Strict type checking.
6. **`uv run tapps-mcp doctor`** -- Diagnose configuration issues.

### Tier 3 -- Situational

7. **`uv run tapps-mcp upgrade --dry-run`** -- Preview upgrade changes.
8. **`uv run tapps-mcp upgrade`** -- Apply upgrades.
9. **`uv run tapps-mcp serve`** -- Run the MCP server for integration testing.

### Tier 4 -- Rarely needed

10. **`uv sync`** -- Install dependencies. Only at setup or after dependency changes.

---

## 2026 Best Practices Driving These Recommendations

### Shift-Left Security
Security scanning should happen inline with every quality check, not as a separate manual step. The most impactful tools provide feedback directly within the developer's environment before code is committed.
- Source: [Best AI Code Review Tools 2026](https://www.aikido.dev/blog/best-ai-code-review-tools)
- Source: [Cloudflare Shift-Left Security](https://www.infoq.com/news/2026/01/cloudflare-security-shift-left/)

### System-Aware Agentic Reviewers
The next era of AI code review is defined by system-aware reviewers that understand contracts, dependencies, and production impact. Multi-agent approaches deploy dedicated agents for code review, test generation, security scanning, and deployment -- each specialized, all coordinated.
- Source: [AI Code Review Tools 2026](https://www.qodo.ai/blog/best-ai-code-review-tools-2026/)

### Context Engineering
Tools should maximize context quality per token. LLMs deliver more per token with better context management, fewer retries, and stronger first passes. Loading tools on demand, filtering data before it reaches the model, and executing complex logic in a single step.
- Source: [Context Engineering for AI Agents](https://weaviate.io/blog/context-engineering)
- Source: [Anthropic Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)

### Agent Memory as First-Class Primitive
2026 is when agent memory becomes a first-class MCP primitive. Shared memory systems understand context -- AI remembers relevant information across conversations and coding sessions.
- Source: [MCP Predictions for 2026](https://dev.to/blackgirlbytes/my-predictions-for-mcp-and-ai-assisted-coding-in-2026-16bm)

### Quality Gates Around AI Contributions
A key goal is to bolster the quality gates around AI code contribution: more tests, more monitoring, and potentially AI-on-AI code reviews. An AI-friendly workflow requires strong automation.
- Source: [Addy Osmani's LLM Coding Workflow 2026](https://addyosmani.com/blog/ai-coding-workflow/)

### Net Productivity Over Speed
Developers care about net productivity -- the entire workflow, not isolated moments. Tools that generate correct code on the first pass and fit naturally into existing workflows earn praise; tools requiring constant correction lose favor.
- Source: [Best AI Tools for Coding 2026](https://www.builder.io/blog/best-ai-tools-2026)

---

## Promotion Analysis: Tools That Can Reach Tier 1

### 1. `tapps_security_scan` (Tier 2 --> Tier 1)

**Current limitations:**
- Single-file only, no project-wide or directory scan
- Finding output hard-capped at 50 items (silently dropped beyond)
- When bandit is missing, degrades silently with no fallback static analysis
- Synchronous function -- blocks the event loop
- No severity threshold filter
- No `.bandit` config integration

**Enhancement: Auto-integrate into `tapps_quick_check` and `tapps_validate_changed`**

| Change | Impact |
|--------|--------|
| Add `security_depth` param to `quick_check` (`"basic"` / `"full"`) | Eliminates need to call `security_scan` separately |
| Add multi-file / directory scanning | Scan `src/` in one call instead of file-by-file |
| Add severity threshold filter | Only care about HIGH+ in most sessions -- reduce noise |

**Verdict:** If security scanning is baked into tools already called every session, it becomes Tier 1 by default.

---

### 2. `tapps_research` (Tier 2 --> Tier 1)

**Current limitations:**
- Docs only fetched when `chunks_used == 0` OR `confidence < 0.5` -- high-confidence RAG answers never supplemented with current docs
- Defaults to `library="python"` when library can't be detected -- produces useless results
- `consult_expert` called via `asyncio.to_thread` (blocking)
- Question capped at 2000 chars -- too short for code snippets
- Structured output silently swallows construction errors

**Enhancement: Context-aware research with always-on docs**

| Change | Impact |
|--------|--------|
| Always supplement with docs (remove `confidence < 0.5` gate) | Expert answers backed by current API docs = much more reliable |
| Infer library from file being edited (use project profile) | No more defaulting to `library="python"` |
| Add `file_context` parameter (path to file being worked on) | Expert advice grounded in actual code context |
| Increase question limit from 2000 --> 5000 chars | Allow pasting code snippets in questions |

**Verdict:** With file context and always-on docs, this becomes the go-to tool for every non-trivial decision.

---

### 3. `tapps_impact_analysis` (Tier 2 --> Tier 1)

**Current limitations:**
- Single-file only; no batch analysis
- Python files only (AST-based static import graph)
- `max_depth=3` hardcoded -- not exposed as parameter
- Dynamic imports (`importlib.import_module`) not detected
- Structured content loses `impact_type` and `reason` fields
- Synchronous -- blocks event loop for large projects

**Enhancement: Auto-integrate into `tapps_validate_changed`**

| Change | Impact |
|--------|--------|
| Add impact summary to `validate_changed` output | Every validation shows what changes affect |
| Support multi-file input (batch impact) | One call for 5 changed files, not 5 separate calls |
| Include in `tapps_checklist` evaluation | Checklist flags "modified X but didn't check impact on Y" |
| Expose `max_depth` parameter | Control analysis depth for large codebases |

**Verdict:** Blast radius data in every `validate_changed` run = automatic promotion via integration.

---

### 4. `tapps_checklist` (Tier 2 --> Tier 1)

**Current limitations:**
- Only checks which tools have been called (via `CallTracker`) -- does not check actual code state
- Fresh session shows all tools as uncalled even if called in previous session
- Invalid `task_type` values silently fall through
- No way to reset call tracker mid-session
- Structured output drops `*_hints` fields

**Enhancement: Make it a "pre-flight check" that runs actual validations**

| Change | Impact |
|--------|--------|
| Run `quick_check` on changed files if not already done | Catch quality issues that were forgotten |
| Run security scan if task_type is `"security"` or `"feature"` | Don't just remind -- execute |
| Return actual pass/fail for each item with results | "Tests pass: YES, Security: 2 HIGH issues" vs "security_scan: not called" |
| Add `auto_fix=True` option to run fixable items | One-shot "make everything green" |

**Verdict:** A checklist that executes rather than reminds = the ultimate "am I done?" tool.

---

### 5. `tapps_dead_code` (Tier 3 --> Tier 2, possibly Tier 1)

**Current limitations:**
- Single-file vulture is nearly useless -- cross-file analysis is the whole point
- Silent failure when vulture isn't installed (no degraded flag)
- No structured output (`structuredContent`)
- `min_confidence` not validated for range
- Whitelist patterns from settings only, no per-call overrides
- Timeout hardcoded to 30 seconds

**Enhancement: Project-aware dead code detection**

| Change | Impact |
|--------|--------|
| Add project-wide mode (scan all files, cross-reference) | Dramatically reduces false positives |
| Add `scope` param: `"file"` / `"project"` / `"changed"` | `"changed"` = only scan files in git diff |
| Surface degraded flag when vulture is missing | LLM needs to know when tool isn't actually scanning |
| Integrate into `tapps_report` | Dead code metrics in project health dashboard |

**Verdict:** With project-wide scanning and a `"changed"` scope, useful during every refactoring session.

---

### 6. `tapps_dashboard` + `tapps_feedback` + `tapps_stats` (Tier 5 --> Tier 2)

**Current limitations (`tapps_dashboard`):**
- `time_range` accepted but not used to filter underlying data (just a label)
- HTML format writes file to disk -- contradicts read-only annotation
- OTel format only fetches last 100 executions
- Unknown formats silently fall through to JSON
- No structured output

**Current limitations (`tapps_feedback`):**
- `tool_name` not validated against known tools -- arbitrary strings accepted
- `context` not sanitized (unlike other tools)
- Feedback doesn't influence scoring/expert weights in real-time
- No deduplication -- same feedback recorded multiple times
- Synchronous -- blocks event loop during disk write

**Current limitations (`tapps_stats`):**
- Returns raw usage data with no actionable insights
- No recommendations based on usage patterns

**Enhancement: Close the adaptive learning loop**

| Change | Impact |
|--------|--------|
| `tapps_feedback` adjusts scoring weights in real-time | Feedback actually improves the next score |
| `tapps_stats` returns actionable recommendations | "You skip security_scan 80% -- consider auto-security in quick_check" |
| `tapps_dashboard` surfaces quality trends per-session | "Quality trending down in last 3 files -- slow down" |
| Fix `time_range` to actually filter data | Currently a label-only bug |

---

## Priority Roadmap

| Priority | Enhancement | Tools Affected | Effort | Promotion |
|----------|-------------|----------------|--------|-----------|
| **P0** | Bake security + impact into `validate_changed` | `security_scan`, `impact_analysis` | Medium | Both --> Tier 1 |
| **P1** | Make `checklist` execute validations, not just track calls | `checklist` | Medium | --> Tier 1 |
| **P2** | Always-on docs + file context in `research` | `research`, `lookup_docs` | Small | --> Tier 1 |
| **P3** | Project-wide dead code with `"changed"` scope | `dead_code` | Medium | --> Tier 2+ |
| **P4** | Close the adaptive feedback loop | `feedback`, `stats`, `dashboard` | Large | --> Tier 2 |

### Key Insight

The P0 change alone -- enriching `validate_changed` with security and impact data -- would effectively promote 3 tools to Tier 1 by making their value **automatic rather than opt-in**. The pattern across all promotions is the same: **tools that require the LLM to remember to call them will always be lower tier than tools integrated into the workflow the LLM already follows.**

---

## Sources

- [Best AI Code Review Tools 2026 - Qodo](https://www.qodo.ai/blog/best-ai-code-review-tools-2026/)
- [Addy Osmani's LLM Coding Workflow 2026](https://addyosmani.com/blog/ai-coding-workflow/)
- [MCP Predictions for 2026](https://dev.to/blackgirlbytes/my-predictions-for-mcp-and-ai-assisted-coding-in-2026-16bm)
- [Best AI Code Review Tools - Aikido](https://www.aikido.dev/blog/best-ai-code-review-tools)
- [Context Engineering for AI Agents - Weaviate](https://weaviate.io/blog/context-engineering)
- [Best MCP Servers 2026 - Builder.io](https://www.builder.io/blog/best-mcp-servers-2026)
- [Anthropic Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [Cloudflare Shift-Left Security - InfoQ](https://www.infoq.com/news/2026/01/cloudflare-security-shift-left/)
- [Best AI Tools for Coding 2026 - Builder.io](https://www.builder.io/blog/best-ai-tools-2026)
- [Best LLMs for Coding 2026 - Builder.io](https://www.builder.io/blog/best-llms-for-coding)
