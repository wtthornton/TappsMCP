# tapps-brain v2.1.0 — Tag Required

**Date:** 2026-04-07
**Status:** Action needed in tapps-brain repo

## Summary

tapps-brain v2.1.0 has been released as a commit (c82937f) with the message:

> release: v2.1.0 — async API, PA extraction, procedural tier, temporal filtering, profile consolidation

However, **no git tag was created**. TappsMCP pins tapps-brain by tag (`v2.0.4`),
so the v2.1.0 features are not available to TappsMCP or docs-mcp.

## Action Required

In the tapps-brain repo (`/home/wtthornton/code/tapps-brain`):

```bash
git tag v2.1.0 c82937f
git push origin v2.1.0
```

Then in tapps-mcp, bump the pin:

```bash
# In pyproject.toml (root):
# tapps-brain = { git = "...", tag = "v2.1.0" }
uv lock
```

## v2.1.0 Features Needed by EPIC-11

These features already exist in the v2.1.0 commit and are required by
EPIC-11 (Memory-Aware Agents):

| Feature | Module | API |
|---------|--------|-----|
| Agent scope parameter | `store.py` | `MemoryStore.save(agent_scope="domain")` |
| Hive search | `hive.py` | `HiveStore.search()`, `search_with_groups()` |
| Recall orchestrator with hive | `recall.py` | `RecallOrchestrator._search_hive()` |
| Agent scope validation | `agent_scope.py` | `normalize_agent_scope()` |
| Group membership | `hive.py` | `get_agent_groups()`, `create_group()` |
| Profile/promotion | `profile.py`, `promotion.py` | `MemoryProfile`, `PromotionEngine` |
| Namespace listing | `hive.py` | `list_namespaces()` |

## Dependency Chain

```
tapps-brain v2.1.0 (tag needed)
    └── EPIC-2: Hybrid Matcher (new, docs-mcp)
        ├── EPIC-11: Memory-Aware Agents (docs-mcp)
        └── EPIC-12: Catalog Governance (docs-mcp)
```
