# Repo Workflow (tapps-mcp only)

This file is **specific to the tapps-mcp repo** and is not deployed to consumers via `tapps_upgrade`. Consuming projects have their own workflow conventions; the rules below apply only when working inside this monorepo.

## Commit directly to master — no feature branches, no PRs

For tapps-mcp, commit code changes directly to `master`. Solo-dev workflow on a tool repo.

- Run local validation (tests, quality gate) and `git commit` + `git push` to `master`.
- Do not propose "open a PR for X" or branch-and-PR flows in plans or recommendations.

The pre-push test gate (`.githooks/pre-push`) enforces a green non-slow unit
suite before any push to master. Run `scripts/install-git-hooks.sh` once per
fresh clone to activate it (sets `core.hooksPath=.githooks`). For genuine
emergencies, bypass with `TAPPS_SKIP_PREPUSH=1 git push` — bypasses are
logged to `.tapps-mcp/.bypass-log.jsonl`. Do not bypass for routine work; if
the suite is red, fix it or pause.

The pre-push hook also enforces a **tapps-brain version floor** (TAP-1923):
it reads the `tapps-brain>=X.Y.Z` line from `packages/tapps-core/pyproject.toml`
and blocks the push if the floor is below `3.18.0` (the ADR-0010 minimum,
required to avoid crashes from the v3.18.0 alias removals). The same
`TAPPS_SKIP_PREPUSH=1` bypass applies. Do not lower the floor below `3.18.0`
— if you need to test an older brain, do so in a branch, never on master.

The post-merge auto-sync hook (`.githooks/post-merge`) runs `uv sync
--all-packages` after any merge / pull that touches `pyproject.toml`,
`packages/*/pyproject.toml`, or `uv.lock` — so the project venv stays in
lockstep with the merged tree. When none of those files changed, the hook
exits in <1s. Bypass with `TAPPS_SKIP_POSTMERGE=1` (same `.bypass-log.jsonl`).
Same install path as the pre-push gate (`scripts/install-git-hooks.sh`).
- Still ask before destructive ops (force-push, `reset --hard`) — "no PRs" is a workflow preference, not a green light to skip the destructive-op confirmation rule.
- Linear writes (epics, stories, comments) are unaffected — those go through the `linear-issue` skill as usual.

## All three packages share the same version — use the unified bumper

`packages/tapps-mcp`, `packages/docs-mcp`, and `packages/tapps-core` are
released together and **must always share the same `version =` field in
their `pyproject.toml`**. The npm wrappers (`npm/package.json`,
`npm-docs-mcp/package.json`) and the `<!-- tapps-agents-version: X.Y.Z -->`
stamp in `AGENTS.md` must also match. Drift between these is what
TAP-2129 install-drift and `tapps_upgrade` assume cannot happen — fixing
it after the fact requires re-shipping every divergent consumer.

The pre-push hook (`.githooks/pre-push`) calls
`scripts/bump-versions.py --check` and refuses to push on drift. Run
`scripts/install-git-hooks.sh` once per fresh clone to activate it
(same install path as the test gate). Bypass via `TAPPS_SKIP_PREPUSH=1`,
logged to `.tapps-mcp/.bypass-log.jsonl`. Do not bypass for routine work.

Always bump via the script — never edit `pyproject.toml` versions by hand:

```bash
python3 scripts/bump-versions.py --patch    # 3.10.16 -> 3.10.17
python3 scripts/bump-versions.py --minor    # 3.10.16 -> 3.11.0
python3 scripts/bump-versions.py --major    # 3.10.16 -> 4.0.0
python3 scripts/bump-versions.py --sync     # re-align drifted versions
python3 scripts/bump-versions.py --check    # CI gate (what pre-push runs)
```

The script bumps all three pyprojects, both npm `package.json` files, and
the `AGENTS.md` stamp atomically in one commit, and refuses the bump if
`_CANONICAL_HOOK_MANIFEST` references a phantom hook (the 79ef6e3 /
2e2f378 root cause). `--sync` is the recovery path when something drifts
anyway — re-aligns everything to the current max version without bumping.

## Bump the version when prompt templates change

`tapps_upgrade` decides whether to refresh AGENTS.md / CLAUDE.md by comparing
the `<!-- tapps-agents-version: X.Y.Z -->` stamp against the installed
package version. When the stamps match, the smart-merge is skipped entirely
— even if the template content has changed. This means template changes
that don't bump `packages/tapps-mcp/pyproject.toml` never reach existing
consumers.

When editing anything under `packages/tapps-mcp/src/tapps_mcp/prompts/` —
including the platform rules, agents templates, and obligations block — bump
the patch version in the same commit. The smart-merge logic will then
propagate the change on the consumer's next `tapps_upgrade`, preserving
their customizations to non-canonical sections.

The `EXPECTED_SECTIONS` list in `pipeline/agents_md.py` enumerates the
sections that get fully replaced by template content during merge. If your
edit is to a section in that list, the user's customizations to that
specific section are intentionally overwritten. If you need a section to be
canonical-but-not-listed, add it to `EXPECTED_SECTIONS`.

## Do not publish tapps-mcp to PyPI / npm

tapps-mcp, tapps-core, docs-mcp, and any npm wrappers are **installed globally from the local checkout** (`uv tool install -e packages/tapps-mcp` or `uv tool install --reinstall <local path>`). No PyPI / npm distribution pipeline is in use.

- When releasing a new version, stop after `git push` + `git tag` + `gh release create`.
- Do not suggest `uv publish`, `twine upload`, `npm publish`, or check for publish CI workflows.
- If the user asks how to pick up a new version on their global CLI, point them at reinstalling from the local path — not at any registry.

## How to apply

Both rules describe **this repo's** release shape: a single-author, locally-installed tool. They override the generic Claude Code defaults of "branch + PR" and "publish to a package registry." If you find yourself proposing a feature branch, a PR description, or a registry upload while working in this repo, stop and re-read this file.
