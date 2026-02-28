# Epic 29: Doc Provider Simplification

> Simplify documentation lookup from 4 providers to 2: Context7 + LlmsTxt.
> Deprecate Deepcon and Docfork to reduce config sprawl and maintenance burden.

**Status:** Proposed
**Priority:** P2 — Improvement
**Estimated LOE:** ~1 week
**Dependencies:** Epic 2 (Knowledge & Docs), Epic 16 (Doc Backend Resilience)
**Blocks:** None

---

## Goal

Reduce the doc lookup provider chain from four providers (Deepcon, Context7, Docfork, LlmsTxt) to two: **Context7** (primary, paid) and **LlmsTxt** (fallback, free). Deprecate Deepcon and Docfork.

## Rationale

| Consideration | Current (4 providers) | Target (2 providers) |
|---------------|------------------------|----------------------|
| **Best practice** | Single primary + one fallback | ✓ Context7 + LlmsTxt |
| **Config complexity** | 3 optional API keys | 1 optional key (Context7) |
| **Maintenance** | 4 integrations to maintain | 2 integrations |
| **Value** | Diminishing returns after 2 | Primary + free fallback sufficient |
| **Resilience** | LlmsTxt always-on, no key | Same; Context7 cache + LlmsTxt |

Deepcon and Docfork add marginal value for the complexity. Context7 has the richest integration (cache, SWR, circuit breaker). LlmsTxt is a solid zero-config fallback with growing adoption.

## Acceptance Criteria

- [ ] Provider chain uses only Context7 (if key) + LlmsTxt (always)
- [ ] Deepcon and Docfork removed from default chain
- [ ] `deepcon_api_key` and `docfork_api_key` deprecated and removed from settings
- [ ] Deepcon and Docfork provider modules removed or moved to optional/experimental
- [ ] All documentation updated (README, AGENTS.md, setup guides)
- [ ] Tests updated; all pass
- [ ] CHANGELOG updated

---

## Stories

### 29.1 — Simplify provider registry to Context7 + LlmsTxt

**LOE:** ~0.5 day

Remove Deepcon and Docfork from the default provider chain. Change `_build_provider_registry` to register only Context7 (when key present) and LlmsTxt.

**Source Files:**
- `src/tapps_mcp/knowledge/lookup.py`

**Tasks:**
- [ ] Remove Deepcon and Docfork imports and registration from `_build_provider_registry`
- [ ] Update docstring: "Context7 (if key), LlmsTxt (always)"
- [ ] Verify `ProviderRegistry` behavior unchanged (first success wins)

**Definition of Done:** Lookup uses only Context7 and LlmsTxt. Existing tests pass.

---

### 29.2 — Deprecate and remove Deepcon/Docfork settings

**LOE:** ~0.25 day

Remove `deepcon_api_key` and `docfork_api_key` from settings. Add deprecation notice in CHANGELOG for users who may have them set.

**Source Files:**
- `src/tapps_mcp/config/settings.py`
- `CHANGELOG.md`

**Tasks:**
- [ ] Remove `deepcon_api_key` and `docfork_api_key` from `TappsMCPSettings`
- [ ] Add CHANGELOG entry: deprecation note; users with keys set will be ignored (no runtime error)

**Definition of Done:** Settings no longer expose Deepcon/Docfork keys. CHANGELOG documents removal.

---

### 29.3 — Remove Deepcon and Docfork provider modules

**LOE:** ~0.5 day

Delete the Deepcon and Docfork provider implementations. Remove from providers package.

**Source Files:**
- `src/tapps_mcp/knowledge/providers/deepcon_provider.py` (delete)
- `src/tapps_mcp/knowledge/providers/docfork_provider.py` (delete)
- `src/tapps_mcp/knowledge/providers/__init__.py` (update exports if needed)

**Tasks:**
- [ ] Delete `deepcon_provider.py`
- [ ] Delete `docfork_provider.py`
- [ ] Update `providers/__init__.py` if it re-exports these
- [ ] Remove or update `tests/unit/test_provider_orchestration.py` tests that assert Deepcon/Docfork order

**Definition of Done:** Provider modules removed. No imports of Deepcon or Docfork remain.

---

### 29.4 — Update documentation

**LOE:** ~0.5 day

Update all docs to reflect the 2-provider model. Remove references to Deepcon and Docfork.

**Source Files:**
- `README.md`
- `AGENTS.md`
- `docs/TAPPS_MCP_SETUP_AND_USE.md`
- `docs/ARCHITECTURE_CACHE_AND_RAG.md`
- `addenda.md`
- `docs/planning/epics/EPIC-16-DOCUMENTATION-BACKEND-RESILIENCE.md` (add "superseded by Epic 29" note)

**Tasks:**
- [ ] Update README doc lookup section: Context7 + LlmsTxt only
- [ ] Update AGENTS.md `tapps_lookup_docs` / `tapps_research` descriptions
- [ ] Remove Deepcon/Docfork from setup guides and env var lists
- [ ] Add note to Epic 16: "Epic 29 simplifies to 2 providers (Context7 + LlmsTxt)."

**Definition of Done:** All user-facing docs describe 2-provider model. No Deepcon/Docfork references.

---

### 29.5 — Update Epic README and dependency graph

**LOE:** ~0.25 day

Add Epic 29 to the epics overview and dependency graph.

**Source Files:**
- `docs/planning/epics/README.md`

**Tasks:**
- [ ] Add Epic 29 row to Epic Overview table
- [ ] Add to dependency graph: Epic 29 depends on Epic 2, Epic 16

**Definition of Done:** Epic 29 visible in planning docs.
