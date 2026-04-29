# Make file scanning async to unblock event loop

## What

Make file scanning async to unblock event loop

## Where

- `packages/docs-mcp/src/docs_mcp/server_val_tools.py:32-112`

## Acceptance

- [ ] 1. Wrap DriftDetector.check() call in asyncio.to_thread() for async execution
2. Prevent blocking file I/O from halting MCP event loop
3. Large project scans no longer block other concurrent requests
4. Response time for parallel requests improves by 5-10x
5. All existing tests pass; new tests verify async behavior
6. Code reviewed and merged to master
