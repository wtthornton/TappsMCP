# TappsMCP Memory Reference

Complete reference for the `tapps_memory` tool’s **33 actions** (single MCP tool, action dispatch via `action=`).

**Pipeline defaults (POC-oriented):** shipped `default.yaml` enables `memory.auto_save_quality`, `memory.track_recurring_quick_check`, `memory.auto_supersede_architectural`, `memory.enrich_impact_analysis`, and `memory_hooks.auto_recall` / `auto_capture`. Override in `.tapps-mcp.yaml` to turn features off.

**Architectural saves:** when `memory.auto_supersede_architectural` is true, `save` with `tier=architectural` uses `MemoryStore.supersede` (via `store.history`) so prior versions stay in the temporal chain; responses may include `status`, `superseded_old_key`, `new_key`, `version_count`.

## Memory tiers

| Tier | Half-life | Use for | Examples |
|------|-----------|---------|----------|
| **architectural** | 180 days | Stable, long-lived decisions | "We use PostgreSQL", "Monorepo with 3 packages" |
| **pattern** | 60 days | Coding conventions | "Use structlog not print", "All models inherit BaseModel" |
| **procedural** | 30 days | Workflows, step sequences | "Deploy: build -> test -> push -> tag" |
| **context** | 14 days | Short-lived session facts | "Refactoring auth module this sprint" |

## Memory scopes

| Scope | Visibility | Use for |
|-------|-----------|---------|
| **project** | All sessions in this project (default) | Architecture, patterns, decisions |
| **branch** | Only sessions on this git branch | Branch-specific WIP |
| **session** | Current session only (expires 7 days) | Temporary notes |
| **shared** | Federation-eligible (cross-project) | Reusable knowledge |

## Core CRUD actions

| Action | Parameters | Description |
|--------|-----------|-------------|
| **save** | `key`, `value`, `tier`, `scope`, `tags`, `source` | Save a memory entry (architectural tier may supersede; see intro) |
| **save_bulk** | `entries` (list, max 50) | Batch save entries |
| **get** | `key` | Retrieve by key (includes provenance for consolidated) |
| **list** | `scope`, `tier`, `tags`, `limit`, `include_sources` | List with filters (max 50) |
| **delete** | `key` | Delete by key |

## Search

| Action | Parameters | Description |
|--------|-----------|-------------|
| **search** | `query`, `ranked`, `limit`, `scope`, `tier`, `tags` | BM25 composite scoring (40% relevance + 30% confidence + 15% recency + 15% frequency) |

## Intelligence & maintenance

| Action | Parameters | Description |
|--------|-----------|-------------|
| **reinforce** | `key`, `boost` | Reset decay clock, optionally boost confidence (max +0.2) |
| **gc** | -- | Archive stale memories. HTTP bridge calls `maintenance_gc` (operator-profile only — `memory_gc` was never registered on the brain side). When the active brain profile excludes `maintenance_gc` (default `full` does not include it), the bridge returns a structured `{"archived_count": 0, "degraded": True, "reason": ...}` payload instead of raising. See [`brain_bridge.py:1430`](../packages/tapps-core/src/tapps_core/brain_bridge.py#L1430). |
| **contradictions** | -- | Detect memories contradicting current project state |
| **reseed** | -- | Re-seed from project profile (never overwrites human memories) |

## Consolidation

| Action | Parameters | Description |
|--------|-----------|-------------|
| **consolidate** | `entry_ids` or `query`, `dry_run` | **Degraded since tapps-brain 3.10**. `memory_consolidate` was removed on the brain side; `BrainBridge` returns a structured degraded payload (`groups_found: 0`, `degraded: True`, `reason`) via the fallback at [`brain_bridge.py:1455`](../packages/tapps-core/src/tapps_core/brain_bridge.py#L1455). The same fallback also covers EPIC-073 profile gating (`reason: "memory_consolidate not in active brain profile"`). Plan to deprecate this action surface in tapps-mcp once the deprecation cycle completes. |
| **unconsolidate** | `key` | Same status as `consolidate` — returns degraded payload on tapps-brain 3.10+. |

## Import / export

| Action | Parameters | Description |
|--------|-----------|-------------|
| **import** | `file_path`, `overwrite` | Import from JSON (max 500 entries) |
| **export** | `file_path`, `format` | Export to JSON or Markdown |

## Federation (cross-project)

| Action | Parameters | Description |
|--------|-----------|-------------|
| **federate_register** | `project_id`, `tags` | Register in federation hub |
| **federate_publish** | -- | Publish shared-scope entries to hub |
| **federate_subscribe** | `sources`, `tag_filter`, `min_confidence` | Subscribe to other projects |
| **federate_sync** | -- | Pull subscribed memories |
| **federate_search** | `query` | Search local + federated (local boost) |
| **federate_status** | -- | Hub status: projects, subscriptions, counts |

## Session & maintenance

| Action | Parameters | Description |
|--------|-----------|-------------|
| **index_session** | `session_id`, `chunks` (JSON array) | Index session transcript chunks via the brain's `memory_index_session` tool (TAP-1633 — replaces the legacy local index). |
| **search_sessions** | `query`, `limit` | Search indexed session chunks via the brain's `memory_search_sessions` tool (TAP-1633). |
| **session_end** | `value` (summary), `tags`, `dry_run` (daily-note flag) | Record a session-end summary via the brain's `tapps_brain_session_end` tool (TAP-1633). |
| **validate** | `key` | Validate a memory entry against current project state |
| **maintain** | -- | Run full maintenance cycle (gc + contradictions + reseed) |

## Knowledge graph (TAP-1630)

Surface tapps-brain 3.17+ graph tools through `tapps_memory`. All four
require the HTTP bridge; in-process bridges return a structured
`knowledge_graph_requires_http_bridge` degraded payload.

| Action | Parameters | Description |
|--------|-----------|-------------|
| **related** | `key`, `max_hops` (default 2) | Walk the graph outward from `key`. Maps to `memory_find_related`. |
| **relations** | `key` OR (`subject` / `predicate` / `object_entity`) | Relations attached to an entry (`memory_relations`) or matching an SPO triple (`memory_query_relations`). At least one filter is required. |
| **neighbors** | `entry_ids` (comma-list), `max_hops`, `limit`, `predicate` | k-hop neighborhood of one or more entity ids. Maps to `brain_get_neighbors`. |
| **explain_connection** | `subject`, `object_entity`, `max_hops` (default 3) | Path explanation between two entity ids. Maps to `brain_explain_connection`. |

## Batch ops (TAP-1631)

Single-round-trip wrappers around the brain's `memory_*_many` endpoints.
In HTTP mode, `save_bulk` routes through `memory_save_many` automatically
(one POST for N entries). New explicit actions:

| Action | Parameters | Description |
|--------|-----------|-------------|
| **recall_many** | `entries` (JSON array of query strings) | Batch recall via `memory_recall_many`. |
| **reinforce_many** | `entries` (JSON array of `{key, confidence_boost?}` objects) | Batch confidence boost via `memory_reinforce_many`. |

## Feedback flywheel (TAP-1632)

Closes the loop on what the brain learned vs. what agents actually
needed. `search` auto-emits `feedback_gap` on misses; the `rate` action
records explicit per-entry feedback.

| Action | Parameters | Description |
|--------|-----------|-------------|
| **rate** | `key` (entry_key), `rating` (default `helpful`), `session_id`, `details_json` | Score an entry via `feedback_rate`. |

Auto-emit knobs in `.tapps-mcp.yaml`:

```yaml
memory:
  feedback_auto_emit: true       # default; set false to silence search-miss emits
  feedback_min_similarity: 0.0   # > 0 also emits when top hit < threshold
```

`tapps doctor` exposes the resulting state under the `tapps-brain
health` row (gap / rating counts from `flywheel_report` plus
`diagnostics_report` health_score).

## Security (Epic M1)

| Action | Parameters | Description |
|--------|-----------|-------------|
| **safety_check** | `value` | Pre-flight content safety validation. Checks for prompt injection patterns without saving. Returns flagged patterns and match count. |
| **verify_integrity** | -- | Check all memory entries for tampering. Computes content hashes and reports mismatches. |

## Profiles (Epic M2)

| Action | Parameters | Description |
|--------|-----------|-------------|
| **profile_info** | -- | Show the active memory profile: layers, decay config, scoring weights, promotion status. |
| **profile_list** | -- | List all available built-in profiles (repo-brain, personal-assistant, customer-support, research-knowledge, project-management, home-automation). |
| **profile_switch** | `value` (profile name) | Switch to a different memory profile. Persists to `.tapps-brain/profile.yaml` and resets the store. |

## Health

| Action | Parameters | Description |
|--------|-----------|-------------|
| **health** | -- | Store health / integrity-style signals when supported by tapps-brain. |

## Hive / Agent Teams (M3)

Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` for live Hive usage; actions still return structured payloads when Hive is disabled.

| Action | Parameters | Description |
|--------|-----------|-------------|
| **hive_status** | -- | Hive / registry status, propagation hints, `propagation_config`. |
| **hive_search** | `query` or `value`, `tags`, `limit` | Search Hive store (tags may filter namespace). |
| **hive_propagate** | `limit`, tiers, etc. | Push eligible local entries through `PropagationEngine`. |
| **agent_register** | `key` (agent id), `value`, `tags` | Register agent in Hive registry. |

### Built-in profiles

| Profile | Use case | Layers | Key emphasis |
|---------|----------|--------|-------------|
| **repo-brain** | Code repos (default) | architectural (180d), pattern (60d), procedural (30d), context (14d) | Relevance 40% |
| **personal-assistant** | Personal AI assistants | identity (365d), long-term (90d), short-term (7d), ephemeral (1d) | Recency 30% |
| **customer-support** | Support agents | product-knowledge (120d), customer-patterns (60d), interaction-history (14d), session-context (3d) | Frequency 25% |
| **research-knowledge** | Research/knowledge mgmt | established-facts (365d), working-knowledge (60d), observations (21d), scratch (3d) | Relevance 50% |
| **project-management** | PM tools | decisions (180d), plans (45d), activity (14d), noise (5d) | Recency 25% |
| **home-automation** | IoT/smart home | household-profile (365d), learned-patterns (60d), recent-events (7d), future-events (90d), transient (1d) | Recency 35% |

## Configuration (.tapps-mcp.yaml)

```yaml
memory:
  enabled: true
  profile: repo-brain # or "" for auto-detect
  max_memories: 1500
  gc_auto_threshold: 0.8
  inject_into_experts: true
  # Pipeline integrations (defaults on in shipped default.yaml; set false to disable)
  auto_save_quality: true
  track_recurring_quick_check: true
  recurring_quick_check_threshold: 3
  enrich_impact_analysis: true
  auto_supersede_architectural: true
  decay:
    architectural_half_life_days: 180
    pattern_half_life_days: 60
    context_half_life_days: 14

memory_hooks:
  auto_recall:
    enabled: true
    max_results: 5
    min_score: 0.3
    min_prompt_length: 50
  auto_capture:
    enabled: true
    max_facts: 5
```

Run `tapps-mcp doctor` to see **Memory pipeline (effective config)** for the resolved values in your project.
