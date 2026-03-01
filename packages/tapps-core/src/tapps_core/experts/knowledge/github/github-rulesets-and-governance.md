# GitHub Rulesets and Repository Governance

## Rulesets vs Branch Protection

Rulesets (GA 2025) replace legacy branch protection rules:

| Feature | Branch Protection | Rulesets |
|---------|------------------|----------|
| API | REST only | REST + UI |
| Scope | Per-branch | Multiple branches, tags |
| Stacking | No | Multiple rulesets stack |
| Bypass | Per-rule | Bypass actors list |
| Organization | No | Org-wide rulesets |

## Creating Rulesets via API

```bash
gh api repos/{owner}/{repo}/rulesets --method POST \
  --input ruleset.json
```

```json
{
  "name": "Main Protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/main"],
      "exclude": []
    }
  },
  "rules": [
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "required_review_thread_resolution": true
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          {"context": "CI"}
        ]
      }
    },
    {"type": "required_linear_history"}
  ]
}
```

## Rule Types

- `pull_request` — require PRs with reviews
- `required_status_checks` — CI must pass
- `required_linear_history` — no merge commits
- `creation` / `deletion` — prevent branch create/delete
- `non_fast_forward` — prevent force pushes
- `merge_queue` — enable merge queue

## CODEOWNERS

`.github/CODEOWNERS` defines required reviewers per path:

```
# Default
*                    @org/core-team

# Security files
**/security/**       @org/security-team
SECURITY.md          @org/security-team

# CI
.github/workflows/** @org/devops-team
```

Last matching pattern wins. CODEOWNERS requires branch protection or
rulesets with "Require review from Code Owners" enabled.

## Bypass Actors

Rulesets support bypass actors (users, teams, apps) that can skip rules:

```json
{
  "bypass_actors": [
    {"actor_id": 1, "actor_type": "Team", "bypass_mode": "always"}
  ]
}
```

## Organization Rulesets

Available on Team plan and above (GA June 2025):

```bash
gh api orgs/{org}/rulesets --method POST --input org-ruleset.json
```

Organization rulesets apply across all repositories matching conditions.
