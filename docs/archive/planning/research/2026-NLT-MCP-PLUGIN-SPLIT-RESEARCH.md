# 2026 Research: NLT Multi-MCP Plugin Split

**Date:** 2026-06-12  
**Purpose:** Confirm the five-server `nlt-*` plugin design with external 2026 best practices and document the zero-duplication tool matrix.  
**Spec:** [docs/architecture/nlt-mcp-plugin-spec.yaml](../../../architecture/nlt-mcp-plugin-spec.yaml)

---

## Executive summary

Splitting the current **78-tool / 2-monolith** surface into **five focused MCP servers** (`nlt-code-quality`, `nlt-linear-issues`, `nlt-project-docs`, `nlt-release-ship`, `nlt-platform-admin`) is **aligned with 2026 industry guidance**.

### Load-bearing assumption

**Users do not enable all five servers at once.** The split only wins when 1–3 servers are active per session. Token math, doctor budgets, and research citations assume **partial enablement**. Enabling everything is an explicit escape hatch (power users / diagnostics), not the default or recommended path.

Splitting the monolith without this discipline **recreates the monolith** (~78 tools, ~29 eager schemas, tool-selection degradation) and should trigger `tapps_doctor` WARN.

The research reinforces:

1. **Single-responsibility servers** — not mega-servers mixing unrelated domains.
2. **~5–20 tools per server** — stay under the ~30-tool accuracy cliff **per active session**, not per catalog.
3. **Enable/disable by task** — users turn off whole servers they don't need (the whole point of the plugin).
4. **Zero duplicate tool registration** — duplicate schemas waste tokens and confuse routing; cross-server work belongs in **skills** and **in-process orchestration**.
5. **Skills + MCP together** — MCP for typed tools; skills for multi-server choreography.

---

## 1. External sources (2026)

| Source | Key finding | Impact on NLT design |
|--------|-------------|----------------------|
| [MCP Best Practice Guide](https://mcp-best-practice.github.io/mcp-best-practice/) | Single responsibility; good-citizen clients don't load all tools | ✅ Five intent-based servers |
| [Phil Schmid – MCP best practices](https://www.philschmid.de/mcp-best-practices) | **5–15 tools per server**; one job; split by persona; `{service}_{action}` naming | ✅ Servers are 7–27 tools (15–9 eager on daily drivers); largest is docs at 27 with defer |
| [Anthropic – Advanced tool use (Nov 2025)](https://www.anthropic.com/engineering/advanced-tool-use) | Tool Search + `defer_loading`; keep **3–5 critical tools eager**; multi-server setups benefit from per-server defer | ✅ Matches TAP-1986/1987 eager split |
| [Jacar – MCP guide 2026](https://jacar.es/en/mcp-guia-completa-2026/) | Norm is **~6 MCP servers** per agent; host prefixes (`mcp__server__tool`) prevent collisions | ✅ `nlt-*` server IDs; keep distinct tool names |
| [DEV – MCP Tool Overload](https://dev.to/nebulagg/mcp-tool-overload-why-more-tools-make-your-agent-worse-5a49) | 40 tools ≈ 43K tokens; 95% vs 71% tool-selection accuracy (minimal vs full GitHub MCP) | ✅ Default bundle ≈ 30 tools, not 78 |
| [Speakeasy – Less is more](https://www.speakeasy.com/mcp/building-servers/less-is-more) | ~30 tools = degradation threshold; ~19 sweet spot (small models) | ✅ Each server ≤16 tools |
| [GitHub MCP discussion #1251](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1251) | 80–90 tools = issues; **30–40 OK**; **separate MCPs by group** | ✅ Primary motivation for split |
| [MCPcat – MCP server best practices](https://mcpcat.io/blog/mcp-server-best-practices/) | Namespaces → dynamic loading → **multiple servers at scale**; microservice pattern | ✅ Phase 2: profiles; Phase 3: optional gateway |
| [Docker MCP Toolkit](https://docs.docker.com/ai/mcp-catalog-and-toolkit/) | Profiles + per-tool filtering via gateway | ✅ Existing `docker-mcp/profiles/` maps to nlt bundles |
| Internal [2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md](2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md) | Combined 51+ tools above safe range; curate by task | ✅ Validated March 2026; still current |

### Anthropic `defer_loading` caveat

`defer_loading` is an **API/client feature**, not MCP protocol ([Medium analysis](https://medium.com/@danielschwartzer/i-built-a-remote-mcp-server-heres-what-i-found-2725c77171d5)). Claude Code's `.claude.json` `defer_loading` per server may be [silently ignored](https://github.com/anthropics/claude-code/issues/26844) as of early 2026.

**Implication:** Do **not** rely on defer alone for Cursor/VS Code hosts. **Physically splitting servers** (disable `nlt-project-docs` during coding) is the portable fix that works everywhere.

---

## 2. Recommendation validation

| Design decision | Research verdict |
|-----------------|------------------|
| **5 × `nlt-*` servers** | ✅ Matches "split by product area" (MCPcat) and "~5 servers" community norm (Jacar, qdrddr) |
| **Zero tool duplication** | ✅ Gateways (mcprouter) prefix tools; duplicate registration = duplicate schemas + collision risk |
| **No duplicate `session_start`** | ✅ Use domain bootstraps (`tapps_session_start` vs `docs_session_start`) |
| **Release tools separate** | ✅ Release is situational (Tier 3); keeps daily coding server lean |
| **Linear as cross-package server** | ✅ Skills already orchestrate docs + tapps linear tools; one server matches user mental model |
| **Keep `tapps_*` / `docs_*` tool names** | ✅ Phil Schmid: disambiguate via server prefix, not rename tools |
| **Default bundle: quality + admin** | ✅ ~30 tools total; under 30-tool threshold |
| **Skills for cross-server steps** | ✅ Phil Schmid: "Skills teach when/how to combine tools" |
| **Monolith `--profile full` legacy** | ✅ Migration pattern; Docker gateway uses same approach |

### What we rejected (research-backed)

| Alternative | Why not |
|-------------|---------|
| Duplicate bridge tools on 2+ servers | +~990 tokens (3 dupes) to +~3K (generous); confuses tool selection |
| Single combined server + presets only | Doesn't reduce tokens on hosts without Tool Search |
| 6th bootstrap-only server | Wastes ~1.2K tokens × N; domain session tools suffice |
| Merge release into project-docs (4 servers) | 36 tools on one server; re-approaches monolith |

---

## 3. Zero-duplication matrix summary

| Server ID | Tools | Eager | Default on |
|-----------|------:|------:|------------|
| `nlt-code-quality` | 15 | 9 | yes |
| `nlt-linear-issues` | 15 | 7 | no |
| `nlt-project-docs` | 27 | 6 | no |
| `nlt-release-ship` | 7 | 5 | no |
| `nlt-platform-admin` | 14 | 2 | yes |
| **Total** | **78 unique** | **29** | **~30 in default bundle** |

**Duplicate registrations: 0**

Previously considered bridge duplicates (removed in zero-dup spec):

| Tool | Was on | Now only on | Cross-server handling |
|------|--------|-------------|------------------------|
| `docs_git_summary` | project-docs + release | project-docs | `tapps_release_update` imports docs in-process |
| `tapps_dependency_scan` | quality + release | release | Pre-ship workflow only |
| `tapps_linear_snapshot_invalidate` | linear + release | linear | `linear-release-update` skill optional step |

---

## 4. Token budget (partial enablement — design target)

Budgets below assume **not all servers selected**. This is the expected case.

| Session type | Servers enabled | Eager schemas (est.) | vs monolith today |
|--------------|-----------------|----------------------|-------------------|
| **Daily coding (target)** | `nlt-code-quality` only | ~9 (~3K) | **Better** (~5.8K → ~3K) |
| **Developer default (init)** | code-quality + admin | ~11 (~3.7K) | Similar; disable admin post-bootstrap → ~3K |
| **Planning / Linear** | code-quality + linear-issues | ~16 (~5.3K) | Similar eager count, clearer scope |
| **Docs audit** | project-docs only | ~6 (~2K) | Much lighter than enabling full docs-mcp |
| **Release day** | release-ship + project-docs | ~11 (~3.7K) | Task-scoped |
| **Anti-pattern: all five** | all nlt-* | ~29 (~10K) | **Worse** — do not default to this |
| Monolith reference | tapps-mcp + docs-mcp (both on) | ~16 (~5.8K) | Baseline many users run today |

**Takeaway:** The plugin saves tokens when users run **one primary server** (coding OR docs OR linear). Savings disappear if everything stays enabled — same as today's problem with both monoliths always on.

---

## 5. Implementation phases (unchanged LOE)

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 1. Profile wiring | 1–1.5 wks | `--profile nlt-*` frozensets from YAML spec |
| 2. Plugin packaging | 1–1.5 wks | `server.json` × 5, Docker profiles, npm wrappers |
| 3. Skills/hooks/doctor | 1 wk | Server-prefixed `allowed-tools`; multi-probe doctor |
| 4. Migration | 3–5 days | `tapps_init --bundle developer\|planning\|full` |
| **Total** | **~4–5 wks** | Real installable plugin |

---

## 6. References

- [nlt-mcp-plugin-spec.yaml](../../../architecture/nlt-mcp-plugin-spec.yaml) — canonical tool matrix
- [tool-budget.md](../../../architecture/tool-budget.md) — eager/deferred budget
- [TOOL-TIER-RANKING.md](../../TOOL-TIER-RANKING.md) — tier assignments
- [TOOL-SUBSETS-AND-DOCKER-FILTERING.md](../../TOOL-SUBSETS-AND-DOCKER-FILTERING.md) — Docker gateway
- [2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md](2026-MCP-TOOLS-BEST-PRACTICES-OPTIMAL-COUNT.md) — internal research (Mar 2026)
