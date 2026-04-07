---
name: MCP large response handling patterns (2025-2026)
description: Comprehensive research on MCP spec limits, production patterns, resource primitives, FastMCP SDK support, and client behavior for 85K+ character tool responses like docs_generate_api
type: project
---

Research completed 2026-04-06. Focused on docs_generate_api generating 85K+ chars.

**Why:** docs_generate_api returns full content inline. At 85K chars (~21K tokens), Claude Code bails out to file-save instead of displaying the content. Need a strategy to fix this.

**How to apply:** Reference when deciding how to change docs_generate_api and other large-content generator tools.

---

## 1. MCP Spec: Response Size Limits

**The MCP specification (2025-11-25) sets NO hard limit on tool response size.**

The spec defines tool call responses as `CallToolResult` with a `content` array of `TextContent | ImageContent | EmbeddedResource`. There is no `maxContentSize` field, no pagination protocol for tool results, and no negotiated size cap.

What the spec DOES have:
- **Pagination for list endpoints only**: `tools/list`, `resources/list`, `prompts/list` support `cursor`-based pagination (client sends `cursor`, server returns `nextCursor`). Tool *calls* have no equivalent.
- **Resources primitive** (`resources/read`): designed for arbitrary-size content with MIME type. Not paginated either, but clients treat it differently (download vs. inject-into-context).
- **Progress notifications**: `$/progress` for long-running ops (no relation to size).
- **Tasks primitive** (2025-11-25): async/long-running ops. Not for chunking responses.

**Practical limit comes from the client, not the spec:**
- Claude Code: dumps to file when response > ~50K chars (observed behavior). No documented threshold.
- Cursor: injects into context up to its window limit, then truncates silently.
- VS Code Copilot: similar to Cursor.

The threshold is client-specific and undocumented. Claude Code's behavior (save to file) is actually the most honest — Cursor may silently truncate.

---

## 2. Production MCP Server Patterns for Large Content

### Pattern A: Write-to-file, return path + summary (RECOMMENDED for docs generators)

The tool writes the file directly (when `can_write_to_project()` is true) and returns only metadata in the response: path, size, section count, next steps.

**Already used in docs_generate_api when `output_path` is provided.** The gap is the no-`output_path` case returns full content.

Fix: Make `output_path` a **required default behavior** with a computed path (e.g., `docs/api-reference.md`), and return a summary response instead of content. Caller can override to `output_path=""` for explicit content-return.

```python
# Computed default path when output_path is empty
default_output = "docs/api-reference.md"  # or derive from source_path
```

### Pattern B: Pagination via tool parameters (cursor pattern)

Add `offset: int = 0, limit: int = 0` parameters. When `limit=0`, write to file. When `limit > 0`, return a slice.

**Not recommended for docs generators.** Partial markdown is useless — you can't act on the first 200 lines of API docs. Pagination is good for list tools (memory search, issue lists) but not document generators.

### Pattern C: MCP Resources instead of tool responses

Register the generated content as an MCP resource with a URI like `docs://api/{source_path}`. Tool call returns the URI; client reads via `resources/read`.

**Elegant but has a critical gap:** Claude Code does not automatically read MCP resources returned from tool calls. The LLM would need to explicitly call a resource-read action. Resources are intended for pre-existing, stable data (config, status) not dynamically generated content.

The `server_resources.py` pattern in DocsMCP (docs://status, docs://config, docs://coverage) shows resources work well for lightweight, read-only status data — not for 85K generated docs.

### Pattern D: Content-return with FileManifest (already built)

The existing `FileManifest` / `build_generator_manifest()` infrastructure in `tapps_core.common.file_operations` handles Docker/read-only mode. In Docker mode, full content IS returned (because the AI must write it). In direct-write mode, full content should NOT be returned.

**The current bug**: `docs_generate_api` ALWAYS puts `content` in the response dict, even when `written_path` is set (line 458: `"content": content`). It only omits content in the `output_path` specified but not writable case.

### Pattern E: Response size configuration / negotiation

No MCP standard for this. Could add a `.docsmcp.yaml` setting `max_inline_content_chars: 40000`. Client-side, no negotiation possible because the spec has no mechanism.

---

## 3. MCP Resources — Fit for This Use Case?

**Resources in the MCP spec:**
- URI-based (`docs://status`, `file:///path/to/doc.md`)
- Returned as `ReadResourceResult` with `contents: list[TextResourceContents | BlobResourceContents]`
- Intended for ambient data the LLM can read (not generate-on-demand)
- `@mcp.resource("docs://coverage")` pattern: sync or async, returns str

**Dynamic resource templates** (2025-11-25): `@mcp.resource("docs://api/{source_path}")` — the URI contains a variable. The client can read `docs://api/packages/tapps-mcp/src` and get the generated docs.

This IS theoretically possible with FastMCP. The tool could:
1. Generate the content
2. Write it to `self._cache[uri]`
3. Return the URI in the tool response
4. Client reads via resource

**But**: Claude Code's UX for resources is separate from tool results. The LLM sees the tool result and would need to follow up with a resource read. This adds a round-trip and forces the LLM to understand the indirection. Not seamless.

**Verdict**: Resources work for the `docs://status`, `docs://config`, `docs://coverage` pattern (small, stable). Not a natural fit for 85K generated docs that the user wants written to disk anyway.

---

## 4. FastMCP Python SDK Support

FastMCP (the Python SDK used by both TappsMCP and DocsMCP) as of 2025-11-25:

- **No built-in streaming for tool responses** in stdio transport. Streamable HTTP supports SSE but tool results are still delivered as a single `CallToolResult`.
- **`ctx.report_progress()`**: sends progress notifications, not content chunks.
- **Resources**: `@mcp.resource("uri://pattern")` with template variable support.
- **No `max_response_size` on the tool decorator**.
- **`structuredContent` field** (2025-06-18+): tools can return both text and a structured dict. Still one atomic response.

The "correct" FastMCP answer for large content is: write to file, return a metadata summary.

---

## 5. Best Practices 2025-2026

From the mcp-patterns.md knowledge base (anti-patterns section):
> "Unbounded output: Returning megabytes of data overwhelms the LLM's context"

From observed production MCP server behavior (GitHub MCP, filesystem MCP, etc.):

1. **File-write-first for generators**: Any tool that generates a document should write it and return path + summary. Only return inline content when no filesystem access is available (Docker/content-return mode).

2. **Size threshold gates**: Check `len(content) > THRESHOLD` and switch behavior.
   - Threshold: ~20K chars (~5K tokens) is a reasonable inline limit for doc fragments.
   - 85K chars is 5-10x over any reasonable inline limit.

3. **Summary-first response**: Always return `content_length`, `sections_generated`, `module_count`, `written_to` (path) as the primary response. The LLM can relay this to the user without reading the content.

4. **`output_path` should default to auto-computed**: For `docs_generate_api`, compute a sensible default like `docs/api/{package_name}.md` rather than requiring the caller to always pass it.

5. **Explicit `return_content=True` flag**: When the caller explicitly wants inline content (rare), allow it with a boolean flag. Default to `False` for large generators.

---

## 6. Client Behavior at Scale

### Claude Code
- Injects tool result into context as a `<tool_result>` block.
- When the result is very large (observed threshold ~50-60K chars), it writes to a temp file and shows the path instead.
- The "save to file" behavior is Claude Code's own UX choice, not the MCP spec.
- Consequence: the LLM never sees the content, only the file path. If the tool also wrote the file to `output_path`, that's fine. If not (no `output_path` given), the content is stranded in a temp file.

### Cursor
- Injects into context up to a soft limit, then silently truncates.
- Silent truncation is worse than Claude Code's behavior — the LLM thinks it read everything.

### VS Code Copilot (agent mode)
- Similar to Cursor. Truncates silently at context window boundaries.
- No special handling for large tool results.

### Key insight
Claude Code's save-to-file behavior is the most honest but still problematic: if `docs_generate_api` returned content only (no file write), the content lands in a temp file the user never intended, and the LLM thinks "I returned the docs" but the user has no idea where they are.

**The right answer is always**: write the file to the expected path AND return a compact summary.

---

## 7. Recommended Solution for docs_generate_api

### Immediate fix: invert the default behavior

Currently: when `output_path=""`, return full content inline.
Fix: when `output_path=""`, auto-compute a path, write the file, return summary.
Escape hatch: `output_path="__inline__"` or `return_inline=True` for programmatic use.

```python
# Auto-compute default output path
if not output_path:
    pkg_name = _derive_package_name(src, root)
    computed_output = f"docs/api/{pkg_name}.md"
else:
    computed_output = output_path

# Write to file (direct-write mode)
if can_write_to_project(root):
    write_path = validator.validate_write_path(computed_output)
    write_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(write_path.write_text, content, encoding="utf-8")
    
    # Return compact summary — NOT full content
    return success_response("docs_generate_api", elapsed_ms, {
        "format": format,
        "depth": depth,
        "module_count": generator.last_module_count,
        "content_length": len(content),
        "written_to": computed_output,
        "next_steps": [
            f"API docs written to {computed_output}.",
            "Review the generated docs and commit.",
        ],
    })

# Content-return mode (Docker): must return full content via FileManifest
return success_response("docs_generate_api", elapsed_ms, {
    "format": format,
    "depth": depth,
    "content_length": len(content),
    "file_manifest": build_generator_manifest(...),
})
```

### Size threshold gate (belt + suspenders)

Even when writing to file, add a guard so inline content is never returned above a threshold:

```python
_MAX_INLINE_CHARS = 20_000  # ~5K tokens

if len(content) > _MAX_INLINE_CHARS and not return_inline:
    # Force file write even if caller didn't request it
    ...
```

### Option comparison for this use case

| Option | Verdict | Notes |
|---|---|---|
| A. Write-to-file + summary | BEST | Already partially implemented. Invert the default. |
| B. Pagination | BAD for docs | Partial markdown is not actionable. |
| C. MCP Resources | INTERESTING but roundabout | Extra round-trip, not seamless in Claude Code. |
| D. FileManifest (Docker mode) | ALREADY DONE | Correct for content-return mode. |
| E. Size config/negotiation | WEAK standalone | Add as defense-in-depth, not primary solution. |

### Which generators need this fix?

All `docs_generate_*` tools that return `"content": content` inline without a written_path guard need review:

- `docs_generate_api` — 85K+ chars confirmed. High priority.
- `docs_generate_readme` — typically 5-15K. Borderline.
- `docs_generate_changelog` — large repos can hit 30K+. Medium priority.
- `docs_generate_onboarding` — typically under 10K.
- `docs_generate_contributing` — typically under 5K.
- `docs_generate_architecture` — HTML, can be 50K+. High priority.
- `docs_generate_interactive_diagrams` — HTML, can be 100K+. High priority.

---

## References

- MCP Spec 2025-11-25: https://modelcontextprotocol.io/specification/2025-11-25
- FastMCP docs: https://gofastmcp.com/
- `packages/tapps-core/src/tapps_core/experts/knowledge/ai-frameworks/mcp-patterns.md` — anti-pattern: "Unbounded output"
- `packages/tapps-core/src/tapps_core/experts/knowledge/software-architecture/mcp-server-architecture.md` — server patterns
- `packages/tapps-core/src/tapps_core/common/file_operations.py` — FileManifest, detect_write_mode
- `packages/docs-mcp/src/docs_mcp/server_helpers.py` — build_generator_manifest, can_write_to_project
- `packages/docs-mcp/src/docs_mcp/server_gen_tools.py` lines 363-469 — current docs_generate_api implementation
