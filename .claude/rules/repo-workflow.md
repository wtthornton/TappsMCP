# Repo Workflow (tapps-mcp only)

This file is **specific to the tapps-mcp repo** and is not deployed to consumers via `tapps_upgrade`. Consuming projects have their own workflow conventions; the rules below apply only when working inside this monorepo.

## Commit directly to master — no feature branches, no PRs

For tapps-mcp, commit code changes directly to `master`. Solo-dev workflow on a tool repo.

- Run local validation (tests, quality gate) and `git commit` + `git push` to `master`.
- Do not propose "open a PR for X" or branch-and-PR flows in plans or recommendations.
- Still ask before destructive ops (force-push, `reset --hard`) — "no PRs" is a workflow preference, not a green light to skip the destructive-op confirmation rule.
- Linear writes (epics, stories, comments) are unaffected — those go through the `linear-issue` skill as usual.

## Do not publish tapps-mcp to PyPI / npm

tapps-mcp, tapps-core, docs-mcp, and any npm wrappers are **installed globally from the local checkout** (`uv tool install -e packages/tapps-mcp` or `uv tool install --reinstall <local path>`). No PyPI / npm distribution pipeline is in use.

- When releasing a new version, stop after `git push` + `git tag` + `gh release create`.
- Do not suggest `uv publish`, `twine upload`, `npm publish`, or check for publish CI workflows.
- If the user asks how to pick up a new version on their global CLI, point them at reinstalling from the local path — not at any registry.

## How to apply

Both rules describe **this repo's** release shape: a single-author, locally-installed tool. They override the generic Claude Code defaults of "branch + PR" and "publish to a package registry." If you find yourself proposing a feature branch, a PR description, or a registry upload while working in this repo, stop and re-read this file.
