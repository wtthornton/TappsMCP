# 2026 MCP Tools: Best Practices & Optimal Tool Count for LLMs

**Date:** 2026-03-11  
**Purpose:** Research on MCP tool best practices (2026) and evidence-based guidance on how many tools to expose to LLMs and what is optimal.

---

## Executive summary

- **Best practices (2026):** Single-responsibility servers, defense-in-depth security, fail-safe design, contracts-first development, and **curated tool sets**—not “one server with everything.”
- **Tool count vs. LLM performance:** More tools **hurt** accuracy, latency, and cost. Research and production reports agree:
  - **~30 tools:** Critical threshold where overlap and confusion begin (large models).
  - **~19 tools:** Reported sweet spot for smaller models (e.g., Llama 3.1 8B).
  - **80–100+ tools:** Widespread reports of degraded or failing tool selection; 100+ is “virtually guaranteed to fail.”
- **Context budget:** Tool definitions alone can consume **tens of thousands of tokens per server** (e.g., GitHub MCP ~42K). Keeping tools **under ~20–40% of context** is recommended; many setups sit at 40–60% before the first user message.
- **Optimal approach:** **Fewer, focused tools**—curate by task/use case, use **dynamic/progressive tool loading** when available, keep descriptions **short and precise**, and consider **task-specific sub-agents** (or servers) instead of one agent with every tool.

---

## 1. 2026 MCP best practices (architecture & operations)

Sources: [MCP Best Practice Guide](https://mcp-best-practice.github.io/mcp-best-practice/), [Model Context Protocol best practices](https://modelcontextprotocol.info/docs/best-practices/), Lushbinary/Nerd Level Tech 2026 guides.

### 1.1 Architectural principles

| Principle | Guidance |
|-----------|----------|
| **Single responsibility** | One MCP server = one clear purpose. Avoid monolithic “mega-servers” that mix DB, files, APIs, email, etc. |
| **Defense in depth** | Layer security: network isolation, auth, authorization, input validation, output sanitization, audit logging. |
| **Fail-safe design** | Circuit breakers, caching, rate limiting, graceful degradation. Return safe defaults on unexpected failure. |
| **Stateless defaults** | Prefer stateless servers; manage state explicitly when required. |

### 1.2 Lifecycle practices

- **Develop:** Contracts-first design, observability from day one, least-privilege integrations.
- **Test:** Unit, integration, E2E; evals and baselines; coverage and CI gates.
- **Package:** Containers, SBOMs/signing, provenance, trusted catalogs.
- **Deploy:** Gateway front-door, environment separation, sandboxing, rollout strategies.
- **Operate:** SLOs, monitoring, catalog and approvals, multi-tenancy.
- **Secure:** Identity/access, policy-as-code, runtime controls, continuous assurance.
- **Use (clients):** Host choices, gateway mediation, **good-citizen patterns**—don’t load every tool for every task.

### 1.3 Client consumption: “good citizen” pattern

Best practice is to **not** expose all tools to the LLM at once. Separate MCPs by group and **disable or don’t load** servers/tools when not needed for the current task. Manually curate or dynamically select tools per task.

---

## 2. How many tools can an LLM handle? (research & production data)

### 2.1 Token cost of tool definitions

Tool definitions (name, description, input schema) are **token-heavy**. Representative numbers:

| MCP server | Approx. tokens (definitions only) |
|------------|-----------------------------------|
| GitHub MCP (official) | ~42,000 |
| Slack MCP | ~8,000 |
| Notion MCP | ~6,500 |
| Linear MCP | ~5,800 |
| Postgres MCP | ~3,200 |

*Source: [DEV – MCP Tool Overload](https://dev.to/nebulagg/mcp-tool-overload-why-more-tools-make-your-agent-worse-5a49).*

A single well-documented tool often uses **500–1,500 tokens**. Aggregated (Speakeasy-style benchmarks):

| Toolset size | Initial token consumption |
|--------------|---------------------------|
| 40 tools | ~43,300 |
| 100 tools | ~128,900 |
| 200 tools | ~261,700 (exceeds 200K context) |
| 400 tools | ~405,100 |

*Source: [Progressive Disclosure MCP](https://matthewkruczek.ai/blog/progressive-disclosure-mcp-servers.html).*

So “how many tools” is also “how much context budget?” Keeping tool definitions **below ~20–40% of total context** is a common recommendation; above that, the rest of the prompt (system instructions, conversation, task) gets starved.

### 2.2 Accuracy and cognitive overload

- **“Lost in the middle”:** When relevant context is buried in a large window, LLM accuracy drops.
- **Tool collision:** With many similar tools (`search_issues`, `list_issues`, `get_issue`, `find_issues_by_label`), semantic boundaries blur; the model picks the wrong tool or hallucinates parameters.
- **Reported thresholds:**
  - **Large models (e.g., DeepSeek-v3):** Strong degradation above **~30 tools**; **100+ tools** → “virtually guaranteed to fail” at tool selection.
  - **Smaller models (e.g., Llama 3.1 8B):** **~19 tools** = sweet spot; **~46 tools** = failure point.
  - **Production (GitHub discussion #1251):** “Reported issues when reaching **80–90**”; “using currently **30–40** no issues” and “trying to separate MCPs by groups to disable when not needed.”
  - **Community (qdrddr):** “Around **50** you’ll start noticing suboptimal responses”; with ~10 tools per server that implies **~5 MCP servers**.
  - **Community (ckaraca):** “Over **30** is confusing most of the time”; use a proxy and disable tools not needed for the current task.

*Sources: [Speakeasy – Less is more](https://www.speakeasy.com/mcp/building-servers/less-is-more), [GitHub MCP discussion #1251](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1251), Southern Illinois University research (arXiv 2411.15399), “Less is More: Optimizing Function Calling for LLM Execution on Edge Devices.”*

### 2.3 Benchmark: minimal vs. full toolset

Example (create GitHub issue task):

- **Minimal toolset** (~4 tools, ~1,200 tokens): **~95%** correct tool selection.
- **Full GitHub MCP** (~46 tools, ~42,000 tokens): **~71%** correct tool selection.

So a **24-point accuracy drop** from context bloat alone—same model, same task, same system prompt.

*Source: [DEV – MCP Tool Overload](https://dev.to/nebulagg/mcp-tool-overload-why-more-tools-make-your-agent-worse-5a49).*

### 2.4 Lazy / progressive tool loading (Anthropic)

When tool schemas are loaded on demand instead of upfront:

- **Opus 4:** 49% → **74%** accuracy on tool selection.
- **Opus 4.5:** 79.5% → **88.1%** accuracy.

Improvement comes from showing the model **fewer, more relevant** tools, not from a different model.

*Source: [Progressive Disclosure MCP](https://matthewkruczek.ai/blog/progressive-disclosure-mcp-servers.html).*

---

## 3. What is optimal?

### 3.1 Target ranges (summary)

| Context | Optimal / safe range | Avoid |
|---------|----------------------|--------|
| **Total tools in context** | **&lt; 30** (large models); **&lt; 20** (smaller models or strict) | &gt; 50; &gt; 80–100 |
| **MCP servers** | **2–5** if each has ~10 tools | Many servers × many tools |
| **Context budget for tools** | **&lt; 20–40%** of context window | &gt; 40–50% |
| **Per-server tool count** | **Focused set per use case** (e.g., 8–15) | Monolithic 50+ tool servers |

### 3.2 Optimal strategies (2026)

1. **Curate by use case**  
   Expose only the tools needed for the **current task** (e.g., “code quality” vs “docs” vs “security review”). Use separate MCP servers or tool groups and enable/disable by context.

2. **Dynamic / deferred tool loading**  
   Don’t load all tool schemas upfront. Options:
   - **Progressive disclosure:** Minimal listing (name + short description, no full schema) first; fetch full schema only when the model chooses a tool (reported **85–100×** token reduction, **95%** initial context reduction in some setups).
   - **Tool search / intent-based loading:** One cheap classifier or search step to select tool groups, then load only those tools.
   - **Anthropic `defer_loading`:** API support for lazy tool loading; Claude Code can enable MCP Tool Search when tools would exceed ~10% of context.

3. **Shorter, precise tool descriptions**  
   Descriptions written for “completeness” are often 3–5× longer than needed. Trim to: **what it does + required/optional args**. Saves tokens and reduces confusion.

4. **Tool namespacing**  
   Use clear prefixes (e.g., `github__create_issue`, `notion__search_pages`) so the model can rule out whole clusters without reading every schema.

5. **Task-specific sub-agents (or servers)**  
   Instead of one agent with 80 tools, use an orchestrator that delegates to focused agents/servers (e.g., “GitHub agent” with 8 tools, “Slack agent” with 4). Each sub-agent has a small, relevant toolset.

6. **Audit before optimizing**  
   Measure token cost of your current tool definitions (e.g., with `tiktoken`). If tools use **&gt; 20%** of context, treat it as bloat worth fixing.

---

## 4. Implications for TappsMCP and DocsMCP

- **TappsMCP:** **29 tools.**  
- **DocsMCP:** **22 tools.**  
- **Combined:** **51 tools** in one session if both servers are enabled.

**Assessment:**

- 51 tools is **above** the commonly cited “safe” range (30–40) and in the zone where “suboptimal responses” and confusion are reported.
- A single server (Tapps or Docs) at 29 or 22 is **near or within** the 30-tool threshold but already non-trivial for smaller models.

**Recommendations for this repo:**

1. **Document “recommended tool subsets” by task** (e.g., “coding session” vs “docs-only” vs “security review”) and map them to the existing [TOOL-TIER-RANKING.md](../TOOL-TIER-RANKING.md) (Tier 1–2 = highest leverage; Tier 3–4 = situational/support).
2. **Encourage clients to enable only one of TappsMCP or DocsMCP** when the task is clearly code-quality-only or docs-only, to keep active tool count in the low 20s.
3. **When both are needed:** Prefer instructing the LLM (e.g., in AGENTS.md or system prompt) to **prioritize Tier 1 and Tier 2 tools** and use Tier 3–4 only when the task explicitly requires them; this doesn’t reduce tool count but focuses attention.
4. **Long term:** Consider **progressive disclosure or tool groups** (e.g., “pipeline,” “scoring,” “experts,” “docs”) so hosts can load only the group relevant to the current task, if the MCP stack supports it.
5. **Keep tool descriptions concise** in server definitions (name + one-line purpose + key args); avoid long tutorials in the schema.

---

## 5. Can we default tools in an MCP to off?

**Short answer: yes.** The protocol does not define an “on/off” flag per tool; it only defines that the server returns a list of tools from `tools/list`. So “default off” means **the server does not advertise** those tools (i.e., it does not register or return them). That is under the server’s control.

### 5.1 How it works

- **MCP protocol:** The client calls `tools/list`; the server returns the set of tools it advertises. There is no standard field for “enabled” or “default off.” Whatever the server includes in that list is what the client (and thus the LLM) sees.
- **Server-side “default off”:** The server **only registers** tools that are “on.” So at startup, instead of registering all 29 tools, the server reads config (e.g. `enabled_tools` allow list or `disabled_tools` deny list) and only calls `mcp.tool()(handler)` for tools that pass the filter. `tools/list` then returns only that subset. So **yes, we can default tools to off** by not registering them unless explicitly enabled.
- **Client-side filtering:** Some clients (e.g. OpenAI Codex) support `enabled_tools` / `disabled_tools` in their MCP server config; they filter the list returned by the server before passing tools to the LLM. So even if the server sends all tools, the client can show only a subset. That is **client-dependent** (Cursor, Claude Code, etc. may or may not support it). The MCP spec issue [#278](https://github.com/modelcontextprotocol/specification/issues/278) (client-side selective disable) was closed as dormant; there is no standard for it yet.

### 5.2 Recommendation: implement server-side “default off”

For TappsMCP and DocsMCP we can support **default tools off** on the server:

1. **Config**
   - **Option A (allow list):** `enabled_tools: ["tapps_session_start", "tapps_quick_check", ...]`  
     - Default: a **core** set (e.g. Tier 1 only: ~7 TappsMCP tools). Empty or missing = “all tools” (current behavior).
   - **Option B (deny list):** `disabled_tools: ["tapps_dashboard", "tapps_stats", ...]`  
     - Default: `[]` (all enabled). Users disable specific tools.
   - **Option C (both):** Allow list takes precedence; if non-empty, only those tools are exposed. Otherwise, deny list is applied to the full set. Gives “default to core set” and “hide a few” in one place.

2. **Registration**
   - Before calling each `register(mcp)` (or inside each module’s `register()`), only register a tool if it passes the filter (in `enabled_tools` when set, or not in `disabled_tools`). No change to tool handlers; only to **whether** they are registered.

3. **Defaults**
   - **Recommended default:** Expose only a **core** set (e.g. Tier 1 from [TOOL-TIER-RANKING.md](../TOOL-TIER-RANKING.md): session_start, quick_check, validate_changed, quality_gate, checklist, lookup_docs, security_scan). Users who want the full 29 tools set `enabled_tools: []` or list all tools explicitly.

4. **Docs**
   - Document the new setting in AGENTS.md and config docs (e.g. “By default only core tools are exposed; set `enabled_tools` to customize.”).
   - Optionally document a few **presets** (e.g. `tool_preset: core | pipeline | full`) that map to fixed sets so users don’t maintain long lists.

Implementing this is a small, backward-compatible change: add one or two settings, a filter helper, and conditional registration; default “core” keeps tool count in the optimal range while still allowing “all on” when needed.

---

## 6. Docker MCP Toolkit and the “too many tools” issue (2026)

The [Docker MCP Toolkit](https://docs.docker.com/ai/mcp-catalog-and-toolkit/) (GA 2026) provides a managed distribution channel for MCP servers via Docker Desktop: a curated **MCP Catalog** (300+ verified server images), an **MCP Gateway** (stdio proxy that routes to containerized servers), and **profiles** (named server collections). It affects the “too many tools” problem in both helpful and potentially harmful ways.

### 6.1 How Docker MCP Toolkit helps

| Mechanism | How it helps |
|-----------|----------------|
| **Profiles** | Profiles are named collections of **servers**. You choose which servers are in a profile (e.g. `tapps-minimal` = only tapps-mcp vs `tapps-full` = tapps-mcp, docs-mcp, context7, github, filesystem). So you control **how many servers** (and thus total tools) are active. Minimal profile = one server ≈ 29 tools; full profile = five servers = much higher tool count unless you also use tool filtering. |
| **Per-tool filtering (gateway)** | The MCP Gateway supports **per-server, per-tool** allow/deny via `tools.yaml` and the CLI. You can enable or disable **individual tools** for each server in a profile. Semantics: server not in file = all tools enabled; server with list = only those tools enabled; server with `[]` = all tools for that server disabled. So the **gateway** can expose a subset of tools to the client without any server-side change. This is “default tools off” at the **gateway** layer. |
| **CLI and UI** | `docker mcp profile tools <profile> --enable <server>.<tool>` / `--disable` / `--enable-all` / `--disable-all`. In Docker Desktop, the profile’s **Tools** tab lists all tools from the profile’s servers and lets you enable or disable them. So users can curate a small set (e.g. only Tier 1 TappsMCP tools) and stay under the &lt;30-tool target. |
| **Single gateway entry** | The client configures one MCP entry (`MCP_DOCKER` → `docker mcp gateway run --profile <name>`). The gateway aggregates servers and applies tool filtering; the client sees one logical “server” with a filtered tool list. So tool count is under the user’s control at the gateway. |
| **Custom catalogs** | Orgs can define private catalogs with only approved servers, reducing the temptation to add many servers. |
| **Dynamic MCP can be disabled** | [Dynamic MCP](https://docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp/) lets agents discover and add servers mid-conversation (`mcp-find`, `mcp-add`), which can **increase** tool count during a session. It is on by default but can be turned off: `docker mcp feature disable dynamic-tools`. Disabling it avoids unbounded tool growth during a conversation. |

**Bottom line:** Docker MCP Toolkit **helps** by giving two levers: (1) **which servers** are in a profile (fewer servers ⇒ fewer tools), and (2) **which tools** from each server the gateway exposes (`tools.yaml` / profile tools). Used together, you can run “tapps-mcp + docs-mcp” but expose only 10–15 tools total, aligning with 2026 best practice.

### 6.2 How Docker MCP Toolkit can hurt (or be misused)

| Risk | Why it happens | Mitigation |
|------|----------------|------------|
| **Default is “all tools on”** | For each server in a profile, the gateway default is “all tools enabled” (server omitted from `tools.yaml` ⇒ all enabled). So out of the box, a profile with 5 servers still exposes 100+ tools unless the user explicitly trims via Tools tab or `docker mcp profile tools`. | Document “recommended” tool sets and provide example `tools.yaml` or profile export that enables only core tools (e.g. Tier 1). |
| **Catalog has 300+ servers** | Easy to add many servers to one profile. Without using the Tools tab or CLI to trim, users can end up with 80–100+ tools in a single profile and hit the “too many tools” degradation. | Recommend minimal or standard profiles in docs; encourage tool filtering for “full” profiles. |
| **Dynamic MCP on by default** | Agents can add servers (and their tools) during a conversation. That can grow the tool set mid-session and worsen context bloat. | For users who care about stable, small tool sets: `docker mcp feature disable dynamic-tools`. |
| **Discovery friction** | Users must know to use the Tools tab or `docker mcp profile tools` to trim. The toolkit enables curation but does not **default** to a small set. | Provide ready-made “minimal” or “core tools” profile exports and document the flow in AGENTS.md / Docker MCP docs. |

### 6.3 2026 takeaway

- **Docker MCP Toolkit helps** the “too many tools” issue when users **curate**: use a minimal profile (fewer servers) and/or use **per-tool filtering** (Tools tab or `tools.yaml`) so the gateway exposes only the tools needed for the task. The gateway’s tool filtering is a first-class, production-ready way to keep tool count in the optimal range **without** changing server code.
- **It hurts** if users add many servers to one profile and never trim tools: they still get 80–100+ tools. So the toolkit **enables** good behavior but doesn’t **enforce** it by default.
- **Recommendation for TappsMCP/DocsMCP:** In Docker MCP docs and `docker-mcp/` profiles, add a **“core tools”** profile or an example `tools.yaml` that enables only Tier 1 (and optionally Tier 2) tools for tapps-mcp and docs-mcp, and document that using the gateway’s tool filtering keeps tool count optimal. Optionally, still implement server-side `enabled_tools` so that users **not** using the Docker gateway (e.g. direct stdio to tapps-mcp) also get a small default set.

---

## 7. References

| Source | URL | Notes |
|--------|-----|--------|
| MCP Best Practice Guide | https://mcp-best-practice.github.io/mcp-best-practice/ | Vendor-neutral production guidance |
| Model Context Protocol best practices | https://modelcontextprotocol.info/docs/best-practices/ | Architecture & implementation |
| MCP Tool Overload (DEV) | https://dev.to/nebulagg/mcp-tool-overload-why-more-tools-make-your-agent-worse-5a49 | Token cost, 95% vs 71% benchmark, strategies |
| Speakeasy – Less is more | https://www.speakeasy.com/mcp/building-servers/less-is-more | 30 / 100+ thresholds, 19-tool sweet spot, curation |
| Progressive Disclosure MCP (Kruczek) | https://matthewkruczek.ai/blog/progressive-disclosure-mcp-servers.html | 85–100× token reduction, Opus accuracy gains |
| GitHub MCP discussion #1251 | https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1251 | 80–90 issues, 30–40 in use, separate by groups |
| Southern Illinois University (arXiv 2411.15399) | (tool loadout / RAG for tools) | Curated tool sets improve performance |
| Lushbinary MCP Developer Guide 2026 | https://www.lushbinary.com/blog/mcp-model-context-protocol-developer-guide-2026/ | Adoption, transports, security |
| TappsMCP & DocsMCP tier ranking | [TOOL-TIER-RANKING.md](../TOOL-TIER-RANKING.md) | Which tools matter most for this repo |
| Docker MCP Catalog and Toolkit | https://docs.docker.com/ai/mcp-catalog-and-toolkit/ | Profiles, gateway, catalog |
| Docker MCP Profiles (enable/disable tools) | https://docs.docker.com/ai/mcp-catalog-and-toolkit/profiles/ | “Tools: You can enable or disable individual tools” |
| docker mcp profile tools | https://docs.docker.com/reference/cli/docker/mcp/profile/tools/ | CLI: --enable / --disable per server.tool |
| Docker MCP Gateway tools filtering (PR #62) | https://github.com/docker/mcp-gateway/pull/62 | tools.yaml format, gateway consumes it |
| Dynamic MCP | https://docs.docker.com/ai/mcp-catalog-and-toolkit/dynamic-mcp/ | mcp-add etc.; can disable via dynamic-tools |

---

*This document is research synthesis for planning. Implementations (e.g., tool grouping, progressive disclosure) would require design and spec work.*
