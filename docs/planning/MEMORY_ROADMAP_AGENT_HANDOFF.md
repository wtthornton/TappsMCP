# Memory roadmap — agent execution chunks

**Purpose:** Split [TAPPS_MCP_MEMORY_ROADMAP.md](TAPPS_MCP_MEMORY_ROADMAP.md) Tier C (and remaining gaps) into **independent, agent-sized work packages**. Each chunk lists files, dependencies, acceptance checks, and explicit **out-of-scope** items.

**Canonical spec:** `docs/planning/TAPPS_MCP_MEMORY_ROADMAP.md` (M3–M7).

**Repo constraints:** Python 3.12+, `mypy --strict`, `ruff`, async handlers, `structlog`, path validator for any new file reads.

---

## Before any chunk: baseline (15 min)

1. Read `packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py` — `_VALID_ACTIONS` and dispatch map at bottom.
2. Read `packages/tapps-mcp/src/tapps_mcp/server_helpers.py` — `_get_memory_store()`, cache reset patterns.
3. Run: `uv run pytest packages/tapps-mcp/tests/ -m "not slow" -k "memory" -q` (adjust `-k` if too narrow).
4. Pin: **tapps-brain** is git-sourced at `v1.3.1` (root `pyproject.toml`). Inspect installed API with:
   `uv run python -c "import tapps_brain.hive as h; print(dir(h))"` (and same for `audit`, `markdown_import`, `metrics` if needed).

---

## Already shipped (do not re-implement blindly)

Verify in tree before duplicating:

| Area | Likely location |
|------|-----------------|
| M1 security actions, dual-server doctor | `distribution/doctor.py` (`check_dual_memory_server`), `server_memory_tools.py` (`safety_check`, `verify_integrity`) |
| M2 profiles | `server_memory_tools.py` (`profile_info`, `profile_list`, `profile_switch`) |
| M2 promotion hint on reinforce | `_handle_reinforce` — search `promoted` in `server_memory_tools.py` |
| Session memory hints | `server_pipeline_tools.py` — memory_status / enrichment helpers |

If the roadmap checkbox disagrees with code, **update the roadmap doc** instead of copying implementations.

---

## Chunk sequence (recommended order)

### CHUNK-A — Hive discovery (prerequisite, ~0.5 day)

**Goal:** Confirm what `tapps_brain.hive` actually exposes in v1.1.0 vs the roadmap’s assumed API (`HiveStore`, `register_agent`, `list_namespaces`, etc.).

**Do:**
- Document real class names, methods, and constructor args in a short note (append to this file under “Hive API notes” or a comment in CHUNK-B PR).
- If API differs, adjust CHUNK-B design **before** coding.

**Done when:** Written mapping `{roadmap name → actual symbol}` and a minimal import smoke test passes.

**Out of scope:** TappsMCP feature code.

---

### CHUNK-B — M3.1–M3.2 Hive bootstrap + session start (`hive_status` in session)

**Goal:** Optional Hive singleton when Agent Teams env is set; expose non-fatal status in `tapps_session_start`.

**Files (typical):**
- `packages/tapps-mcp/src/tapps_mcp/server_helpers.py` — `_get_hive_store`, `_reset_hive_store_cache` (mirror memory store pattern; thread-safe).
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` — attach `hive_status` dict to session start payload.
- `packages/tapps-mcp/tests/conftest.py` (or package conftest) — reset hive cache in autouse fixture if present.

**Behavior:**
- If `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` unset → `hive_status.enabled == false`, no errors.
- If set but Hive unavailable / ImportError → `degraded: true` + message (same pattern as other optional tapps-brain features).

**Tests:** Unit tests with env var patched; no requirement for real multi-agent runtime.

**Depends on:** CHUNK-A.

---

### CHUNK-C — M3.3–M3.6 `tapps_memory` Hive actions

**Goal:** `hive_status`, `hive_search`, `hive_propagate`, `agent_register` actions delegating to real Hive when enabled; graceful degraded responses otherwise.

**Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py` — `_VALID_ACTIONS`, handlers, tool docstring action list.
- `tools/checklist.py` — only if checklist references specific memory actions (grep first).

**Tests:** `packages/tapps-mcp/tests/unit/` — mock Hive or patch `_get_hive_store`; cover disabled and degraded paths.

**Depends on:** CHUNK-B.

---

### CHUNK-D — M4.1 Auto-save expert consultations

**Goal:** After `tapps_consult_expert` (or central wrapper), optionally persist a **pattern**-tier memory when `memory.auto_save_quality` (or roadmap name) is true.

**Files:** Locate the single success exit path for expert consultation (grep `tapps_consult_expert`, `consult_expert` in `server_*tools.py`). Add `MemorySettings` field in `packages/tapps-core` or `tapps-mcp` config (follow existing `memory` model).

**Tests:** Mock `MemoryStore.save`, assert called once when flag on.

**Depends on:** None (parallel to Hive after baseline).

---

### CHUNK-E — M4.2 Recurring `tapps_quick_check` failures

**Goal:** Detect same file + same category failing repeatedly; reinforce or save **procedural** memory.

**Files:** `server_scoring_tools.py` / quick_check handler + small helper module or `server_helpers.py` (avoid circular imports).

**Caution:** Needs **bounded** in-process or project-local state (do not grow unbounded). Roadmap suggests key per file+category.

**Tests:** Simulate three failures; assert one save/reinforce behavior.

**Depends on:** None (parallel).

**Execution status (this repo):** Landed — `quick_check_recurring.py`, `MemorySettings.track_recurring_quick_check` + `recurring_quick_check_threshold`, `_reset_recurring_quick_check_state` in conftest teardown, tests `test_memory_recurring_quick_check.py`.

---

### CHUNK-F — M4.3 Architectural save → supersede

**Goal:** On `save` with `tier=architectural` and existing key, call `store.supersede` (or tapps-brain equivalent) when setting enabled.

**Files:** `server_memory_tools.py` — `_handle_save` (or equivalent).

**Tests:** Mock store with existing entry; assert supersede path.

**Depends on:** Confirm `MemoryStore.supersede` signature in installed tapps-brain (baseline step).

**Execution status (this repo):** Landed — `MemorySettings.auto_supersede_architectural` (default `true` for POC);
`_memory_tier_label`, `_resolve_architectural_supersede_old_key`, `_handle_save` supersede path +
fallback to `save`; `version_count` / `superseded_old_key` / `new_key` on success. Tests:
`test_memory_architectural_supersede.py`.

---

### CHUNK-G — M4.4 Impact analysis + memory context

**Goal:** `tapps_impact_analysis` response includes a **memory_context** (or `knowledge_context`) section from `store.search` and, if available, relation APIs.

**Files:** `packages/tapps-mcp/src/tapps_mcp/tools/impact.py` (or current impact implementation — grep `impact_analysis`).

**Tests:** Mock store search results; assert response shape.

**Depends on:** None (parallel).

**Execution status (this repo):** Landed (2026-03-23) — `MemorySettings.enrich_impact_analysis`,
`server_helpers.build_impact_memory_context`, wired in `server_analysis_tools.tapps_impact_analysis`;
`ImpactOutput.memory_context`; tests `test_memory_impact_context.py`. Relation-graph enrichment
still optional (no stable public API in tapps-brain v1.1.0).

---

### CHUNK-H — M4.5 Config wiring

**Goal:** Add `MemorySettings` flags: `auto_save_quality`, `auto_supersede_architectural`, `enrich_impact_analysis` (names must match YAML keys under `memory:`).

**Files:** Config models + default yaml + `tapps_validate_config` if applicable.

**Depends on:** CHUNK-D, F, G (land config when behaviors exist, or land flags first with no-ops).

**Partial (this repo):** `enrich_impact_analysis` landed with CHUNK-G (M4.4). `auto_supersede_architectural`
landed with CHUNK-F (M4.3). Remainder of M4.5 is doc-only / validate-config surfacing if desired.

---

### CHUNK-I — M5 Feature-gap actions (split per PR if large)

**Goal:** Add actions: `audit`, `audit_recent`, `import_markdown`, `relations`, `metrics` — each **delegates** to tapps-brain if module exists; otherwise return `degraded` + clear message.

**Files:** `server_memory_tools.py` primary.

**Order within chunk (suggested):**  
1) `import_markdown` (highest user value)  
2) `relations`  
3) `audit` / `audit_recent`  
4) `metrics`

**Tests:** One test file per action or parameterized; include ImportError path.

**Depends on:** Baseline introspection of `tapps_brain` modules.

---

### CHUNK-J — M6 Memory-aware quality (two PRs ok)

**J1 — M6.3:** `tapps_quick_check` adds `memory_context` (search by file path / basename), **no score change**.

**J2 — M6.1 + M6.2:** Recall conventions for scoring response section; optional **convention** category with **weight 0** default.

**Files:** `server_pipeline_tools.py`, `scoring/scorer.py`, `scoring/categories.py`, settings.

**Tests:** Performance assertion or benchmark note (<50ms memory add — roadmap); unit tests with mocked store.

---

### CHUNK-K — M7 Init, doctor, docs

**Goal:**  
- `tapps_init`: hint if `MEMORY.md` exists; hint if uv workspace (federation).  
- `doctor`: `check_memory_health` / profile checks if not already present (dual-server already exists).  
- Docs: `docs/MEMORY_REFERENCE.md`, `AGENTS.md`, `README.md` action counts.

**Files:** `pipeline/init.py`, `distribution/doctor.py`, docs.

**Depends on:** CHUNK-I if docs list `import_markdown` etc.

---

## Per-chunk definition of done

- [ ] `uv run ruff check packages/tapps-mcp/src/` clean for touched files.
- [ ] `uv run mypy --strict packages/tapps-mcp/src/tapps_mcp/` (or narrowed paths if repo standard).
- [ ] Targeted pytest green; no new flaky timing tests.
- [ ] No new MCP **tools** unless explicitly required (prefer new `tapps_memory` **actions**).
- [ ] Update `docs/planning/TAPPS_MCP_MEMORY_ROADMAP.md` checkboxes for completed items.

---

## Parallelization

| Track 1 (sequential) | Track 2 (parallel after baseline) |
|----------------------|-------------------------------------|
| A → B → C | D, E, G (done 2026-03-23) |
| | ~~F~~ done (M4.3 architectural supersede) |
| | I after tapps_brain introspection |
| | J, K late (K partly parallel) |

---

## Hive API notes (CHUNK-A — tapps-brain v1.1.0)

**Smoke test:** `uv run python -c "from tapps_brain.hive import AgentRegistration, AgentRegistry, HiveStore, PropagationEngine; HiveStore; AgentRegistry.register"`

| Roadmap / assumed name | Actual symbol / behavior |
|------------------------|-------------------------|
| `HiveStore.register_agent(...)` | **`AgentRegistry.register(agent: AgentRegistration)`** — YAML at `~/.tapps-brain/hive/agents.yaml` |
| `hive.list_agents()` | **`AgentRegistry.list_agents() -> list[AgentRegistration]`** |
| `hive.count()` (total Hive entries) | **Not in public API** — omit or add a tapps-brain helper later; do not call on `HiveStore` |
| `HiveStore(...)` | `HiveStore(db_path: Path \| None = None)` → default `~/.tapps-brain/hive/hive.db` |
| `AgentRegistry(...)` | `AgentRegistry(registry_path: Path \| None = None)` → default `~/.tapps-brain/hive/agents.yaml` |
| `AgentRegistration` | Pydantic: `id`, `name`, `profile`, `skills`, `project_root` |
| `HiveStore` CRUD / search | `save`, `get`, `search`, `list_namespaces`, `close` |
| `PropagationEngine.propagate` | **Static** method — propagates **one** entry; args include `hive_store`, `agent_scope`, `agent_profile`, `tier`, `auto_propagate_tiers`, `private_tiers`. Bulk “push all local memories” is **not** a single brain API — TappsMCP must iterate. |

**Execution status (this repo):** CHUNK-B landed — `collect_session_hive_status`, `_get_hive_store` / `_get_hive_registry`, `_reset_hive_store_cache`, `hive_status` on full + quick `tapps_session_start`, conftest reset, tests in `test_memory_hive_session.py`. **CHUNK-C landed** — `tapps_memory` actions `hive_status`, `hive_search`, `hive_propagate`, `agent_register` in `server_memory_tools.py`; tests in `test_memory_hive_actions.py`. **M3 polish (2026-03-23):** explicit `propagation_config` on every `hive_status` payload (`_hive_propagation_config_payload`), `initial_session_hive_status()` for session-start defaults before/after collection. **CHUNK-D landed (M4.1)** — `MemorySettings.auto_save_quality` (default `true` for POC); `_expert_consultation_memory_key` + `_auto_save_expert_consultation_memory` in `server_helpers.py`; wired from `tapps_consult_expert` and `tapps_research`; tests in `test_memory_auto_save_expert.py`. **CHUNK-E landed (M4.2)** — `quick_check_recurring.py`, `MemorySettings.track_recurring_quick_check` + `recurring_quick_check_threshold`, wired from `server_scoring_tools.tapps_quick_check` / `_quick_check_single`; conftest resets recurrence state; tests in `test_memory_recurring_quick_check.py`.

---

## Handoff prompt (compact — ~1 screen)

Copy when you need a shorter onboarding blurb (expand from the handoff doc as needed).

```
Continue TappsMCP memory roadmap: MEMORY_ROADMAP_AGENT_HANDOFF.md + TAPPS_MCP_MEMORY_ROADMAP.md (M3–M7).
Done: CHUNK-A–E (Hive session + tapps_memory hive actions; M4.1 expert auto-save; M4.2 recurring quick_check → procedural memory).
Next (pick one): Track 1 (M3 propagation_config) done; Track 2 = CHUNK-G (impact + memory_context), CHUNK-F (architectural supersede — confirm MemoryStore.supersede first), CHUNK-H remainder (auto_supersede_architectural, enrich_impact_analysis on MemorySettings).
Process: baseline steps in handoff → tapps_session_start → one chunk → definition of done → update roadmap checkboxes.
Do not redo A–E; verify in code. Prefer tapps_memory actions over new MCP tools.
```

---

## Next-session handoff prompt (full — copy everything in the fence)

Use this when onboarding a new agent to continue the memory roadmap after CHUNK-A/B/C/D/E/F.

```
You are continuing TappsMCP work from docs/planning/MEMORY_ROADMAP_AGENT_HANDOFF.md
and the canonical spec docs/planning/TAPPS_MCP_MEMORY_ROADMAP.md (epics M3–M7).

## Already completed in this repo (do not redo)

- CHUNK-A: Hive API mapped to tapps-brain v1.1.0 — see “Hive API notes” in the handoff doc.
- CHUNK-B: `server_helpers.py` — `_ensure_hive_singletons`, `_get_hive_store`, `_get_hive_registry`,
  `_reset_hive_store_cache`, `collect_session_hive_status`. `server_pipeline_tools.py` — `hive_status`
  on full + quick `tapps_session_start`. `tests/conftest.py` resets hive cache. Tests:
  `packages/tapps-mcp/tests/unit/test_memory_hive_session.py`.
- CHUNK-C: `server_memory_tools.py` — `tapps_memory` actions `hive_status`, `hive_search`,
  `hive_propagate`, `agent_register` (+ `_VALID_ACTIONS`, dispatch, docstring). Tests:
  `test_memory_hive_actions.py`; `test_memory_epic42.py` expected action set updated.
- CHUNK-D (M4.1): `MemorySettings.auto_save_quality` in `tapps_core` config; `_auto_save_expert_consultation_memory`
  in `server_helpers.py`; `tapps_consult_expert` + `tapps_research` merge `quality_memory_*` fields. Tests:
  `test_memory_auto_save_expert.py`.
- CHUNK-E (M4.2): `memory.track_recurring_quick_check` + `recurring_quick_check_threshold`; `quick_check_recurring.record_quick_check_recurring`
  from `server_scoring_tools`; `recurring_quality_memory_events` on `tapps_quick_check` / `QuickCheckOutput`. Tests:
  `test_memory_recurring_quick_check.py`.
- CHUNK-F (M4.3): `MemorySettings.auto_supersede_architectural`; architectural `tapps_memory` `save`
  uses `store.history` + `MemoryStore.supersede` when enabled (fallback to `save`). Tests:
  `test_memory_architectural_supersede.py`.

## Behavioral notes (read before changing Hive code)

- Agent Teams gate: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` must be set for Hive init/actions
  (except `hive_status` / session payload still returns `enabled: false` when unset).
- Registration uses `AgentRegistry.register(AgentRegistration(...))`, not methods on `HiveStore`.
- `hive_search`: search text in `query` or `value`; `tags` doubles as comma-separated **namespace**
  filter (maps to `tag_list` in the tool).
- `hive_propagate`: iterates local `MemoryStore.snapshot().entries` (cap via `limit`, default 100);
  delegates per entry to `PropagationEngine.propagate` (tapps-brain static method).
- `agent_register`: `key` = agent id (validated first); profile from `memory.profile` settings.

## Expert / research auto-save (M4.1)

- Default **on** for POC: `memory.auto_save_quality` (set `false` in `.tapps-mcp.yaml` to disable). Requires `memory.enabled: true`.
- Wired on `tapps_consult_expert` and `tapps_research`; response includes `quality_memory_saved`,
  `quality_memory_key`, or `quality_memory_skip` / `quality_memory_error` when applicable.

## Recurring quick_check (M4.2)

- Default **on** for POC: `memory.track_recurring_quick_check` (set `false` to disable). Requires `memory.enabled: true`. Threshold via
  `memory.recurring_quick_check_threshold` (default 3, range 2–50).
- State is **in-process**, bounded (4096 `(path_fp, category)` keys), thread-safe; cleared per file on
  gate pass. Memory keys: `recurring-qc-{path_hash}-{category}`.
- `tapps_quick_check` / batch per-file results may include `recurring_quality_memory_events`
  (`saved` / `reinforced` / `skipped`).

## Architectural auto-supersede (M4.3)

- Default **on** for POC: `memory.auto_supersede_architectural` (set `false` to disable). Requires `memory.enabled: true`.
- On `tapps_memory` `save` with `tier=architectural`, resolves the active architectural head via
  `store.history(key)` and calls `MemoryStore.supersede`; on failure falls back to plain `save`.
- Successful supersede responses may include `status`, `superseded_old_key`, `new_key`, `version_count`.

## Known gaps / follow-ups

- **M3 propagation visibility (done):** `hive_status` / session `hive_status` always include
  `propagation_config` (`profile_sourced: false` + `hive_propagate_tool` notes) until tapps-brain
  exposes profile YAML tier lists to TappsMCP.
- Baseline `pytest packages/tapps-mcp/tests/ -m "not slow" -k memory` may still fail on this
  machine (schema version expectations vs tapps-brain 1.1.0, MemoryRetriever helper signatures).
  Fix or narrow tests if you touch memory retrieval.
- `server_memory_tools.py` is large; `tapps_quick_check` may score below gate threshold — prefer
  targeted ruff/mypy/pytest on files you change.

## Recommended next work (pick one track)

**Track 1 — M3 polish (small):** ~~Enrich `hive_status` with propagation hints / explicit “not
  available”~~ **Done (2026-03-23):** `propagation_config` on all `hive_status` payloads via
  `_hive_propagation_config_payload` + `initial_session_hive_status` for session-start defaults.

**Track 2 — CHUNK-H (M4.5 remainder):** ~~Land `auto_supersede_architectural`~~ **Done with CHUNK-F.**
  `enrich_impact_analysis` already on `MemorySettings`. **Already on MemorySettings:** `auto_save_quality`,
  `track_recurring_quick_check`, `recurring_quick_check_threshold` — do not duplicate.

**Track 2 — parallel:** ~~CHUNK-G~~ done; ~~CHUNK-F~~ done (`MemoryStore.supersede(old_key, new_value, **kwargs)`).

## Process

1. Run the “Before any chunk: baseline” steps in MEMORY_ROADMAP_AGENT_HANDOFF.md.
2. Call `tapps_session_start` then implement the chosen chunk only; follow “Definition of done”.
3. Prefer new `tapps_memory` actions over new MCP tools. Use path validator for file reads.
4. Update TAPPS_MCP_MEMORY_ROADMAP.md checkboxes / Phase table when you complete items.

## Single-chunk prompt (when scope is one chunk only)

You are implementing CHUNK-<X> from docs/planning/MEMORY_ROADMAP_AGENT_HANDOFF.md.
Read that chunk and TAPPS_MCP_MEMORY_ROADMAP.md for the matching epic (M3–M7).
Do not duplicate features under “Already shipped” or “Already completed” — verify in code first.
Follow Definition of done in the handoff doc. Keep changes scoped to this chunk only.
```

---

## Agent prompt snippet (copy-paste)

```
You are implementing CHUNK-<X> from docs/planning/MEMORY_ROADMAP_AGENT_HANDOFF.md.
Read that chunk and TAPPS_MCP_MEMORY_ROADMAP.md for the matching epic (M3–M7).
Do not duplicate features listed under “Already shipped” — verify in code first.
Follow Definition of done in the handoff doc. Keep changes scoped to this chunk only.
```
