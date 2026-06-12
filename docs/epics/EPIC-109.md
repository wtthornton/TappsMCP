# Epic 109: NLT MCP Plugin — five-server split with partial enablement

<!-- docsmcp:start:metadata -->
**Status:** Shipped (master `f05c1e0`)
**Priority:** High
**Estimated LOE:** L (4–5 weeks total; phased v1.0–v1.2)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that consumers can enable only the MCP servers they need per session (1–3 of 5), reducing tool-schema token cost and tool-selection errors, while keeping zero duplicate tool registration across servers.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Ship the **NLT Tapps Quality Plugin**: five independently toggleable MCP servers (`nlt-code-quality`, `nlt-linear-issues`, `nlt-project-docs`, `nlt-release-ship`, `nlt-platform-admin`) driven by `docs/architecture/nlt-mcp-plugin-spec.yaml`. Default `tapps_init` writes the **developer** bundle only (code-quality + platform-admin), not all five.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Today tapps-mcp (38 tools) and docs-mcp (40 tools) load ~16 eager schemas (~5.8K tokens) when both are enabled. Research (2026) shows accuracy degrades above ~30 tools. Users rarely need all 78 tools at once. Splitting by user intent with partial enablement targets ~9 eager tools for daily coding.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Five `--profile nlt-*` serve modes match `nlt-mcp-plugin-spec.yaml` exactly (78 unique tools, zero overlap)
- [ ] `tapps_init` writes developer bundle (2 servers) by default; opt-in servers commented in mcp.json
- [ ] `tapps_doctor` WARNs when >3 nlt-* servers enabled or eager total >20
- [ ] Skills updated to `mcp__nlt-*__` server prefixes
- [ ] `--profile full` preserves backward-compatible monolith behavior for one release cycle
- [ ] Unit tests assert profile tool sets and disjoint union equals ALL tapps + docs tool catalogs

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 109.1 — tapps-mcp: nlt-code-quality and nlt-platform-admin profiles

**Points:** 5 | **Phase:** v1.0

Implement `TOOL_PROFILE_NLT_CODE_QUALITY` (15 tools) and `TOOL_PROFILE_NLT_PLATFORM_ADMIN` (14 tools) in `server.py`; `--profile` CLI flag; tests.

**Spec:** `docs/architecture/nlt-mcp-plugin-spec.yaml` servers `nlt-code-quality`, `nlt-platform-admin`

---

### 109.2 — tapps-platform: nlt-linear-issues and nlt-release-ship profiles

**Points:** 5 | **Phase:** v1.1

Cross-package profiles combining tapps + docs handlers for Linear and release workflows.

**Spec:** servers `nlt-linear-issues`, `nlt-release-ship`

---

### 109.3 — docs-mcp: nlt-project-docs profile

**Points:** 3 | **Phase:** v1.2

Implement `nlt-project-docs` profile (27 tools, 6 eager) in `docs_mcp/server.py`.

---

### 109.4 — tapps_init: multi-server mcp.json with developer bundle default

**Points:** 5 | **Phase:** v1.0

Write `nlt-code-quality` + `nlt-platform-admin` entries; comment opt-in servers; `--bundle developer|planning|docs|release`.

---

### 109.5 — tapps_doctor: partial-enablement WARN thresholds

**Points:** 3 | **Phase:** v1.0

WARN when >3 nlt-* servers in mcp.json or combined eager count >20; per-server tool budget rows.

---

### 109.6 — Skills and hooks: nlt-* server prefix migration

**Points:** 3 | **Phase:** v1.1

Update `linear-issue`, `linear-read`, `tapps-finish-task`, linear gate hooks to match new MCP server IDs.

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:refs -->
## Refs

- `docs/architecture/nlt-mcp-plugin-spec.yaml`
Linear: TAP-3795 (shipped `f05c1e0`)

- `docs/archive/planning/research/2026-NLT-MCP-PLUGIN-SPLIT-RESEARCH.md`
- `docs/architecture/tool-budget.md`
- Epic 79 (tool presets), TAP-1986/1987 (defer_loading)

<!-- docsmcp:end:refs -->
