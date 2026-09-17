# Skill Authoring Conventions

Reference commit: [mattpocock/skills@b8be62f](https://github.com/mattpocock/skills/commit/b8be62ffacb0118fa3eaa29a0923c87c8c11985c)

This document defines three rules that every shipped skill template must
satisfy. Skills are deployed to consuming projects via `tapps_init` /
`tapps_upgrade`; these rules keep the generated files consistent and
ensure Claude Code's autoload routing fires at the right times.

## Where a skill actually lives (frontmatter/wiring vs. body)

A shipped `CLAUDE_SKILLS` entry is split across two places — and the split
is the opposite of what you'd guess if you assume the Python dict carries
the content:

- **Body text, including its frontmatter** — a package-data Markdown file
  under `packages/tapps-mcp/src/tapps_mcp/pipeline/assets/claude_skills/<skill-name>.md`.
  This is the file you edit for wording, structure, steps, `description:`,
  `allowed-tools:`, and `disable-model-invocation:` — **Rule 1 and the
  `disable-model-invocation` checklist item below both apply to this file**,
  not to `platform_skills.py`. Check for yourself:
  `head -8 packages/tapps-mcp/src/tapps_mcp/pipeline/assets/claude_skills/tapps-memory.md`
  opens `---` / `name:` / `user-invocable:` / `model: {{model:...}}` /
  `description:` — full frontmatter, inline in the `.md`. All 24 files
  under `assets/claude_skills/` (23 per-skill bodies plus the shared
  domain-skill template below) open the same way.
- **Dict wiring only** — `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py`.
  Each entry is one line, e.g.
  `CLAUDE_SKILLS["tapps-memory"] = _load_claude_skill("tapps-memory")`.
  `platform_skills.py` injects no frontmatter and no body text here; it only
  decides which skill keys exist and loads their already-complete `.md` files.

`_load_claude_skill(skill_name)` calls `_read_claude_skill_asset()` to read
`assets/claude_skills/<skill_name>.md` through `importlib.resources` (with a
`sys.frozen` fallback that reads the file directly next to the module, for
the PyInstaller-frozen binary build), then resolves the body's
`{{model:<role>}}` marker via `resolve_role_model()` so a body that names a
model role never bakes a resolved model string into the `.md` file —
`MODEL_ROLES` stays the single place a model changes. **Substitution can
fail, on purpose**: an unknown role (a typo'd `{{model:no-such-role}}`)
makes `resolve_role_model()` raise `RoleResolutionError` at load time rather
than silently falling back to a default model. **A missing asset file fails
the same way** — `_load_claude_skill("foo")` with no
`assets/claude_skills/foo.md` on disk raises an uncaught `FileNotFoundError`
at import time. Both are load-time crashes, not something a generated
project can hit at runtime, but they mean a bad skill registration breaks
every `tapps-mcp` invocation, not just the one skill.

**CLAUDE_AGENTS** (`packages/tapps-mcp/src/tapps_mcp/pipeline/platform_subagents.py`)
carries the split one step further: `_read_claude_agent_asset()` is a bare
read with **no marker resolution at all** — `assets/claude_agents/*.md`
files hardcode `model: claude-sonnet-5` directly in their own frontmatter,
since agents never need the `{{model:role}}` indirection skills use. The
docs-automation dicts (`platform_docs_automation.py`, bodies under
`assets/claude_doc_agents/` and `assets/claude_docs_skills/`) sit in
between: no `{{model:role}}` marker, but a `{{docs_prefix}}` marker resolved
to the fixed `mcp__nlt-project-docs__` string.

**Not every `CLAUDE_SKILLS` entry has an asset file.** Three —
`tapps-domain-frontend`, `tapps-domain-security`, `tapps-domain-testing` —
have no per-skill `.md` under `assets/claude_skills/`. `platform_domain_skills.py`
generates them at import time from a shared
`assets/claude_skills/_domain_skill_template.md` skeleton plus Python-side
step content (`_DOMAIN_STEP_PLAYBOOK`, `_DOMAIN_FINISH`, and per-domain
extras still defined as Python string literals), merging the result in via
`CLAUDE_SKILLS.update(CLAUDE_DOMAIN_SKILLS)`. That template uses a
**second, unrelated marker family** — `{{skill:name}}`,
`{{skill:description}}`, `{{skill:tools}}`, `{{skill:body}}` — substituted
by `_render_claude_domain_skill()`, and it **hardcodes**
`model: claude-sonnet-5` rather than a `{{model:role}}` marker. To change
one of these three skills, edit `platform_domain_skills.py`; there is no
per-skill `.md` file to edit instead.

**`CLAUDE_SKILLS` and `CURSOR_SKILLS` must stay in lockstep.**
`test_platform_generators.py` asserts `set(CLAUDE_SKILLS) == set(CURSOR_SKILLS)`
and `len(CLAUDE_SKILLS) == len(CURSOR_SKILLS)`. `CURSOR_SKILLS` was **not**
touched by the package-data extraction — its bodies are still inline Python
string literals in `platform_skills.py`. Adding a skill only to
`CLAUDE_SKILLS` (plus its asset file) without adding the matching
`CURSOR_SKILLS["<name>"] = "..."` entry turns that test red.

**So: to change what a skill says, edit the `.md` file under
`assets/claude_skills/`** (the three domain skills are the one exception —
edit `platform_domain_skills.py` instead). **To add a new skill:** add the
asset file, the one-line `CLAUDE_SKILLS["<name>"] = _load_claude_skill("<name>")`
registration, *and* a matching `CURSOR_SKILLS["<name>"]` entry, or the parity
test fails. Emitted output is unaffected by any of this — a project running
`tapps_init` / `tapps_upgrade` sees byte-identical generated files either
way.

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
- [ ] New skill: added the matching `CURSOR_SKILLS["<name>"]` entry too — `test_platform_generators.py` fails otherwise
- [ ] Version bumped via `python3 scripts/bump-versions.py --patch` (template changes propagate to consumers only after a version bump)
