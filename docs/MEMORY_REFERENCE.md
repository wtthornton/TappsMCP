# TappsMCP Memory Reference

Complete reference for the `tapps_memory` tool's 28 actions.

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
| **save** | `key`, `value`, `tier`, `scope`, `tags`, `source` | Save a memory entry |
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
| **gc** | -- | Archive stale memories |
| **contradictions** | -- | Detect memories contradicting current project state |
| **reseed** | -- | Re-seed from project profile (never overwrites human memories) |

## Consolidation

| Action | Parameters | Description |
|--------|-----------|-------------|
| **consolidate** | `entry_ids` or `query`, `dry_run` | Merge related memories with provenance |
| **unconsolidate** | `key` | Undo consolidation, restore sources |

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
| **index_session** | `session_id` | Index session transcript chunks into memory for later retrieval |
| **validate** | `key` | Validate a memory entry against current project state |
| **maintain** | -- | Run full maintenance cycle (gc + contradictions + reseed) |

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
max_memories: 1500
gc_auto_threshold: 0.8
memory_decay_enabled: true
profile: ""  # Empty = auto-detect. Override: "repo-brain", "research-knowledge", etc.

memory_hooks:
  auto_recall:
    enabled: false
    min_score: 0.3
  auto_capture:
    enabled: false
    max_facts: 5
```
