# Migration: `<old_tool_name>` → `<new_tool_name>`

**Removed in**: vX.Y.Z  
**Deprecated in**: vA.B.C (YYYY-MM-DD)  
**Linear**: TAP-XXXX  

---

## What changed

<!-- One paragraph: what the old tool did, why it was removed or renamed, and what the replacement does differently. -->

## Migration steps

1. Replace every call to `<old_tool_name>(...)` with `<new_tool_name>(...)`.
2. Update parameter names / types if the signature changed:

   | Old parameter | New parameter | Notes |
   |---|---|---|
   | `old_param` | `new_param` | Brief explanation |

3. Verify the return shape — list any field renames or removals:

   | Old field | New field | Notes |
   |---|---|---|
   | `old_field` | `new_field` | Brief explanation |

## Example

**Before**:
```python
result = await tapps_<old_tool_name>(param="value")
```

**After**:
```python
result = await tapps_<new_tool_name>(new_param="value")
```

## Consumers affected

<!-- List known downstream projects or agents that called this tool. Update when known. -->

- [ ] tapps-mcp internal (checklist, doctor, etc.)
- [ ] docs-mcp
- [ ] AGENTS.md / deployed agent scaffolding
