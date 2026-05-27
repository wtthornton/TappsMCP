# Skill Authoring Conventions

Reference commit: [mattpocock/skills@b8be62f](https://github.com/mattpocock/skills/commit/b8be62ffacb0118fa3eaa29a0923c87c8c11985c)

This document defines three rules that every shipped skill template in
`platform_skills.py` must satisfy. Skills are deployed to consuming
projects via `tapps_init` / `tapps_upgrade`; these rules keep the
generated files consistent and ensure Claude Code's autoload routing
fires at the right times.

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

1. The skill body is ≤ ~30 lines.
2. The description does **not** name a triggering keyword, context, or
   file type that would legitimately fire during normal agentic work.
3. The skill is a user-invoked utility (e.g. a mode switch, a gate
   check, a pipeline runner) rather than an agent-callable specialist.

**Rationale.** `disable-model-invocation: true` tells the Claude Code
skill router to exclude the skill from autoload consideration entirely.
Without it, short utility skills can match spurious patterns and fire
mid-task, interrupting normal agentic flow. Skills that target specific
contexts or file types (e.g. `tapps-research`, `tapps-review-pipeline`)
should keep autoload enabled so they fire at the right moment; utility
stubs should not.

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

Before adding or modifying a skill in `platform_skills.py`:

- [ ] Description has a capability sentence **and** a "Use when ..." clause
- [ ] Description is ≤ 1 024 characters
- [ ] Short user-only utility skills have `disable-model-invocation: true`
- [ ] Template body is ≤ ~100 lines, or companion `*.md` refs exist
- [ ] Version bumped via `python3 scripts/bump-versions.py --patch` (template changes propagate to consumers only after a version bump)
