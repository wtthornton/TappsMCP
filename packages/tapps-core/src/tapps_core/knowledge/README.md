# tapps_core.knowledge

Knowledge & documentation lookup system (Epic 2) plus Knowledge-Graph (KG)
key derivation.

## Library docs lookup

Most modules here back `tapps_lookup_docs`: Context7 client, cache, fuzzy
matching, content normalisation, RAG-safety, and import analysis. See each
module's docstring.

## KG entity-key derivation (`kg_keys.py`)

`kg_keys.entity_uuid(project_id, entity_type, canonical_name)` derives a
**deterministic** UUIDv5 for a Knowledge-Graph entity:

```python
from tapps_core.knowledge.kg_keys import entity_uuid

eid = entity_uuid("tapps-mcp", "module", "tapps_core.brain_bridge")
# always the same UUID for the same triple
```

The same `(project_id, entity_type, canonical_name)` triple always maps to
the same UUID. This is what makes `BrainBridge.upsert_entity` (TAP-1947)
idempotent: re-running `docs_generate_architecture` re-derives the *same*
entity IDs instead of inserting duplicate `kg_entities` rows.

### The namespace is immutable

`KG_NAMESPACE` (the UUIDv5 namespace root) **must never change**. Every
entity UUID is derived from it; changing it re-derives every ID and orphans
all existing `kg_entities` / `kg_edges` / `kg_evidence` rows in the brain.

### Input contract

`entity_type` is a closed vocabulary (`package`, `module`, `symbol`, `doc`)
and `canonical_name` is a dotted identifier or POSIX path. Neither may
contain the `|` field separator (`KEY_SEPARATOR`); within that domain the
key construction is injective, so distinct entities never collide.
