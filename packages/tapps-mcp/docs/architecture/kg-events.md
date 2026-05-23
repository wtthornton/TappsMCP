# Brain KG Event Taxonomy (TAP-2003)

tapps-mcp fires brain KG events for significant pipeline actions so that subsequent agents can discover history via `brain_get_neighbors`. Events are **best-effort**: a brain outage or call failure must never block the tool that fires them.

## How events are stored

Events are routed through `BrainBridge.record_kg_event()` which serialises the payload to JSON and calls the brain's `brain_record_event` MCP tool. Results are queryable via `brain_get_neighbors(entity_ids=[<entity_id>], hops=2)`.

## Event types

### `quality_gate_fail`

Fired by `tapps_quality_gate` whenever the gate returns at least one failure.

**Entities**

| type   | id                          | description                       |
|--------|-----------------------------|-----------------------------------|
| `file` | absolute file path (str)    | The file that failed the gate     |
| `rule` | category name (str)         | The quality category that failed  |

**Edges**

| src         | predicate  | dst           |
|-------------|------------|---------------|
| file path   | `violates` | category name |

**Payload**

```json
{
  "score":     <float>,   // actual category score
  "category":  <str>,     // same as rule entity id
  "threshold": <float>    // required threshold
}
```

**One event per failure**: if a file fails both `security` and `complexity`, two
separate `quality_gate_fail` events are emitted, each with its own
`file VIOLATES rule` edge.

**Query example**

```python
# What quality rules has src/auth.py violated?
brain_get_neighbors(entity_ids=["src/auth.py"], hops=2)

# What files have violated the "security" rule?
brain_get_neighbors(entity_ids=["security"], hops=2)
```

### `deprecated_tool_call`

Fired by `tapps_memory` on every action call (TAP-1992). Used to measure
tapps_memory usage frequency before the 3-phase deprecation (TAP-1990).

**Entities**

| type   | id                                | description                          |
|--------|-----------------------------------|--------------------------------------|
| `tool` | `"tapps_memory:<action>"` (str)   | The specific tapps_memory action used |

No edges or payload.

## Extending the taxonomy

To add a new event type:

1. Add a `record_kg_event()` call (fire-and-forget, wrap in `asyncio.create_task()`).
2. Document the new type in this file under its own `### <event_type>` heading.
3. Follow the pattern: entities → edges → payload.
4. Keep it best-effort: `try/except Exception: pass` around both the bridge lookup
   and the coroutine body.
