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

## Dependency Chain

```
tapps-brain v2.1.0 (tagged)
    └── EPIC-2: Hybrid Matcher (implemented, docs-mcp)
        └── EPIC-12: Catalog Governance (docs-mcp)
```

> **Note (2026-04-07):** EPIC-11 (Memory-Aware Agents) was removed — it belongs
> in the AgentForge repo, not docs-mcp. tapps-brain v2.1.0 has been tagged and
> the pin bumped.
