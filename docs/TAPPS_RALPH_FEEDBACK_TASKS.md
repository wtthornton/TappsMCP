# Task List: Ralph Feedback on tapps-mcp upgrade

External feedback from the Ralph project (a bash-first, non-greenfield publisher
with hand-tuned `CLAUDE.md` loop semantics) flagged `tapps_upgrade` as too
invasive. This is the actionable backlog for tapps-mcp. Items are ordered by
blast-radius: P0 items are blocking for any non-greenfield consumer; P2 items
are polish.

## P0 — `upgrade_skip_files` granularity

**Problem.** `upgrade_skip_files` is the only escape hatch but it's
all-or-nothing for Claude artifacts:
[`upgrade.py:154`](../packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py#L154)
gates `claude_md` only, and everything else (settings, hooks, agents, skills,
python-quality rule, agent-scope rule, pipeline rule) runs regardless.

**Fix.** Honor skip entries per-file for every artifact `_upgrade_platform`
writes. Acceptance criteria:

- `.claude/rules/python-quality.md` skippable.
- `.claude/rules/agent-scope.md` skippable.
- `.claude/rules/tapps-pipeline.md` skippable.
- `AGENTS.md` already supported — keep.
- `.mcp.json` skippable.
- The Karpathy block inside `CLAUDE.md` skippable via a reserved token
  (e.g. `CLAUDE.md#karpathy`) without skipping the whole file.
- Each artifact reports `skipped (upgrade_skip_files)` in the result dict so
  consumers can see it took effect.

Relevant: [`upgrade.py:144-188`](../packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py#L144-L188),
[`settings.py:760-765`](../packages/tapps-core/src/tapps_core/config/settings.py#L760-L765).

## P0 — Gate Python-specific rules on project language

**Problem.** `generate_claude_python_quality_rule` runs unconditionally in
`_upgrade_platform`. Ralph is bash-first with a small Python SDK, and
non-Python consumers (Node, Go, Rust) get a `.claude/rules/python-quality.md`
they'll never use. No language detection gates it.

**Fix.** Before writing `python-quality.md`:
- Use the existing project-type detector (`project/type_detector.py`,
  `profiler.py`) to check for Python signals: `pyproject.toml`, `*.py` files
  outside `.venv`, or explicit `languages: [python]` in `.tapps-mcp.yaml`.
- If none, skip with result `"skipped (no python detected)"`.
- Allow override: `force_python_rule: true` in config for mixed repos that
  want it anyway.

Same treatment should apply at init time
([`init.py:793-795`](../packages/tapps-mcp/src/tapps_mcp/pipeline/init.py#L793-L795)).

## P1 — `--mcp-only` narrow upgrade mode

**Problem.** Ralph's ask was literal: "just wire the MCP server into this
repo, skip everything else." No flag supports that today. `minimal` at init
time still writes AGENTS.md + CLAUDE.md + settings.json. `upgrade` has no
minimal flag at all.

**Fix.** Add `mcp_only: bool = False` to the upgrade entrypoint (MCP tool
arg + CLI flag). When true:

- Write/merge the `tapps-mcp` entry into `.mcp.json`.
- Merge `mcp__tapps-mcp` and `mcp__tapps-mcp__*` into
  `.claude/settings.json` permissions.
- Skip CLAUDE.md, AGENTS.md, hooks, agents, skills, all rules, CI, governance.
- Return a result dict that clearly shows what was skipped and why so
  consumers know they took the narrow path.

Document in CLAUDE.md's "Upgrade & Rollback" section.

## P1 — Opt-in AGENTS.md when CLAUDE.md is the source of truth

**Problem.** Ralph declares `CLAUDE.md` as single source of truth for agent
behavior. `tapps_upgrade` unconditionally creates `AGENTS.md` at root, which
creates dual-truth drift. The user can skip via `upgrade_skip_files:
[AGENTS.md]` but the default is still "create."

**Fix.** Detect explicit opt-out:
- If the top of `CLAUDE.md` contains a sentinel like
  `<!-- tapps:agents-md-disabled -->`, do not create AGENTS.md.
- Alternatively (or additionally), add
  `create_agents_md: bool = true` to `.tapps-mcp.yaml` and honor it at
  upgrade time (not just init time). Today this only gates init behavior.
- When skipping, emit a `next_steps` hint pointing to the sentinel or the
  config key, so future upgrades don't silently revert.

## P1 — Opt-in Karpathy block

**Problem.** The Karpathy guidelines get appended to a hand-tuned
`CLAUDE.md` every consumer gets. The block is content-idempotent after
[726d2c1](../../../commit/726d2c1) (good), but the SHA-pinned marker
(`<!-- BEGIN: karpathy-guidelines c9a44ae -->`) and the full 50-line section
still show up in diffs the first time, and re-show on every source-SHA bump.
For projects like Ralph with carefully-tuned loop semantics, this is noise.

**Fix.** Make it opt-in via `.tapps-mcp.yaml`:

```yaml
claude_md:
  include_karpathy_guidelines: false  # default true for now; flip after a deprecation window
```

When false:
- `install_or_refresh` is skipped.
- If a prior install left the block in place, the next upgrade **does not
  remove it** (respect prior consent) but logs a hint that the user has
  opted out for future installs.

Relevant: `pipeline/karpathy_block.py`.

## P2 — `.mcp.json` consent gate

**Problem.** `_upgrade_platform` regenerates `.mcp.json`
([`upgrade.py:131-142`](../packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py#L131-L142))
whenever `_validate_config_file` finds anything it doesn't like. For
consumers who are not dogfooding the MCP-in-Claude-Code integration, this
hooks tapps-mcp into every session without explicit opt-in.

**Fix.** Split `mcp_config` into two modes:
- `required` (today's behavior): auto-regenerate missing/broken entries.
- `on-demand`: only regenerate when `tapps_init --with-mcp-json` or
  `tapps_upgrade --refresh-mcp-json` is passed.

Default for greenfield: `required`. Default when the upgrade detects an
existing `.mcp.json` without a `tapps-mcp` server entry: `on-demand`, so we
don't barge in.

## P2 — Documentation

**Problem.** `upgrade_skip_files` is mentioned in one line of
[CLAUDE.md:173](../CLAUDE.md#L173) with no examples. Ralph's author had to
read the Python to figure out what tokens it accepts.

**Fix.** Expand the "Upgrade & Rollback" section of CLAUDE.md (and the
consumer-facing `AGENTS.md` template) with:
- Full list of skippable tokens once P0 lands.
- Example `.tapps-mcp.yaml` snippet showing the common "I have my own
  CLAUDE.md, just give me the MCP tools" setup.
- Pointer to `--mcp-only` once P1 lands.

## P2 — Detect hand-tuned platform artifacts before overwriting

**Problem.** `generate_subagent_definitions`, `generate_skills`, and the
rule generators pass `overwrite=True`. That's fine for `tapps-*` prefixed
files (tapps owns them), but the rule files (`python-quality.md`,
`agent-scope.md`, `tapps-pipeline.md`) live in the consumer's
`.claude/rules/` alongside their own rule files. If a consumer edits one,
upgrade silently reverts it.

**Fix.** Before overwriting any rule file:
- Compute content hash of last-shipped version and compare to current on-disk
  content.
- If they differ, the consumer has edited it. Either:
  - Skip with a clear message + `next_steps` to add it to `upgrade_skip_files`.
  - Or write the new version to `<name>.new` and leave the original alone.
- Store the last-shipped-hash in `.tapps-mcp.yaml` under a managed
  `upgrade_manifest` block (already exists for CI files — extend it).

## Out of scope (not a tapps-mcp issue)

Ralph's corrupted `PreToolUse` entry at `.claude/settings.json:46-54` is in
their own hand-edited settings. Not caused by our merge logic — verified by
reading `_bootstrap_claude_settings`, which merges permissions only, not
hook stanzas. They should delete the stray entry themselves.

---

## Suggested rollout order

1. **P0 skip-file granularity** — unblocks every non-greenfield consumer
   today. Low risk, pure addition.
2. **P0 language gate on Python rules** — removes cross-ecosystem confusion.
3. **P1 `--mcp-only`** — gives Ralph (and similar consumers) the exact
   narrow install they asked for; also valuable for CI containers that only
   need the MCP server.
4. **P1 AGENTS.md opt-out + Karpathy opt-in** — respects hand-tuned
   CLAUDE.md workflows.
5. **P2 items** — polish, can ship with 2.12 or later.

All P0+P1 changes need test coverage in
`packages/tapps-mcp/tests/unit/test_upgrade*.py` with at least one case per
skip token and one end-to-end `mcp_only=True` snapshot.
