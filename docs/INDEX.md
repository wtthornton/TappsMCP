# tapps-mcp — Documentation Index

**138 documents** across **9 categories**

## Overview

| Category | Count |
|---|---|
| API Reference | 32 |
| Architecture | 46 |
| Configuration | 3 |
| Getting Started | 15 |
| Guides | 9 |
| Operations | 6 |
| Other | 5 |
| Planning | 12 |
| Release | 10 |

## API Reference

- [Configuration Reference](CONFIG_REFERENCE.md) — TappsMCP is configured via `.tapps-mcp.yaml` in the project root. Settings can also be overridden with environment va... *(updated 2026-06-22)*
- [Field Report: TappsMCP + DocsMCP Full-Session Usage](FEEDBACK_2026-04-06_agentforge-cleanup-session.md) — **Date:** 2026-04-06 *(updated 2026-04-06)*
- [tapps-mcp — Documentation Index](INDEX.md) — **138 documents** across **9 categories** *(updated 2026-06-22)*
- [TappsMCP Memory Reference](MEMORY_REFERENCE.md) — Complete reference for TappsMCP **shared brain memory** — **42 actions** when accessed via CLI or the `nlt-memory` MC... *(updated 2026-06-16)*
- [Skill Authoring Conventions](SKILL_AUTHORING.md) — Reference commit: mattpocock/skills@b8be62f *(updated 2026-05-27)*
- [TAP-967: 2-Week `list_issues` Call-Count Measurement Report](TAP-967-measurement.md) — **Measurement date:** 2026-05-07 *(updated 2026-06-13)*
- [`packages.docs-mcp.src.docs_mcp`](api/docs-mcp.md) — Docs MCP: Documentation MCP server for the Tapps platform. *(updated 2026-06-22)*
- [API Reference Index](api/reference.md) — Auto-generated package-level API docs (public symbols, markdown). Regenerate with `docs_generate_api` per package or ... *(updated 2026-06-22)*
- [`packages.tapps-core.src.tapps_core`](api/tapps-core.md) — Tapps Core: Shared infrastructure library for the Tapps platform. *(updated 2026-06-22)*
- [`packages.tapps-mcp.src.tapps_mcp`](api/tapps-mcp.md) — TappsMCP: MCP server providing code quality tools. *(updated 2026-06-22)*
- [`packages.docs-mcp.src.docs_mcp`](archive/api/docs-mcp-api.md) — Docs MCP: Documentation MCP server for the Tapps platform. *(updated 2026-04-05)*
- [`packages.tapps-core.src.tapps_core`](archive/api/tapps-core-api.md) — Tapps Core: Shared infrastructure library for the Tapps platform. *(updated 2026-04-05)*
- [`packages.tapps-mcp.src.tapps_mcp.server_analysis_tools`](archive/api/tapps-mcp-analysis_tools.md) — Analysis and inspection tool handlers for TappsMCP. *(updated 2026-04-05)*
- [`packages.tapps-mcp.src.tapps_mcp.server`](archive/api/tapps-mcp-core-tools.md) — TappsMCP MCP server entry point. *(updated 2026-04-05)*
- [`packages.tapps-mcp.src.tapps_mcp.server_expert_tools`](archive/api/tapps-mcp-expert_tools.md) — Business expert management tool handlers for TappsMCP. *(updated 2026-04-05)*
- [`packages.tapps-mcp.src.tapps_mcp.server_memory_tools`](archive/api/tapps-mcp-memory_tools.md) — Memory tool handlers for TappsMCP. *(updated 2026-04-05)*
- [`packages.tapps-mcp.src.tapps_mcp.server_metrics_tools`](archive/api/tapps-mcp-metrics_tools.md) — Metrics, dashboard, feedback, and research tool handlers for TappsMCP. *(updated 2026-04-05)*
- [`packages.tapps-mcp.src.tapps_mcp.server_pipeline_tools`](archive/api/tapps-mcp-pipeline_tools.md) — Pipeline orchestration and validation tool handlers for TappsMCP. *(updated 2026-06-09)*
- [`packages.tapps-mcp.src.tapps_mcp.server_scoring_tools`](archive/api/tapps-mcp-scoring_tools.md) — Scoring and quality-gate tool handlers for TappsMCP. *(updated 2026-04-05)*
- [2026 Claude Control Files Audit & Grading Report](archive/reference/2026-CLAUDE-CONTROL-FILES-AUDIT.md) — **Project:** TappsMCP *(updated 2026-04-05)*
- [TappsPlatform Composition Guide](archive/reference/COMPOSITION_GUIDE.md) — TappsMCP (29 code quality tools) and DocsMCP (19 documentation tools) can be served as a single combined MCP server —... *(updated 2026-04-05)*
- [MCP Context (`ctx`) Pattern Reference](archive/reference/CTX_PATTERN_REFERENCE.md) — This document defines TappsMCP's standard patterns for using the MCP `Context` object *(updated 2026-04-05)*
- [MCP Client Timeouts and Long-Running Tools](archive/reference/MCP_CLIENT_TIMEOUTS.md) — TappsMCP exposes several tools that can take 10–35+ seconds to complete. Some MCP clients (e.g. Cursor, Claude Code) ... *(updated 2026-04-05)*
- [MCP Composition and Rule Hierarchy](archive/reference/MCP_COMPOSITION.md) — TappMCP works as one MCP server in a larger AI-assistant setup. This doc explains how to compose it with other MCPs a... *(updated 2026-04-05)*
- [Migration from tapps-agents to TappsMCP](archive/reference/MIGRATION_FROM_TAPPS_AGENTS.md) — If you were using **tapps-agents** (e.g. `.tapps-agents/`, experts config, knowledge files) and are moving to **Tapps... *(updated 2026-04-05)*
- [Module Map](archive/reference/MODULE_MAP.md) — **Total modules:** 316 *(updated 2026-04-05)*
- [TappsMCP Consumer Requirements](archive/reference/TAPPS_MCP_REQUIREMENTS.md) — This is the canonical checklist of what a consuming project needs for TappsMCP tools to work. Use it to verify your s... *(updated 2026-04-05)*
- [tapps_validate_changed: Loop and Timing Review](archive/reference/TAPPS_VALIDATE_CHANGED_LOOP_AND_TIMING.md) — The text **"Before ending: please run tapps_validate_changed to confirm all changed files pass quality gates."** is p... *(updated 2026-04-05)*
- [Addenda — Best Practices for Using TappsMCP](archive/reference/addenda.md) — This document supplements the main README.md and AGENTS.md with best practices, tips, and guidance for getting the mo... *(updated 2026-04-05)*
- [CI Integration Guide](archive/reference/ci-integration.md) — TappsMCP can run quality checks in CI pipelines without an interactive session. *(updated 2026-04-05)*
- [Phase B Rollup — outputSchema declarations on high-traffic tools](benchmarks/2026-05-outputschema-rollup.md) — **Status:** **CLOSED** — B1 shipped as a low-risk schema declaration, B4–B8 *(updated 2026-05-22)*
- [Operator secrets (one file, all repos)](operations/OPERATOR-SECRETS.md) — TappsMCP operator secrets are **machine-wide** — the same Context7 API key and *(updated 2026-06-15)*
## Architecture

- [TappsMCP Architecture Reference](ARCHITECTURE.md) — Detailed internal architecture for developers working on TappsMCP itself. *(updated 2026-06-22)*
- [tapps-mcp — Architecture Overview](PURPOSE.md) — **tapps-mcp** exists to give AI coding assistants **deterministic, checker-backed quality tools** instead of relying ... *(updated 2026-06-22)*
- [1. In-process AgentBrain via BrainBridge](adr/0001-in-process-agentbrain-via-brainbridge.md) — Date: 2026-05-02 *(updated 2026-05-12)*
- [2. Pin tapps-brain version floor at 3.7.2 (range: >=3.7.2, <4)](adr/0002-pin-tapps-brain-version-floor-at-372.md) — Date: 2026-05-02 *(updated 2026-05-15)*
- [4. Deterministic-tools-only contract](adr/0004-deterministic-tools-only-contract.md) — Date: 2026-05-02 *(updated 2026-05-12)*
- [5. MCP server zombie-cleanup hook on session start](adr/0005-mcp-server-zombie-cleanup-hook-on-session-start.md) — Date: 2026-05-02 *(updated 2026-06-16)*
- [6. tapps_validate_changed requires explicit file_paths](adr/0006-tapps-validate-changed-requires-explicit-file-paths.md) — Date: 2026-05-02 *(updated 2026-05-12)*
- [7. Linear writes default assignee to the agent, never the OAuth human](adr/0007-linear-writes-default-assignee-to-the-agent-never-the-oauth-human.md) — Date: 2026-05-02 *(updated 2026-05-12)*
- [8. Delete SQLite MemoryPersistence edge-case tests](adr/0008-delete-sqlite-persistence-edge-case-tests.md) — Status: Accepted *(updated 2026-05-12)*
- [9. Pin tapps-brain version floor at 3.17.0 (range: >=3.17.0, <4)](adr/0009-pin-tapps-brain-version-floor-at-3170.md) — Date: 2026-05-15 *(updated 2026-05-16)*
- [10. Pin tapps-brain version floor at 3.18.0 (range: >=3.18.0, <4)](adr/0010-pin-tapps-brain-version-floor-at-3180.md) — Date: 2026-05-16 *(updated 2026-05-18)*
- [11. Pin tapps-brain by release tag instead of commit SHA](adr/0011-pin-tapps-brain-by-tag.md) — Date: 2026-05-18 *(updated 2026-05-18)*
- [12. Select the tapps-brain capability profile per consumer role](adr/0012-brain-capability-profile-per-consumer-role.md) — Date: 2026-06-03 *(updated 2026-06-03)*
- [13. Pin tapps-brain version floor at 3.24.0 (range: >=3.24.0, <4)](adr/0013-pin-tapps-brain-version-floor-at-3240.md) — Date: 2026-06-09 *(updated 2026-06-14)*
- [14. Brain-central doc RAG (big-bang cutover)](adr/0014-brain-central-doc-rag-big-bang.md) — Date: 2026-06-13 *(updated 2026-06-14)*
- [15. Require tapps-brain docs_lookup at 3.24.0+ (ADR-0014 consumer floor)](adr/0015-require-tapps-brain-docs-lookup-at-3240.md) — Date: 2026-06-13 *(updated 2026-06-13)*
- [16. Needs-based NLT MCP taxonomy (Build / Memory / Setup)](adr/0016-needs-based-nlt-mcp-taxonomy.md) — Date: 2026-06-13 *(updated 2026-06-22)*
- [17. Function-level call graph (Python-first)](adr/0017-function-level-call-graph-python-first.md) — Date: 2026-06-15 *(updated 2026-06-15)*
- [18. Deploy all six NLT MCP servers by default (full bundle)](adr/0018-deploy-all-six-nlt-mcp-servers-by-default.md) — Date: 2026-06-16 *(updated 2026-06-16)*
- [19. Blue/green dev-monorepo MCP deploy](adr/0019-blue-green-dev-monorepo-mcp-deploy.md) — Date: 2026-06-16 *(updated 2026-06-16)*
- [20. Global uv-tool default; blue/green deploy opt-in](adr/0020-global-uv-tool-default-blue-green-opt-in.md) — Date: 2026-06-16 *(updated 2026-06-16)*
- [21. Usage-gap doc lookup: import/cache aliases + cross-channel telemetry](adr/0021-usage-gap-doc-lookup-telemetry-and-import-cache-aliases.md) — Date: 2026-06-16 *(updated 2026-06-16)*
- [22. Agent hint contract — lookup timing and validation semantics](adr/0022-agent-hint-contract-lookup-and-validation-semantics.md) — Date: 2026-06-16 *(updated 2026-06-16)*
- [ADR-0024: Shared HTTP MCP fleet for multi-window Cursor](adr/0024-shared-http-mcp-fleet.md) — Accepted (2026-06-16) *(updated 2026-06-22)*
- [Agent Gateway Refusal Envelope — Field Spec](architecture/gateway-envelope.md) — When a tapps-mcp or docs-mcp gateway fires, the tool response (or PreToolUse exit-2 body) *(updated 2026-06-02)*
- [MCP Server Eager-Tool Budget](architecture/tool-budget.md) — **Default budget:** 20 tools per MCP server *(updated 2026-06-22)*
- [PRD: Zeek Network Intelligence Service](architecture/zeek-network-intelligence-prd.md) — <!-- docsmcp:start:executive-summary --> *(updated 2026-04-05)*
- [Class Hierarchy](archive/diagrams/class-hierarchy.md) *(updated 2026-04-05)*
- [docs-mcp Dependency](archive/diagrams/docs-mcp-dependency.md) *(updated 2026-04-05)*
- [docs-mcp Module Map](archive/diagrams/docs-mcp-module_map.md) *(updated 2026-04-05)*
- [tapps-core Dependency](archive/diagrams/tapps-core-dependency.md) *(updated 2026-04-05)*
- [tapps-core Module Map](archive/diagrams/tapps-core-module_map.md) *(updated 2026-04-05)*
- [tapps-mcp Dependency](archive/diagrams/tapps-mcp-dependency.md) *(updated 2026-04-05)*
- [tapps-mcp Module Map](archive/diagrams/tapps-mcp-module_map.md) *(updated 2026-04-05)*
- [Architecture: Context7 Cache and Expert RAG](archive/reference/ARCHITECTURE_CACHE_AND_RAG.md) — This document describes how the **Context7 documentation cache** and **Expert RAG indices** work, when they are creat... *(updated 2026-04-05)*
- [Architecture Document Enhancement Plan](archive/reference/ARCHITECTURE_DOCUMENT_PLAN.md) — **Reference:** TappMCP Style Guide | HomeIQ Style Guide *(updated 2026-04-05)*
- [Architecture Report (docs_generate_architecture) — Evaluation & Recommendations](archive/reference/ARCHITECTURE_REPORT_RECOMMENDATIONS.md) — **Evaluated:** `docs/ARCHITECTURE.html` generated for TappMCP *(updated 2026-04-05)*
- [C4 — System Context](diagrams/01-c4-context.md) — Auto-generated by `docs_generate_diagram(diagram_type="c4_context", scope="project", format="mermaid", direction="LR")`. *(updated 2026-06-15)*
- [C4 — Container](diagrams/02-c4-container.md) — Auto-generated by `docs_generate_diagram(diagram_type="c4_container", scope="project", format="mermaid", direction="T... *(updated 2026-06-15)*
- [Module Map](diagrams/03-module-map.md) — Top-level project module map. Auto-generated by `docs_generate_diagram(diagram_type="module_map", scope="project", fo... *(updated 2026-06-15)*
- [Architectural Archetype — Pattern Card](diagrams/04-pattern-card.md) — Auto-classified by `docs-mcp`'s deterministic pattern classifier. tapps-mcp is detected as **microservice** with conf... *(updated 2026-05-19)*
- [C4 — Component (tapps-mcp)](diagrams/05-c4-component-tapps-mcp.md) — Internal components of the `tapps_mcp` package. Auto-generated by `docs_generate_diagram(diagram_type="c4_component",... *(updated 2026-06-15)*
- [C4 — Component (docs-mcp)](diagrams/06-c4-component-docs-mcp.md) — Internal components of the `docs_mcp` package. Auto-generated by `docs_generate_diagram(diagram_type="c4_component", ... *(updated 2026-06-15)*
- [ER — Structured Output Schemas](diagrams/07-er-output-schemas.md) — Pydantic models that define `structuredContent` for tapps-mcp tool responses. Source: packages/tapps-mcp/src/tapps_mc... *(updated 2026-05-19)*
- [Sequence — TAPPS Quality Pipeline](diagrams/08-sequence-quality-pipeline.md) — The recommended tool call order for a coding session. Auto-generated by `docs_generate_diagram(diagram_type="sequence... *(updated 2026-05-19)*
- [tapps-brain 3.22.0 — Integration Review for tapps-mcp + docs-mcp](handoff/BRAIN-322-integration-review.md) — **Date:** 2026-06-03 *(updated 2026-06-15)*
## Configuration

- [Tool-Description Eval: tool-selection accuracy A/B](benchmarks/2026-05-19-description-eval.md) — **Baseline:** `cc1d340^` (`b7f0ba4`) — **HEAD:** `HEAD` (`7e31f2c`) *(updated 2026-05-19)*
- [Tool-Description Eval: tool-selection accuracy A/B (Phase A — clean noise floor)](benchmarks/2026-05-20-description-eval.md) — **Baseline:** `cc1d340^` (`b7f0ba4`) — **HEAD:** `HEAD` (`4c11f2f`) *(updated 2026-05-21)*
- [outputSchema A/B (negative finding) — tapps_quick_check (B2)](benchmarks/outputschema-tapps_quick_check.md) — **Baseline:** `HEAD^=30149b1` (post-B1) — **HEAD:** `634ea57` (B2 candidate) *(updated 2026-05-20)*
## Getting Started

- [TappsMCP checklist (`tapps_checklist`)](CHECKLIST.md) — The checklist tracks **which MCP tools were invoked** in the current **checklist session** and compares that to **tas... *(updated 2026-06-12)*
- [GitHub Setup Guide](GITHUB_SETUP_GUIDE.md) — <!-- tapps-generated: v3.12.45 --> *(updated 2026-06-22)*
- [3. No PyPI or npm publish — global install from local checkout](adr/0003-no-pypi-or-npm-publish-global-install-from-local-checkout.md) — Date: 2026-05-02 *(updated 2026-05-12)*
- [23. Immutable MCP CLI releases — no in-place uv tool reinstall](adr/0023-immutable-mcp-cli-releases-no-inplace-uv-reinstall.md) — Date: 2026-06-16 *(updated 2026-06-16)*
- [Architecture Decision Records](adr/README.md) — Architectural decisions for tapps-mcp / tapps-core / docs-mcp / tapps-brain. Each ADR follows the MADR template (Cont... *(updated 2026-06-22)*
- [Archived Documentation](archive/README.md) — Regeneratable or supplementary docs kept out of the main tree to reduce noise for LLMs and developers. *(updated 2026-06-16)*
- [Claude Code: Full Access Setup (No Permission Prompts)](archive/reference/CLAUDE_FULL_ACCESS_SETUP.md) — This guide explains how to grant Claude Code **100% full access** so it never asks for permission when using tools (B... *(updated 2026-04-05)*
- [YouTube MCP Setup](archive/reference/MCP_YOUTUBE_SETUP.md) — The YouTube MCP server is configured for this workspace. It provides: *(updated 2026-04-05)*
- [TappsMCP: Setup and Use Summary](archive/reference/TAPPS_MCP_SETUP_AND_USE.md) — TappsMCP is an **MCP (Model Context Protocol) server** that exposes **code quality tools** to LLMs (Claude, Cursor, e... *(updated 2026-04-05)*
- [Archived smoke-test artifacts](archive/smoke/README.md) — DocsMCP generator smoke outputs moved here during the 2026-06 documentation refresh. *(updated 2026-06-15)*
- [TappsMCP Diagrams](diagrams/README.md) — Auto-generated from source by `docs-mcp`. All diagrams render natively on GitHub. *(updated 2026-06-22)*
- [Consumer repo: verify tapps-mcp ↔ tapps-brain wiring](operations/CONSUMER-REPO-BRAIN-WIRING.md) — Operator and agent checklist for wiring a **new LLM coding repo** to the shared *(updated 2026-06-15)*
- [tapps-brain: Local and Multi-Project Setup](operations/TAPPS-BRAIN-LOCAL-SETUP.md) — This guide explains how to connect tapps-mcp to tapps-brain for persistent memory. *(updated 2026-06-09)*
- [TappsMCP Epics](planning/epics/README.md) — Epics live in **Linear**, not in this repository. Per `.claude/rules/linear-standards.md`, create and update epics th... *(updated 2026-06-16)*
- [Tutorials](tutorials/README.md) — Six short, copy-paste runnable walkthroughs for the most-asked starter tasks. Each ends with explicit verification st... *(updated 2026-06-15)*
## Guides

- [Call graph tools (consumer guide)](CALL_GRAPH.md) — TappsMCP v3.12.31+ ships **function-level call graph** tools for Python projects (Epic 114, ADR-0017). Use them befor... *(updated 2026-06-22)*
- [Getting Started with tapps-mcp](ONBOARDING.md) — - **Python 3.12+** *(updated 2026-06-22)*
- [TappsMCP Design System Style Guide](STYLE_GUIDE.md) — **Derived from:** the HomeIQ Design System Style Guide (sibling repo, see workspace). *(updated 2026-05-12)*
- [Tutorial: Add a new MCP tool to tapps-mcp](tutorials/01-add-an-mcp-tool.md) — **Time:** ~15 minutes. **Outcome:** A working `tapps_hello` MCP tool callable from Claude Code, registered in the che... *(updated 2026-05-18)*
- [Tutorial: Run the quality pipeline against a fresh Python project](tutorials/02-quality-pipeline-walkthrough.md) — **Time:** ~10 minutes. **Outcome:** A new Python project bootstrapped with TappsMCP scaffolding, a deliberate quality... *(updated 2026-05-02)*
- [Tutorial: Wire tapps-brain into a Claude Code session](tutorials/03-wire-tapps-brain.md) — **Time:** ~20 minutes (10 of it is the brain HTTP service warming up the first time). **Outcome:** A Claude Code sess... *(updated 2026-06-22)*
- [Tutorial: NLT MCP session modes](tutorials/04-nlt-mcp-session-modes.md) — **Time:** ~10 minutes. **Outcome:** You enable the right 1–3 MCP servers for your task, verify tools appear in Cursor... *(updated 2026-06-15)*
- [Tutorial: Documentation refresh workflow](tutorials/05-docs-refresh-workflow.md) — **Time:** ~2 hours (full pass). **Outcome:** Tier-1 docs accurate, API/diagrams regenerated, link graph clean, CI doc... *(updated 2026-06-15)*
- [Tutorial: Your first memory save and recall](tutorials/06-first-memory-session.md) — **Time:** ~10 min (after tutorial 03 brain wiring). **Outcome:** Save a project decision, recall it in a new chat, an... *(updated 2026-06-15)*
## Operations

- [TappsMCP: Docker Deployment](DOCKER_DEPLOYMENT.md) — Run TappsMCP as a **local Docker MCP server** using Streamable HTTP. The server listens on port **8000** and exposes ... *(updated 2026-06-09)*
- [Docker Image Distribution](DOCKER_MCP_TOOLKIT.md) — TappsMCP and DocsMCP are distributed as Docker images for external distribution, *(updated 2026-05-12)*
- [Prompt: smoke-prompt](archive/smoke/smoke-prompt.md) — <!-- docsmcp:start:metadata --> *(updated 2026-06-15)*
- [Agent Teams Feature Gate Audit (TAP-2021)](features/agent-teams.md) — Audit of every `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` gate in tapps-mcp. *(updated 2026-05-27)*
- [Agent-facing Linear issues — conventions](linear/AGENT_ISSUES.md) — Durable policy for how Linear issues are written, labeled, and nested in the *(updated 2026-05-02)*
- [Brain-central doc RAG — fleet cutover runbook](operations/brain-doc-rag-cutover-runbook.md) — Maintenance window (~30 minutes) for ADR-0014 big-bang cutover. *(updated 2026-06-22)*
## Other

- [Troubleshooting](TROUBLESHOOTING.md) — **Problem:** When the MCP host (Claude Code, Cursor, VS Code) restarts or reloads, the MCP server connection is lost.... *(updated 2026-06-17)*
- [1. Smoke](archive/smoke/0001-smoke.md) — Date: 2026-06-14 *(updated 2026-06-14)*
- [2. Smoke](archive/smoke/0002-smoke.md) — Date: 2026-06-14 *(updated 2026-06-14)*
- [3. Smoke](archive/smoke/0003-smoke.md) — Date: 2026-06-14 *(updated 2026-06-15)*
- [Compaction Resilience Spec](specs/compaction-resilience.md) — **Status:** Active *(updated 2026-06-16)*
## Planning

- [TappsMCP Platform — Backlog Plan (Obsolete — see Linear)](TAPPS_BACKLOG_PLAN.md) — This file is no longer maintained. The 49-issue plan generated on 2026-04-21 *(updated 2026-05-05)*
- [PRD: Smoke](archive/smoke/PRD-smoke.md) — <!-- docsmcp:start:executive-summary --> *(updated 2026-06-15)*
- [Epic 111: Dependency Upgrade: Latest Stable Quality & Runtime Libraries](epics/EPIC-111.md) — <!-- docsmcp:start:metadata --> *(updated 2026-06-15)*
- [Epic 112: Quality Tool Cross-Repo UX & Audit Hardening](epics/EPIC-112.md) — <!-- docsmcp:start:metadata --> *(updated 2026-06-22)*
- [server_analysis_tools.py: honor project_root in MCP handlers](epics/stories/STORY-112.1.md) — server_analysis_tools.py: honor project_root in MCP handlers *(updated 2026-06-15)*
- [validate_changed.py: cross-repo explicit file_paths](epics/stories/STORY-112.2.md) — validate_changed.py: cross-repo explicit file_paths *(updated 2026-06-15)*
- [audit_chunker.py: auto-detect monorepo graph_root](epics/stories/STORY-112.3.md) — audit_chunker.py: auto-detect monorepo graph_root *(updated 2026-06-15)*
- [pip_audit.py: scope scan to target project](epics/stories/STORY-112.4.md) — pip_audit.py: scope scan to target project *(updated 2026-06-15)*
- [doctor.py: NLT tool-budget default bundle](epics/stories/STORY-112.5.md) — doctor.py: NLT tool-budget default bundle *(updated 2026-06-15)*
- [validate_changed_diagnostics.py: close EPIC-103 gaps](epics/stories/STORY-112.6.md) — validate_changed_diagnostics.py: close EPIC-103 gaps *(updated 2026-06-15)*
- [Handoff → tapps-brain: capabilities needed to unblock the "migrate local state into brain" epic (TAP-1996)](handoff/BRAIN-wave2-capabilities.md) — **Status:** requested by tapps-mcp 2026-06-01; revised 2026-06-09 after brain-side review. *(updated 2026-06-09)*
- [Dogfood Retest Checklist (EPIC-113 / TAP-4026)](operations/DOGFOOD-RETEST.md) — Run this checklist on the **tapps-mcp dev repo** after CallMcpTool unwrap (TAP-4017), rolling-stats filter (TAP-4025)... *(updated 2026-06-15)*
## Release

- [Init and Upgrade — Feature List](INIT_AND_UPGRADE_FEATURE_LIST.md) — This document lists what each init-related process does. The codebase has **two init flows** plus **upgrade commands*... *(updated 2026-06-09)*
- [TappsMCP Platform — Sprint Board](SPRINT_BOARD.md) — **Project:** TappsMCP Platform *(updated 2026-06-09)*
- [tapps-brain v2.1.0 — Tag Required](TAPPS_BRAIN_V2.1_TAG.md) — **Date:** 2026-04-07 *(updated 2026-04-07)*
- [Generic upgrade prompt — pull latest tapps-mcp into a consuming project](UPGRADE-PROMPT.md) — Open Claude Code (or Cursor) **inside the consuming project's repo** and paste the prompt below. It works whether or ... *(updated 2026-05-28)*
- [Upgrading TappsMCP — Guide for Consuming Projects](UPGRADE_FOR_CONSUMERS.md) — When you **install or upgrade** TappsMCP in a project that uses it for quality checks, doc lookup, and experts, you m... *(updated 2026-06-16)*
- [Handoff — tapps-mcp consumer migration (brain EPIC-074/075 shipped)](handoff/TAPPS-MCP-CONSUMER-MIGRATION-1997-1998.md) — Paste this into a tapps-mcp session (or a Linear comment on TAP-1997 / TAP-1998). *(updated 2026-06-09)*
- [Brain v3.18.0 Kwarg Audit — TAP-1977](migrations/brain-v3.18-kwarg-audit.md) — **Date:** 2026-05-23 *(updated 2026-06-13)*
- [tapps_memory Deprecation Migration Table (TAP-1991)](migrations/tapps-memory-deprecation.md) — **Status:** REMOVED — v3.12.0 (TAP-1994, Phase 3 complete 2026-Q2). *(updated 2026-06-01)*
- [Migration: `<old_tool_name>` → `<new_tool_name>`](migrations/template.md) — **Removed in**: vX.Y.Z *(updated 2026-05-23)*
- [Fleet maintenance — multi-repo TAPPS upgrade and audit](operations/FLEET-MAINTENANCE.md) — Runbook for upgrading **tapps-mcp**, **AgentForge**, **NLTlabsPE**, and **NewCompanyIdeas** together on one machine (... *(updated 2026-06-17)*
