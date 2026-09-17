# Skill Authoring Conventions

Reference commit: [mattpocock/skills@b8be62f](https://github.com/mattpocock/skills/commit/b8be62ffacb0118fa3eaa29a0923c87c8c11985c)

This document defines three rules that every shipped skill template must
satisfy. Skills are deployed to consuming projects via `tapps_init` /
`tapps_upgrade`; these rules keep the generated files consistent and
ensure Claude Code's autoload routing fires at the right times.

## Where a skill actually lives (frontmatter/wiring vs. body)

A shipped `CLAUDE_SKILLS` entry is split across two places:

- **Frontmatter + dict wiring** — `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py`.
  This is where a skill's key is added to the `CLAUDE_SKILLS` dict, and where
  any Python-side logic (loader helpers, marker resolution) lives.
- **Body text** — a package-data Markdown file under
  `packages/tapps-mcp/src/tapps_mcp/pipeline/assets/claude_skills/<skill-name>.md`.
  This is the file you edit for wording, structure, or steps.

`platform_skills.py` loads each body via `_load_claude_skill(skill_name)`,
which calls `_read_claude_skill_asset()` to read
`assets/claude_skills/<skill_name>.md` through `importlib.resources` (with a
`sys.frozen` fallback that reads the file directly next to the module, for
the PyInstaller-frozen binary build). The loader then resolves the body's
`{{model:<role>}}` marker, if present, via `resolve_role_model()` — so a body
that needs to name a model role (e.g. which model a sub-task should run on)
never bakes a resolved model string into the `.md` file; `MODEL_ROLES` stays
the single place a model changes.

**CLAUDE_AGENTS** (`packages/tapps-mcp/src/tapps_mcp/pipeline/platform_subagents.py`)
and the docs-automation dicts (`packages/tapps-mcp/src/tapps_mcp/pipeline/platform_docs_automation.py`)
follow the identical split: frontmatter/wiring in the `platform_*.py` module,
bodies in their own `assets/` subdirectory (`assets/claude_agents/` for
CLAUDE_AGENTS; `assets/claude_doc_agents/` and `assets/claude_docs_skills/`
for the docs-automation dicts). Each module carries its own small
`_read_*_asset()` / loader pair mirroring the one in `platform_skills.py`.

**So: to change what a skill says, edit the `.md` file under `assets/`. To
add a new skill, change which skills are enabled, or change how a skill is
loaded, edit the owning `platform_*.py` module.** Emitted output is
unaffected by this split — a project running `tapps_init` / `tapps_upgrade`
sees byte-identical generated files either way.

---

## Rule 1 — Use-when trigger in every `description:` field

**Rule.** Every `description:` field begins with one capability sentence
and ends with exactly one sentence beginning with "Use when ..." that
lists the trigger keywords, contexts, or file types.

**Cap.** 1 024 characters total.

**Rationale.** Claude Code uses the `description:` YAML field as the
primary signal when deciding which skill to autoload. Without a
"Use when ..." clause the router has no keyword anchor and either fires
the skill too broadly (on any tool call that matches the capability
sentence) or never fires it at all. The pattern is derived from the
mattpocock/skills corpus (pinned SHA above), which showed consistent
autoload precision when the trigger clause appeared at the end of the
description string.

**Template shape:**

```
description: >-
  <One sentence: what the skill does.> Use when <keywords / contexts /
  file types that should trigger autoload>.
```

**Examples:**

```yaml
# Good — capability + explicit trigger
description: >-
  Look up library documentation and research best practices via
  Context7. Use when writing code that uses an external library or
  when you need API reference, usage examples, or version-specific
  guidance before writing implementation code.

# Bad — capability only, no trigger
description: >-
  Look up library documentation and research best practices via Context7.
```

---

## Rule 2 — `disable-model-invocation: true` for user-only utility skills

**Rule.** Add `disable-model-invocation: true` to the frontmatter of
any skill that satisfies **all three** of the following:

1. The skill body is ≤ ~30 lines **or** the skill is a long, user-gated
   planning flow that must never autoload mid-task (e.g. `/tapps-wayfind`
   decision maps — TAP-5500).
2. The description does **not** name a triggering keyword, context, or
   file type that would legitimately fire during normal agentic work
   **or** (for long planning skills) the skill is intentionally
   slash-invoked only.
3. The skill is a user-invoked utility (mode switch, gate check, pipeline
   runner) **or** a user-gated planning skill (wayfind chart/work), rather
   than an agent-callable specialist that should autoload.

**Rationale.** `disable-model-invocation: true` tells the Claude Code
skill router to exclude the skill from autoload consideration entirely.
Without it, short utility skills can match spurious patterns and fire
mid-task, interrupting normal agentic flow. Long planning skills that
drive Linear map/decision ops likewise must not interrupt implementable
work — agents invoke them explicitly when the route is foggy.
Skills that target specific contexts or file types (e.g. `tapps-research`,
`tapps-review-pipeline`) should keep autoload enabled so they fire at the
right moment; utility stubs and wayfind-style planning skills should not.

**Known candidates** (as of the TAP-2487 audit):

- `tapps-gate` (deprecated; gate check, ≤10 lines)
- `tapps-validate` (deprecated; validate command, ≤10 lines)
- `tapps-engagement` (mode switch, ≤5 lines)
- `tapps-score` (deprecated; score command, ≤10 lines)
- `tapps-report` (deprecated; report command, ≤10 lines)

---

## Rule 3 — Progressive-disclosure threshold at ~100 lines

**Rule.** Any skill template that grows past ~100 lines must split deep
reference content into sibling `*.md` files loaded on demand, rather
than inlining everything in the frontmatter body.

**Rationale.** Claude Code loads skill files into context at autoload
time. A 200-line inline skill body costs ~3 000 tokens of context on
every matching tool call, even when the agent only needed the first
paragraph. Splitting deep content (examples, full option tables,
troubleshooting steps) into companion `*.md` files defers that token
cost until the agent explicitly reads the file, which is the correct
time. The threshold of ~100 lines is conservative; skills that are
consistently under 60 lines in practice have no obligation to split.

**Split shape:**

```
skills/
  tapps-research.md          # frontmatter + short description + USAGE section
  tapps-research-reference.md  # full option table, examples, troubleshooting
```

The primary skill file references the companion with a relative path:

```markdown
For full option reference, see [tapps-research-reference.md](tapps-research-reference.md).
```

---

## Checklist for new skill templates

Before adding or modifying a skill body (`assets/claude_skills/<name>.md`) or
its wiring (`pipeline/platform_skills.py`):

- [ ] Description has a capability sentence **and** a "Use when ..." clause
- [ ] Description is ≤ 1 024 characters
- [ ] Short user-only utility skills have `disable-model-invocation: true`
- [ ] Template body is ≤ ~100 lines, or companion `*.md` refs exist
- [ ] Version bumped via `python3 scripts/bump-versions.py --patch` (template changes propagate to consumers only after a version bump)
