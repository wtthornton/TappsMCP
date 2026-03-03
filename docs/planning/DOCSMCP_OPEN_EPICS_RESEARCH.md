# Research: Are All Open DocsMCP Epics Really Needed?

**Date:** 2026-03-02  
**Scope:** Epic 9 (Project Scan & Workflow), Epic 10 (Distribution & CLI), Epic 12 (Multi-Language)  
**Conclusion:** Much of the “open” work is **already done**, **low-value**, or **optional**. Only a small subset is strictly needed for a clear MVP.

**Recommendations executed (2026-03-02):** Epic 9 closed complete; Epic 10 scope reduced (PyPI required, rest optional/deferred); Epic 12 confirmed post-MVP. Updated: `docs/planning/epics/README.md`, `docs/planning/EPIC_PRIORITIZATION.md`, `docs/planning/DOCSMCP_PRD.md`.

---

## 1. Epic 9: Project Scan & Workflow

### What the PRD Says Is Open

- 9.1 `docs_project_scan` comprehensive audit  
- 9.2 MCP resources (status, config, **templates**, coverage)  
- 9.3 MCP prompts (workflow overview, task-specific)  
- 9.4 `docs_config` tool  
- 9.5 AGENTS.md generation for consuming projects  

### What Actually Exists (Codebase)

| Item | Status |
|------|--------|
| 9.1 `docs_project_scan` | **Implemented** — tool exists and is used |
| 9.2 Resources | **Implemented** — `docs://status`, `docs://config`, `docs://coverage` in `server_resources.py`. **Missing:** `docs://templates/{type}` only |
| 9.3 Prompts | **Implemented** — `docs_workflow_overview`, `docs_workflow(task_type=...)` |
| 9.4 `docs_config` | **Implemented** |
| 9.5 AGENTS.md generation | **Not implemented** — no tool to generate AGENTS.md for consuming projects |

### Research: Are MCP Resources and Prompts Worth More Work?

- **MCP spec:** Resources and prompts are first-class; resources are “application-controlled” (user chooses what to load), tools are “model-controlled” (LLM decides when to call).
- **Real-world usage:**  
  - Tools dominate; clients prioritize tools. “5 resources to 12 tools per implementation” is typical; resources are described as “overlooked” and “underutilized.”  
  - **Claude Desktop:** Lists resources but often **does not call `resources/read`** when answering; may do web search instead.  
  - **Claude Code:** Resources from MCP servers are **not consumable** in practice (reported P0 issues).  
  - **Cursor / other hosts:** Support for resources is inconsistent; many implement `resources/list` but not full `resources/read` or subscriptions.
- **Implication for DocsMCP:** The resources and prompts you already have (status, config, coverage, workflow) are **low impact** today because host support is weak. Adding **`docs://templates/{type}`** has minimal justification: (1) hosts don’t reliably use resources, (2) template discovery can be done via a **tool** (e.g. `docs_list_templates`) later if ever needed.

**Verdict Epic 9:**

- **Not needed for MVP:**  
  - `docs://templates/{type}` resource  
  - AGENTS.md generation for consuming projects (nice-to-have; no strong demand)
- **Already done:** Project scan, resources (status/config/coverage), prompts, `docs_config`.  
- **Recommendation:** **Close Epic 9 as complete.** Optionally add a short PRD note: “Epic 9: MCP resources and prompts implemented; `docs://templates` and AGENTS.md generation deferred (low ROI / host support).”

---

## 2. Epic 10: Distribution & CLI

### What the PRD Says Is Open

- 10.1 PyPI packaging and publishing  
- 10.2 CLI: `docsmcp serve`, `generate`, `check`, `doctor`  
- 10.3 Docker image  
- 10.4 npm wrapper (`npx docsmcp`)  
- 10.5 CI workflow generator for documentation checks  

### What Actually Exists

| Item | Status |
|------|--------|
| 10.1 PyPI for docs-mcp | **Not in current publish flow** — `.github/workflows/publish.yml` builds/publishes from repo root and runs `tapps-mcp --version`; only **tapps-mcp** is published. docs-mcp is not built or published to PyPI. |
| 10.2 CLI | **Partly done:** `docsmcp serve`, `doctor`, `scan`, `version` exist. `generate` is a **stub** that tells users to use MCP tools. No dedicated `check` command (validation is via MCP tools). |
| 10.3 Docker | **Done** — `packages/docs-mcp/Dockerfile` exists (multi-stage, non-root user, `docsmcp serve`). Not published to a registry in CI. |
| 10.4 npm wrapper | **Not implemented** |
| 10.5 CI workflow generator | **Not implemented** |

### Research: What Distribution Is Really Needed?

- **PyPI:**  
  - DocsMCP’s own INSTALLATION.md says “uv add docs-mcp” and “pip install docs-mcp.” For that to work **without cloning the monorepo**, docs-mcp must be on PyPI (or installable via `pip install git+...`).  
  - **Needed if:** you want standalone adoption (e.g. “pip install docs-mcp” in other repos).  
  - **Not needed if:** only monorepo users run `uv sync --all-packages` and use `docsmcp` from the workspace.

- **Docker:**  
  - Image already exists. “Distribution” here = **publishing** the image (e.g. GHCR) and documenting it. Useful for CI and container-based MCP hosts; not strictly required for local Cursor/Claude use.

- **npm wrapper:**  
  - Community guidance: for **Python** CLIs, **pip/pipx/PyPI** are the right distribution; npm/npx wrappers add complexity and are only useful when targeting Node-first users.  
  - Cursor/VS Code can run any command (e.g. `uvx docsmcp serve` or `docsmcp serve` after pip/uv install).  
  - **Verdict:** **Not needed** for MVP; can defer or drop.

- **CLI `generate` / `check`:**  
  - Primary use is MCP: user runs `docsmcp serve`; the IDE uses **tools** (`docs_generate_readme`, `docs_check_drift`, etc.).  
  - A CLI `docsmcp generate` or `docsmcp check` is convenience for scripts/CI; not required for the main “AI uses DocsMCP tools” flow.  
  - **Verdict:** **Nice-to-have**, not MVP-blocking.

- **CI workflow generator (10.5):**  
  - Helps consuming projects run docs checks in CI. Valuable for adoption but not for “DocsMCP works in an IDE.”

**Verdict Epic 10:**

- **Needed for documented “standalone” install:**  
  - **10.1 PyPI for docs-mcp** — if you keep “uv add docs-mcp” / “pip install docs-mcp” in INSTALLATION.md, you should either publish docs-mcp to PyPI or change the doc to “from source only.”
- **Optional / defer:**  
  - **10.2** Full CLI `generate`/`check` — optional; tools cover the workflow.  
  - **10.3** Docker **publish** — optional; image already exists.  
  - **10.4** npm wrapper — **not needed**; recommend dropping or keeping as post-MVP.  
  - **10.5** CI workflow generator — optional; improves adoption, not core functionality.

---

## 3. Epic 12: Multi-Language Support

- PRD and EPIC_PRIORITIZATION already mark this as **post-MVP** (~2 weeks, tree-sitter + TypeScript/Go/Rust/Java).  
- Python-only is sufficient for launch; no evidence that multi-language is required for initial adoption.

**Verdict Epic 12:** **Not needed for MVP.** Keep as post-MVP.

---

## 4. Summary: What Is Really Needed

| Epic | Item | Really needed? | Action |
|------|------|----------------|--------|
| **9** | MCP resources (status, config, coverage) | Already done | — |
| **9** | MCP prompts (workflow) | Already done | — |
| **9** | `docs://templates/{type}` | No (host support weak; tools suffice) | Defer or drop |
| **9** | AGENTS.md generation | No (nice-to-have) | Defer or drop |
| **10** | PyPI for docs-mcp | **Yes**, if standalone install is promised | Add build/publish for docs-mcp or change install docs |
| **10** | CLI serve/doctor/scan/version | Already done | — |
| **10** | CLI generate/check | No (tools cover use case) | Optional |
| **10** | Docker image | Exists | Optional: add publish to registry |
| **10** | npm wrapper | No | Drop or post-MVP |
| **10** | CI workflow generator | No for MVP | Optional |
| **12** | Multi-language | No for MVP | Keep post-MVP |

---

## 5. Recommended Plan

1. **Epic 9**  
   - **Close as complete.** Document that resources/prompts are implemented; `docs://templates` and AGENTS.md generation are deferred (low ROI / host support). Update `docs/planning/epics/README.md` and `EPIC_PRIORITIZATION.md` accordingly.

2. **Epic 10**  
   - **Must-have (if you keep “pip/uv install docs-mcp” in docs):** Add PyPI packaging/publish for **docs-mcp** (separate job or matrix in `.github/workflows/publish.yml` so that on release, docs-mcp wheel is built and published).  
   - **Optional:** Publish Docker image to GHCR; add `docsmcp check` (or similar) CLI that runs validation tools for script/CI use; add CI workflow generator.  
   - **Drop or defer:** npm wrapper; full CLI `generate` (stub is enough).

3. **Epic 12**  
   - Leave as **post-MVP**; no change.

4. **Planning docs**  
   - In DOCSMCP_PRD.md (Epic breakdown), add one sentence under Epic 9: “Resources and prompts implemented; templates resource and AGENTS.md generation deferred.”  
   - In EPIC_PRIORITIZATION.md, adjust “remaining work” to reflect: Epic 9 complete; Epic 10 = PyPI for docs-mcp (+ optional Docker publish / CLI / CI gen); Epic 12 unchanged.

---

## 6. References

- MCP resources vs tools: [Fast.io](https://fast.io/resources/mcp-resources-vs-tools/), [Layered System – MCP Resources: The Overlooked Primitive](https://layered.dev/mcp-resources-the-overlooked-primitive/) (Claude Desktop/Code resource issues, host support).  
- MCP spec: resources and prompts (modelcontextprotocol.io).  
- Python CLI distribution: pipx as npx equivalent; npm wrapper not necessary for Python-first tools.  
- Repo: `packages/docs-mcp/src/docs_mcp/server_resources.py`, `packages/docs-mcp/Dockerfile`, `.github/workflows/publish.yml`, `packages/docs-mcp/docs/INSTALLATION.md`.
