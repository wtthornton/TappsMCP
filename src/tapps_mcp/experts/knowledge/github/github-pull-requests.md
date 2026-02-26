# GitHub Pull Requests

## PR Templates

Single-file template at `.github/PULL_REQUEST_TEMPLATE.md`:

```markdown
## Summary
<!-- Brief description of changes -->

## Changes
-

## Test Plan
- [ ] Tests pass locally
- [ ] Lint clean

## Breaking Changes
None
```

## Auto-Merge

Auto-merge allows PRs to merge automatically when all checks pass:

```bash
gh pr merge --auto --squash "PR_URL"
```

Requirements:
- Branch protection rules or rulesets must be configured
- All required status checks must pass
- Required approvals must be met

## Merge Queues

Merge queues batch PRs and test them together:

```yaml
# In rulesets
rules:
  - type: merge_queue
    parameters:
      merge_method: squash
      min_entries_to_merge: 1
      max_entries_to_merge: 5
```

Trigger CI with `merge_group` event:

```yaml
on:
  merge_group:
  pull_request:
```

## Dependabot PR Management

### Grouped Updates (GA July 2025)

```yaml
groups:
  security-updates:
    applies-to: security-updates
    patterns: ["*"]
  minor-and-patch:
    applies-to: version-updates
    update-types: ["minor", "patch"]
```

### Auto-Merge Dependabot PRs

```yaml
- uses: dependabot/fetch-metadata@v2
- if: steps.metadata.outputs.update-type != 'version-update:semver-major'
  run: gh pr merge --auto --squash "$PR_URL"
```

## Draft PRs

Create PRs as drafts for work-in-progress:

```bash
gh pr create --draft --title "WIP: Feature"
```

## Stacked PRs

Chain PRs by setting base branch to another PR's branch:

```bash
gh pr create --base feature-part1 --head feature-part2
```
