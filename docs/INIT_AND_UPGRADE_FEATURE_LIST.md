# Init and Upgrade — Feature List

This document lists what each init-related process does. The codebase has **two init flows**; there is **no separate upgrade command**. Re-running init is idempotent where possible (existing files are skipped or merged).

---

## 1. **tapps_init** (MCP tool)

**What it is:** Bootstrap the TAPPS pipeline inside a consuming project. Exposed as the `tapps_init` MCP tool and implemented in `src/tapps_mcp/pipeline/init.py` (`bootstrap_pipeline()`).

**When to use:** At the start of a pipeline run in a project that will use TappsMCP for quality checks, doc lookup, and experts. Call once per project (or again to refresh TECH_STACK, cache, and RAG indices).

### Features

| Feature | Flag / behavior | What it does |
|--------|------------------|--------------|
| **Handoff template** | `create_handoff=True` | Creates `docs/TAPPS_HANDOFF.md` from template (only if file does not exist). |
| **Runlog template** | `create_runlog=True` | Creates `docs/TAPPS_RUNLOG.md` from template (only if file does not exist). |
| **AGENTS.md** | `create_agents_md=True` | Creates `AGENTS.md` with AI assistant workflow from template **only if missing**; never overwrites so user customizations are preserved. |
| **TECH_STACK.md** | `create_tech_stack_md=True` | Runs project profiler, then **creates or overwrites** `TECH_STACK.md` with project type, languages, frameworks, libraries, domains, Context7 priority, CI/Docker/tests, and recommendations. |
| **Server verification** | `verify_server=True` | Verifies server info and lists installed vs missing checkers (ruff, mypy, bandit, radon). |
| **Install missing checkers** | `install_missing_checkers=True` | After verification, attempts to `pip install` missing checkers using each checker’s install hint (opt-in). |
| **Platform rules** | `platform="claude"` or `"cursor"` | **Claude:** Appends TAPPS pipeline reference to `CLAUDE.md` (or creates it). **Cursor:** Creates `.cursor/rules/tapps-pipeline.md`. Empty string skips. |
| **Overwrite platform rules** | `overwrite_platform_rules=True` | When true, refreshes platform rule files even if they exist. Use when upgrading TappsMCP to get latest templates. |
| **Overwrite AGENTS.md** | `overwrite_agents_md=True` | When true, replaces AGENTS.md with the latest template. Use when upgrading to get new workflow. Default: false (validate and smart-merge only). |
| **Cache warming** | `warm_cache_from_tech_stack=True` | Uses project profile’s Context7 priority list; pre-fetches docs for those libraries (up to 20) into `.tapps-mcp-cache`. Requires Context7 API key; skips if missing or no libraries. |
| **Expert RAG warming** | `warm_expert_rag_from_tech_stack=True` | Maps tech stack (frameworks, libraries, domains) to expert domains; pre-builds vector RAG indices under `project_root/.tapps-mcp/rag_index/` for up to 10 domains so first `tapps_consult_expert` is fast. |
| **Hooks generation** | `platform="claude"` or `"cursor"` | **Claude:** Creates 7 hook scripts in `.claude/hooks/` and merges hook config into `.claude/settings.json`. **Cursor:** Creates 3 hook scripts in `.cursor/hooks/` and merges into `.cursor/hooks.json`. Existing entries are preserved. |
| **Subagent definitions** | `platform="claude"` or `"cursor"` | Creates 3 agent `.md` files (tapps-reviewer, tapps-researcher, tapps-validator) in `.claude/agents/` or `.cursor/agents/`. Skips existing files to preserve customizations. Platform-specific frontmatter (Claude: comma-separated tools, Cursor: YAML array tools). |
| **Skills generation** | `platform="claude"` or `"cursor"` | Creates 3 skill directories with `SKILL.md` (tapps-score, tapps-gate, tapps-validate) in `.claude/skills/` or `.cursor/skills/`. Skips existing files. |
| **Cursor rule types** | `platform="cursor"` | Creates 3 `.mdc` rule files: `tapps-pipeline.mdc` (alwaysApply), `tapps-python-quality.mdc` (autoAttach `*.py`), `tapps-expert-consultation.mdc` (agentRequested). Reduces context bloat. |
| **Agent Teams** | `agent_teams=True` | Opt-in. Generates TeammateIdle and TaskCompleted hooks for quality watchdog teammate in `.claude/hooks/` and merges into `.claude/settings.json`. Only applies when `platform="claude"`. |
| **Dry run** | `dry_run=True` | Computes and returns what would be created without writing files or warming caches. Skips server verification. Keeps run lightweight (~2–5s). See [MCP_CLIENT_TIMEOUTS.md](MCP_CLIENT_TIMEOUTS.md). |
| **Verify only** | `verify_only=True` | Runs only server verification and returns immediately (~1–3s). Use for quick connectivity/checker checks. |

### Result shape

Returns a dict with: `created`, `skipped`, `errors`, `success`, plus `server_verification`, `agents_md`, `tech_stack_md`, `cache_warming`, `expert_rag_warming`, `hooks`, `agents`, `skills`, `cursor_rules` (Cursor only), `agent_teams` (when opted in).

### Idempotency / “upgrade” behavior

- **Handoff, runlog, AGENTS.md:** Created only if missing; never overwritten unless `overwrite_agents_md=True`.
- **TECH_STACK.md:** Recreated from current project profile on every run (refresh/“upgrade” of stack summary).
- **Platform rules:** Use `overwrite_platform_rules=True` to refresh when templates change. Otherwise: Claude = append if no TAPPS reference; Cursor = write if missing.
- **Cache warming:** Only warms libraries not already cached or stale.
- **Expert RAG warming:** Builds/refreshes indices for selected domains.

So “upgrading” pipeline artifacts and caches is done by **calling `tapps_init` again** with the desired flags.

---

## 2. **CLI init** (`tapps-mcp init`)

**What it is:** Generate or verify MCP host configuration so Claude Code, Cursor, or VS Code can run/connect to the TappsMCP server. Implemented in `src/tapps_mcp/distribution/setup_generator.py` (`run_init()`) and invoked via `tapps-mcp init` in `src/tapps_mcp/cli.py`.

**When to use:** After installing TappsMCP, to add or update the MCP server entry in the host’s config. Use `--check` to verify without writing.

### Features

| Feature | Option / behavior | What it does |
|--------|-------------------|--------------|
| **Host selection** | `--host claude-code \| cursor \| vscode \| auto` | Target MCP host. `auto` detects installed hosts (`.claude` dir, Cursor/VS Code settings dirs) and uses the first detected. |
| **Project root** | `--project-root PATH` | Project root; used for Cursor/VS Code config paths (project-level `.cursor/mcp.json` or `.vscode/mcp.json`). Default: current directory. |
| **Config scope** | `--scope user \| project` | For Claude Code: `user` writes to `~/.claude.json`, `project` writes to `.mcp.json` in the project root. Default: `user`. |
| **Generate config** | (default, no `--check`) | Writes or merges the `tapps-mcp` server entry into the host’s config file. Preserves other servers; only adds/updates the `tapps-mcp` entry. |
| **Verify config** | `--check` | Checks that the host’s config file exists and contains a valid `tapps-mcp` server entry; no writes. |
| **Platform rules** | `--rules / --no-rules` | Generate platform rule files (CLAUDE.md or .cursor/rules/tapps-pipeline.md) alongside MCP config. Default: `--rules`. |
| **Host detection** | (when `--host auto`) | Detects Claude Code (`~/.claude`), Cursor (platform-specific App Data / `.config`), VS Code (Code app data). |
| **Config paths** | (per host) | **Claude Code:** `~/.claude.json` (user) or `.mcp.json` (project). **Cursor:** `project_root/.cursor/mcp.json`. **VS Code:** `project_root/.vscode/mcp.json`. |
| **Server entry** | (merged into config) | Adds `tapps-mcp` with `command: "tapps-mcp"`, `args: ["serve"]` under `mcpServers` (Claude/Cursor) or `servers` (VS Code). |
| **Force overwrite** | `--force` | Overwrite existing tapps-mcp entry without prompting. Use when upgrading or in non-interactive scripts. |
| **Diagnostics** | `tapps-mcp doctor` | Separate command that diagnoses TappsMCP configuration, connectivity, and missing dependencies. |

### Idempotency / “upgrade” behavior

- **Generate:** Merge-safe; re-running overwrites only the `tapps-mcp` key in the servers object, so re-run is the way to “upgrade” or fix the server entry (e.g. after changing how TappsMCP is invoked).

---

## Summary

| Process | Entry point | Purpose |
|--------|-------------|---------|
| **tapps_init** | MCP tool `tapps_init` | Bootstrap pipeline files (handoff, runlog, AGENTS.md, TECH_STACK.md), optional platform rules, server verification, cache warming, expert RAG warming. |
| **CLI init** | `tapps-mcp init` | Generate or verify MCP host config so the IDE/host can start TappsMCP. |

There is **no separate upgrade command**. To refresh project pipeline state and caches, run **tapps_init** again. To refresh host MCP configuration, run **tapps-mcp init** again (optionally with `--check` first).

---

## Upgrading when TappsMCP ships new features (consuming projects)

When you upgrade TappsMCP (`pip install -U tapps-mcp` or similar), new workflow templates and AGENTS.md content may be available. To get the latest templates in your project:

| What to refresh | How |
|-----------------|-----|
| **AGENTS.md** (workflow, tool hints) | Call `tapps_init` with `overwrite_agents_md=True` to replace AGENTS.md with the latest template. Or rely on validate/smart-merge (default) to add missing sections. |
| **Platform rules** (CLAUDE.md, .cursor/rules/tapps-pipeline.md) | Call `tapps_init` with `platform="cursor"` or `"claude"` and `overwrite_platform_rules=True` to refresh rule files. |
| **TECH_STACK.md, caches, RAG indices** | Re-run `tapps_init` with defaults; TECH_STACK is overwritten, cache/RAG warming refreshes as needed. |
| **MCP host config** | Run `tapps-mcp init --force` to overwrite the tapps-mcp entry in the host config without prompting. |

**Example (via AI):** “Call tapps_init with overwrite_agents_md=True and overwrite_platform_rules=True, platform=cursor, to refresh to the latest TappsMCP templates.”

**Example (CLI):** `tapps-mcp init --force --host cursor` to refresh MCP config. Platform rules are generated but not overwritten if they already exist (use tapps_init with overwrite_platform_rules for that).

---

## Epic 10+11 (complete): Expert + Context7 Integration & Retrieval Optimization

Epic 10 and Epic 11 added tighter coupling between expert consultation and doc lookup, plus retrieval quality improvements. All 10 stories are shipped and tested (230 epic-scoped tests passing).

| Enhancement | Delivered via | Status |
|-------------|---------------|--------|
| Expert + doc lookup workflow guidance | AGENTS.md, agents_template.md, recommended_workflow | ✅ Shipped |
| Structured `suggested_tool` / `suggested_library` / `suggested_topic` when RAG is empty | `tapps_consult_expert` response | ✅ Shipped |
| Auto-fallback to Context7 when expert RAG is empty | `tapps_consult_expert` (configurable via `expert_auto_fallback`) | ✅ Shipped |
| Broader testing-strategies KB (test config, URLs, env) | Knowledge files (`test-configuration-and-urls.md`) | ✅ Shipped |
| `tapps_research` combined tool | New MCP tool | ✅ Shipped |
| Hybrid fusion + rerank retrieval | `VectorKnowledgeBase._hybrid_fuse()` | ✅ Shipped |
| Hot-rank adaptive ranking | `experts/hot_rank.py` | ✅ Shipped |
| Fuzzy matcher v2 (multi-signal) | `knowledge/fuzzy_matcher.py` | ✅ Shipped |
| Context7 code-reference normalization | `knowledge/content_normalizer.py` | ✅ Shipped |
| Retrieval evaluation harness + quality gates | `experts/retrieval_eval.py` | ✅ Shipped |

**To get Epic 10+11 content in your project:** After upgrading TappsMCP, run `tapps_init` with `overwrite_agents_md=True` and `overwrite_platform_rules=True` so AGENTS.md and platform rules include the new workflow. See [TAPPS_MCP_IMPROVEMENT_IMPLEMENTATION_PLAN.md](planning/TAPPS_MCP_IMPROVEMENT_IMPLEMENTATION_PLAN.md).

---

## High and critical recommendations for improvement

**Verification (2026-02-22):** All critical and high items have been implemented and verified.

### Critical

| # | Area | Status | Evidence |
|---|------|--------|----------|
| 1 | **CLI exit codes** | ✅ Implemented | `cli.py` raises `SystemExit(1)` when `run_init()` returns `False`. |
| 2 | **Invalid JSON in host config** | ✅ Implemented | `setup_generator.py` returns `False` on `JSONDecodeError`; does not overwrite. |
| 3 | **Cache warming failures hidden** | ✅ Implemented | `_run_cache_warming` sets `error`; `init.py` appends to `state.errors`. |

### High

| # | Area | Status | Evidence |
|---|------|--------|----------|
| 4 | **Checker install environment** | ✅ Implemented | `init.py` uses `sys.executable, "-m", "pip", "install", pkg`. |
| 5 | **Cursor platform rules never refresh** | ✅ Implemented | `overwrite_platform_rules` in `tapps_init`. |
| 6 | **Expert RAG warming errors not surfaced** | ✅ Implemented | `rag_warming.py` returns `failed_domains`; `init.py` appends to `state.errors`. |
| 7 | **No dry-run / preview** | ✅ Implemented | `dry_run` in `bootstrap_pipeline`; `--dry-run` in `tapps-mcp init`; `dry_run` in `tapps_init` MCP tool. |
| 8 | **Success vs subsystem failure** | ✅ Implemented | Cache and expert RAG failures append to `errors`. |
| 9 | **CLI init overwrite non-interactive** | ✅ Implemented | `--force` skips confirm prompt. |

---

### Original recommendations (reference; all implemented)

<details>
<summary>Click to expand original issue text</summary>

### Critical (original)

| # | Area | Issue | Recommendation |
|---|------|--------|----------------|
| 1 | **CLI exit codes** | `tapps-mcp init` and `tapps-mcp init --check` never call `sys.exit()`. When `--check` fails or the user aborts overwrite, the process still exits with code 0. Scripts and CI cannot detect failure. | Have `run_init()` (or the CLI command) call `sys.exit(1)` when `_check_config` returns `False` or when the user declines overwrite. Consider `sys.exit(0)` on success for consistency. |
| 2 | **Invalid JSON in host config** | In `_generate_config`, when the host config file contains invalid JSON, the code backs it up, sets `existing = {}`, and writes a **new** config that contains **only** the `tapps-mcp` entry. All other MCP servers in that file are lost. | On `JSONDecodeError`, do not overwrite. Either: (a) abort and tell the user to fix the JSON manually, or (b) read the backup after renaming, attempt to fix/reparse, and only write a merged config that preserves other keys. Never replace the file with a minimal config. |
| 3 | **Cache warming failures hidden** | In `_run_cache_warming`, `asyncio.run(warm_cache(...))` is wrapped in `except Exception: warmed = 0`. Any failure (network, Context7 API, encoding, etc.) is swallowed. The result reports `warmed: 0` with no error message or reason. | Catch exceptions, log them, and include a `cache_warming.error` (or `cache_warming.error_message`) in the result so callers and users know why warming failed. Optionally append a short message to `result["errors"]` so `success` can reflect subsystem failure. |

### High

| # | Area | Issue | Recommendation |
|---|------|--------|----------------|
| 4 | **Checker install environment** | `install_missing_checkers` runs `subprocess.run(["pip", "install", pkg], cwd=project_root)`. This can install into the wrong environment (e.g. system Python instead of the project’s venv). No use of `python -m pip` or venv detection. | Prefer invoking the same Python that runs TappsMCP (e.g. `sys.executable, "-m", "pip", "install", pkg`) so checkers are installed into the current environment. Optionally detect a project venv and use its pip. |
| 5 | **Cursor platform rules never refresh** | `_bootstrap_cursor` uses `_safe_write`, which **skips** if the file exists. So once `.cursor/rules/tapps-pipeline.md` is created, it is never updated when the template improves. There is no upgrade path for Cursor rules. | Add an option (e.g. `overwrite_platform_rules: bool = False` in `tapps_init`) to allow overwriting Cursor (and optionally CLAUDE) platform rules when re-running init, so users can refresh to the latest template. |
| 6 | **Expert RAG warming errors not surfaced** | In `warm_expert_rag_indices`, per-domain failures are caught with `except Exception: logger.debug(...)`. The returned dict only has counts and `skipped`; no list of failed domains or error messages. | Extend the return dict with e.g. `failed_domains: list[str]` and/or `errors: list[str]` so `tapps_init` can report which domains failed and optionally add them to the main `errors` list. |
| 7 | **No dry-run / preview** | Neither `tapps_init` nor `tapps-mcp init` support a dry-run. Users cannot see which files would be created or which config would be written before making changes. | Add a `dry_run: bool` (or CLI `--dry-run`) that computes and returns the same structure (files to create/update, config diff, etc.) without writing. |
| 8 | **Success vs subsystem failure** | `bootstrap_pipeline` sets `success = len(errors) == 0`. Cache and RAG warming can effectively “fail” (e.g. 0 warmed due to missing API key or exception) without adding to `errors`. So `success` can be `True` even when important subsystems did nothing or failed. | Either: (a) append to `errors` when cache/RAG warming fails (e.g. “Cache warming failed: …”), or (b) add a separate field such as `warnings` or `subsystem_status` so callers can distinguish “no errors but warming skipped” from “all good”. |
| 9 | **CLI init overwrite in non-interactive** | When `tapps-mcp init` finds an existing `tapps-mcp` entry, it calls `click.confirm("Overwrite...?")`. In non-interactive use (CI, scripts) this can block or default to “no” and abort without a clear “use --force to overwrite” path. | Support a non-interactive overwrite flag (e.g. `--force` or `--overwrite`) so scripts can re-run init without prompting. When not TTY and overwrite would be needed, exit with a clear message and non-zero code unless `--force` is set. |

</details>
