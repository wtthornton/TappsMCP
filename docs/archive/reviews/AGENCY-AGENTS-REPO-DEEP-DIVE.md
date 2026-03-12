# Deep Dive: msitarzewski/agency-agents

**Repo:** https://github.com/msitarzewski/agency-agents  
**License:** MIT  
**Stars:** 24.3k+ (as of 2025)

---

## 1. What It Is

**The Agency** is a **collection of ~80 specialized AI agent personalities** stored as Markdown files. Each “agent” is a detailed prompt/instruction set with:

- **Identity & personality** (role, voice, memory)
- **Core mission & deliverables** (concrete outputs)
- **Critical rules** (domain-specific constraints)
- **Technical deliverables** (code samples, templates)
- **Workflow process** (step-by-step)
- **Success metrics** (measurable outcomes)

Agents are **tool-agnostic**: the same Markdown is converted for Claude Code, GitHub Copilot, Cursor, Aider, Windsurf, Antigravity, Gemini CLI, and OpenCode. No runtime; consumption is via copy/install into each tool’s config.

---

## 2. Repository Layout

| Path | Purpose |
|------|--------|
| `engineering/` | 8 agents (Frontend, Backend, Mobile, AI, DevOps, Rapid Prototyper, Senior Dev, Security) |
| `design/` | 7 (UI, UX Researcher, UX Architect, Brand Guardian, Visual Storyteller, Whimsy Injector, Image Prompt Engineer) |
| `marketing/` | 11 (Growth, Content, Twitter, TikTok, Instagram, Reddit, ASO, Social, Xiaohongshu, WeChat OA, Zhihu) |
| `product/` | 3 (Sprint Prioritizer, Trend Researcher, Feedback Synthesizer) |
| `project-management/` | 5 (Studio Producer, Project Shepherd, Studio Ops, Experiment Tracker, Senior PM) |
| `testing/` | 8 (Evidence Collector, Reality Checker, Test Results Analyzer, Performance Benchmarker, API Tester, Tool Evaluator, Workflow Optimizer, Accessibility Auditor) |
| `support/` | 6 (Support Responder, Analytics, Finance, Infrastructure, Legal Compliance, Executive Summary) |
| `spatial-computing/` | 6 (XR Interface, macOS Spatial/Metal, XR Immersive, XR Cockpit, visionOS, Terminal Integration) |
| `specialized/` | 8 (Agents Orchestrator, Data Analytics, LSP/Index, Sales Data Extraction, Data Consolidation, Report Distribution, Identity & Trust, Identity Graph) |
| `game-development/` | Cross-engine + Unity + Unreal + Godot + Roblox agents |
| `strategy/` | (present in tree) |
| `integrations/` | **Generated** output per tool (Cursor `.mdc`, Aider `CONVENTIONS.md`, etc.) |
| `scripts/` | `convert.sh` (source → integrations), `install.sh` (integrations → user config) |
| `examples/` | Multi-agent workflow examples (e.g. Nexus Spatial Discovery) |

Source of truth: **category dirs** (e.g. `engineering/*.md`). `integrations/` is produced by `convert.sh` and should not be edited by hand.

---

## 3. Agent File Format

### 3.1 Frontmatter (YAML)

```yaml
---
name: Frontend Developer
description: Expert frontend developer specializing in modern web technologies...
color: cyan
---
```

- **name**: Display name (used for slugs and references).
- **description**: One-line summary; used in tool-specific outputs (e.g. Cursor rule description).
- **color**: Thematic (e.g. `red` for Reality Checker); used in docs/UI where supported.

### 3.2 Body Structure (from CONTRIBUTING.md)

1. **Your Identity & Memory** — Role, personality, memory, experience.
2. **Your Core Mission** — 3–5 responsibility bullets; “default requirement” (e.g. always accessibility).
3. **Critical Rules You Must Follow** — Domain rules and constraints.
4. **Technical Deliverables** — Code samples, templates, frameworks (real, runnable).
5. **Workflow Process** — Phases (e.g. Setup → Development → Optimization → QA).
6. **Communication Style** — Tone, example phrases.
7. **Learning & Memory** — What the agent “remembers” and improves on.
8. **Success Metrics** — Quantitative/qualitative (e.g. “Lighthouse > 90”, “load < 3s on 3G”).
9. **Advanced Capabilities** (optional) — Deeper techniques.

Design principles (from CONTRIBUTING): **strong personality**, **clear deliverables**, **success metrics**, **proven workflows**, **learning/memory**. Avoid generic “helpful assistant” and vague “I will help with…”.

---

## 4. Example Agent: Frontend Developer (snippet)

- **Identity**: Modern web/UI specialist; detail-oriented, performance- and user-centric.
- **Mission**: Editor integration (WebSocket/RPC, &lt;150ms nav), modern web apps (React/Vue/Angular, a11y by default), performance (Core Web Vitals, PWAs), code quality (tests, TypeScript, CI/CD).
- **Rules**: Performance-first (Core Web Vitals from day one), WCAG 2.1 AA, ARIA, keyboard/screen reader.
- **Deliverables**: e.g. virtualized React table with `@tanstack/react-virtual`, memoization, ARIA; plus a markdown deliverable template (UI stack, performance, accessibility).
- **Workflow**: Setup → Component development → Performance optimization → Testing/QA.
- **Success**: Load &lt;3s on 3G, Lighthouse &gt;90, cross-browser, high reusability, zero prod console errors.

---

## 5. Example Agent: Reality Checker (testing)

- **Identity**: “Stops fantasy approvals”; evidence-based certification; default “NEEDS WORK”.
- **Personality**: Skeptical, evidence-obsessed; remembers premature approvals and integration failures.
- **Process**: Mandatory “reality check” commands (list views, grep for claimed features, run Playwright screenshot capture, inspect `test-results.json`); QA cross-validation; E2E validation with before/after screenshots.
- **Automatic fail**: “Zero issues” claims, perfect scores without evidence, “luxury” claims for basic UIs, “production ready” without proof; missing or inconsistent screenshots/evidence.
- **Report template**: Reality check validation, visual documentation, integration results, issue list, **realistic** quality grade (C+ to B+), deployment readiness (default NEEDS WORK), required fixes and re-assessment.

Contrast: Frontend Developer is **how to build**; Reality Checker is **how to judge** and resist over-claiming.

---

## 6. Conversion and Install Pipeline

### 6.1 `scripts/convert.sh`

- **Input**: All agent `.md` files under category dirs (design, engineering, game-development, marketing, etc.).
- **Output**: Writes under `integrations/<tool>/`; does **not** touch user home or project dirs.
- **Options**: `--tool antigravity|gemini-cli|opencode|cursor|aider|windsurf|all`, `--out`, `--help`.

Mechanics:

- **Frontmatter**: `get_field(name|description, file)`, `get_body(file)` (strip leading `---` block).
- **Slug**: `slugify(name)` → lowercase kebab (e.g. “Frontend Developer” → `frontend-developer`).

Per-tool behavior:

- **Antigravity**: One dir per agent `integrations/antigravity/agency-<slug>/SKILL.md` (name, description, body).
- **Cursor**: One `.mdc` per agent in `integrations/cursor/` (frontmatter + body; Cursor rule format).
- **Aider**: Single concatenated `integrations/aider/CONVENTIONS.md` (header + per-agent name/description/body).
- **Windsurf**: Single `integrations/windsurf/.windsurfrules` (same idea as Aider).
- **Gemini CLI**: Skills + `gemini-extension.json` in `integrations/gemini-cli/`.
- **OpenCode**: One `.md` per agent in `integrations/opencode/agent/`.

So: **one source agent → many target formats** via one script.

### 6.2 `scripts/install.sh`

- **Input**: Pre-built `integrations/` (run `convert.sh` first).
- **Action**: Copies from `integrations/<tool>/` to the right user/project path for each tool.
- **Options**: `--tool <name>`, `--interactive` (default in TTY), `--no-interactive`.
- **Tools**: claude-code, copilot, antigravity, gemini-cli, opencode, **cursor**, aider, windsurf, all.

Cursor-specific (from `integrations/cursor/README.md`):

- Install: from project root, `scripts/install.sh --tool cursor` → creates `.cursor/rules/*.mdc`.
- Activate: mention in prompt, e.g. `@frontend-developer Review this React component.`
- Always-on: set in frontmatter `alwaysApply: true` (and optionally `globs` for scope).

Platform support: Linux, macOS (bash 3.2+), Windows via Git Bash / WSL.

---

## 7. Multi-Tool Support (summary)

| Tool | Format | Install target |
|------|--------|----------------|
| Claude Code | Native `.md` | `~/.claude/agents/` |
| GitHub Copilot | Native `.md` | `~/.github/agents/` |
| Cursor | `.mdc` rules | `.cursor/rules/` (project) |
| Aider | Single `CONVENTIONS.md` | Project root |
| Windsurf | Single `.windsurfrules` | Project root |
| Antigravity (Gemini) | `SKILL.md` per agent | `~/.gemini/antigravity/skills/agency-<slug>/` |
| Gemini CLI | Extension + skills | `~/.gemini/extensions/agency-agents/` |
| OpenCode | `.md` per agent | `.opencode/agent/` or global config |

Regeneration: after adding/editing agents, run `./scripts/convert.sh` (or `--tool cursor` etc.), then re-run `install.sh` as needed.

---

## 8. Examples: Multi-Agent Use

**examples/README.md** and **nexus-spatial-discovery.md** show “full agency” usage:

- **Nexus Spatial Discovery**: One product-discovery run with **8 agents in parallel** (Product Trend Researcher, Backend Architect, Brand Guardian, Growth Hacker, Support Responder, UX Researcher, Project Shepherd, XR Interface Architect). Outputs: market validation, 8-service architecture + SQL schema, brand strategy, GTM, support blueprint, UX personas/journeys, 35-week plan with 65 sprint tickets, spatial UI spec. Single session, no explicit coordinator agent.
- Other examples: `workflow-landing-page.md`, `workflow-startup-mvp.md`, `workflow-with-memory.md`.

Takeaway: agents are written so they can be **invoked in parallel** on a shared objective; the definitions plus user orchestration produce coherent, cross-referencing plans.

---

## 9. Contributing (from CONTRIBUTING.md)

- **New agent**: Pick category (or propose one), follow the agent template, add 2–3 code/template examples and success metrics, test in real scenarios, open PR (“Add [Name] - [Category]”).
- **Improvements**: Real examples, modern code, updated workflows, success metrics, docs.
- **Quality bar**: Narrow specialization, distinct voice, concrete deliverables, measurable metrics, step-by-step workflow, real-world testing. No generic “helpful” persona or untested theory.

Reference agents: Frontend Developer (structure), Reddit Community Builder (personality), Whimsy Injector (creative specialist).

---

## 10. Comparison to TappMCP (this repo)

| Dimension | agency-agents | TappMCP |
|-----------|----------------|---------|
| **Artifact** | Markdown agent definitions (prompts/personas) | MCP server + tools (scoring, security, docs, experts, memory) |
| **Execution** | No server; copy into each host (Cursor, Aider, etc.) | Running MCP server; tools called by IDE/agent |
| **Cursor** | One `.mdc` per agency agent (persona/rule) | Pipeline + Python quality + expert consultation `.mdc` rules; rules reference MCP tools |
| **Determinism** | N/A (prompt-driven behavior) | Explicit (e.g. no LLM in tool chain; same input → same output) |
| **Scope** | Broad “agency” (engineering, design, marketing, product, PM, testing, support, spatial, game, specialized) | Code quality, security, docs lookup, experts, memory, validation, checklists |
| **Integration** | convert.sh → integrations/ → install.sh → tool config | MCP config (e.g. `.cursor/mcp.json`); `tapps_session_start`, `tapps_quick_check`, etc. |

agency-agents is **persona/workflow library + multi-tool packaging**. TappMCP is **deterministic quality tooling** consumed via MCP. They can be used together: e.g. a “Reality Checker” or “Frontend Developer” rule in Cursor plus TappMCP for scoring, gates, and validation.

---

## 11. References

- Repo: https://github.com/msitarzewski/agency-agents  
- README: in-repo and raw [README](https://raw.githubusercontent.com/msitarzewski/agency-agents/main/README.md)  
- CONTRIBUTING: [CONTRIBUTING.md](https://raw.githubusercontent.com/msitarzewski/agency-agents/main/CONTRIBUTING.md)  
- Cursor integration: [integrations/cursor/README.md](https://raw.githubusercontent.com/msitarzewski/agency-agents/main/integrations/cursor/README.md)  
- Examples: [examples/README.md](https://raw.githubusercontent.com/msitarzewski/agency-agents/main/examples/README.md)  
- Convert script: [scripts/convert.sh](https://raw.githubusercontent.com/msitarzewski/agency-agents/main/scripts/convert.sh)  
- Install script: [scripts/install.sh](https://raw.githubusercontent.com/msitarzewski/agency-agents/main/scripts/install.sh)
