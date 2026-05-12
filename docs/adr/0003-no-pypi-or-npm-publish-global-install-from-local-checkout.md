# 3. No PyPI or npm publish — global install from local checkout

Date: 2026-05-02

## Status

accepted

## Context

tapps-mcp, tapps-core, docs-mcp, and the npm wrapper packages could in principle be published to public registries (PyPI / npm) for installation by consuming projects. The default expectation in most Python tooling is that a `pyproject.toml` package gets `uv publish`-ed. However, this repo is single-author and the only consumers today are the author's own portfolio of projects, all installed by the same operator on the same machines.

## Decision

**Do not publish to PyPI or npm.** All packages in this monorepo (tapps-mcp, tapps-core, docs-mcp, and any npm wrappers) are installed globally from the local checkout via `uv tool install -e packages/tapps-mcp` (and equivalents). The release flow stops at `git push` + `git tag` + `gh release create`. No `uv publish`, no `twine upload`, no `npm publish`, no registry-upload CI job. Consumers pick up new versions by reinstalling from the local path.

## Consequences

**Positive:** No registry account, credentials, or yank-on-mistake risk. No version-skew between "what's on disk" and "what's on PyPI" — local checkout is canonical.

**Negative:** External users (people the author doesn't onboard manually) cannot `pip install tapps-mcp`. Acceptable given the current consumer set.

**Neutral:** If the consumer set ever broadens, this ADR is a candidate for being superseded — track via a deprecation, not a silent reversal.
