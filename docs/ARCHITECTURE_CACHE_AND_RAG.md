# Architecture: Context7 Cache and Expert RAG

This document describes how the **Context7 documentation cache** and **Expert RAG indices** work, when they are created/updated, and how to refresh them when needed.

---

## 1. Context7 Documentation Cache

### Purpose

`tapps_lookup_docs` fetches library documentation (e.g. FastAPI, React, SQLAlchemy) from the Context7 API. To reduce latency and API usage, responses are cached locally on disk.

### Cache Location

- **Project-scoped:** `{project_root}/.tapps-mcp/cache/`
- Entries are stored as markdown files with JSON metadata sidecars.

### Stale-While-Revalidate (SWR) Behavior

The lookup engine implements **stale-while-revalidate**:

1. **Cache hit (fresh):** Returns cached content immediately. No API call.
2. **Cache hit (stale):** Returns cached content immediately with a `source="stale_fallback"` and warning. A **background refresh** is queued; the next lookup will typically see fresh content.
3. **Cache miss:** Fetches from the Context7 API, stores in cache, returns the result.
4. **API failure:** If the Context7 API fails or the circuit breaker is open, returns any stale cached content when available instead of failing.

This design ensures fast responses even when entries are past their TTL, while still refreshing the cache asynchronously.

### TTL Parameters

| Setting | Value | Notes |
|---------|-------|-------|
| **Default TTL** | 24 hours | Applies to libraries without an override |
| **Fast-moving libraries** | 12 hours | `next`, `react`, `vue`, `svelte` |
| **Stable libraries** | 48 hours | `python`, `flask`, `django`, `sqlalchemy` |

Staleness is checked using the `cached_at` timestamp in the metadata sidecar. Per-library overrides are configured in `tapps_mcp/knowledge/cache.py` (`DEFAULT_STALENESS_POLICIES`).

### When the Cache Is Updated

- **On cache miss:** After a successful Context7 API fetch.
- **On background refresh:** When a stale entry is returned, a background task fetches fresh content and overwrites the cache entry.
- **On `tapps_init`:** Cache warming pre-fetches docs for detected project dependencies (when `warm_cache_from_tech_stack=True` and an API key is set).

---

## 2. Expert RAG Indices

### Purpose

`tapps_consult_expert` retrieves relevant chunks from curated expert knowledge files (markdown). When FAISS and sentence-transformers are installed, a **vector index** is built for semantic search; otherwise, keyword search is used.

### Index Location

- **Project-scoped:** `{project_root}/.tapps-mcp/rag_index/{domain_slug}/`
- Each expert domain has its own subdirectory (e.g. `security/`, `testing-strategies/`).

### When Indices Are Created

- **On `tapps_init`:** If `warm_expert_rag_from_tech_stack=True`, indices are pre-built for expert domains relevant to the detected tech stack (e.g. FastAPI → api-design-integration, pytest → testing-strategies).
- **On first `tapps_consult_expert` for a domain:** If no index exists and the vector backend is available, `VectorKnowledgeBase` builds the index on first search and saves it to the project index directory.

### When Indices Are Updated

RAG indices are **not** automatically invalidated when expert knowledge files change. The system assumes the knowledge base is updated infrequently (e.g. on TappsMCP releases or during local development of the package).

### Manual Index Rebuild

If you edit expert knowledge files (e.g. in `src/tapps_mcp/experts/knowledge/`) and want `tapps_consult_expert` to use the new content, you must **delete the existing index** so it can be rebuilt on the next consultation:

1. Remove the domain index directory:
   ```
   {project_root}/.tapps-mcp/rag_index/{domain_slug}/
   ```
   Or remove the entire `rag_index` folder to rebuild all domains:
   ```
   {project_root}/.tapps-mcp/rag_index/
   ```

2. The next `tapps_consult_expert` call for that domain will rebuild the index from the current knowledge files.

**Example (Windows PowerShell):**
```powershell
Remove-Item -Recurse -Force "C:\cursor\MyProject\.tapps-mcp\rag_index\security"
# Or rebuild all domains:
Remove-Item -Recurse -Force "C:\cursor\MyProject\.tapps-mcp\rag_index"
```

---

## 3. Summary

| Component | Created/Updated | Manual Refresh |
|-----------|-----------------|----------------|
| **Context7 cache** | On lookup (miss) or background refresh (stale) | Not needed; SWR keeps entries fresh |
| **RAG indices** | On `tapps_init` or first `tapps_consult_expert` | Delete `project_root/.tapps-mcp/rag_index/{domain}` or entire `rag_index/` folder |
