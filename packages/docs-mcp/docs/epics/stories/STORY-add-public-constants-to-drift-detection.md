# Add public constants to drift detection

## What

Add public constants to drift detection

## Where

- `packages/docs-mcp/src/docs_mcp/validators/drift.py:160-165`
- `api_surface.py:46-53`

## Acceptance

- [ ] 1. Extend _get_public_names to include APISurface.constants
2. Include public constants (MAX_RETRIES
- [ ] DEFAULT_TIMEOUT
- [ ] TypeAlias) in drift coverage
3. Add test/internal constants to _DEFAULT_IGNORE_PATTERNS (e.g.
- [ ] constants matching `_*`
- [ ] `test_*`)
4. Document rationale for constant inclusion in docstring
5. All existing tests pass; new tests cover constant drift detection
6. Code reviewed and merged to master
