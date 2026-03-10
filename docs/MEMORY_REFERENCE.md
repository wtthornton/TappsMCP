# TappsMCP Memory Reference

Complete reference for the `tapps_memory` tool's 20 actions.

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

## Configuration (.tapps-mcp.yaml)

```yaml
max_memories: 1500
gc_auto_threshold: 0.8
memory_decay_enabled: true

memory_hooks:
  auto_recall:
    enabled: false
    min_score: 0.3
  auto_capture:
    enabled: false
    max_facts: 5
```
