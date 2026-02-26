# GitHub Actions Best Practices (2026)

## Action Version Pinning

Always SHA-pin third-party actions to prevent supply chain attacks:

```yaml
# Bad — mutable tag
- uses: actions/checkout@v4

# Good — SHA-pinned
- uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
```

Use Dependabot to auto-update SHA pins with `package-ecosystem: "github-actions"`.

## Minimal Permissions

Always declare explicit permissions at the workflow or job level:

```yaml
permissions:
  contents: read
  pull-requests: write
```

Never use `permissions: write-all`. The default token has broad permissions
that violate least-privilege.

## Concurrency Groups

Cancel superseded runs on the same PR:

```yaml
concurrency:
  group: ci-${{ github.head_ref || github.ref }}
  cancel-in-progress: true
```

## Artifacts v4

Artifacts v3 was deprecated January 2025. Use `actions/upload-artifact@v4`
and `actions/download-artifact@v4`. Key differences:

- Artifacts are immutable (no overwrite with same name)
- 10 GB per artifact, 50 GB per repository
- `retention-days` default is 90 (configurable)
- `if-no-files-found: warn` prevents silent failures

## Arm64 Runners

GitHub Arm64 runners (GA 2025) are 37% cheaper and free for public repos:

```yaml
runs-on: ubuntu-24.04-arm
```

## Reusable Workflows

Support up to 10 nested levels and 50 total workflows per run:

```yaml
# Caller
jobs:
  quality:
    uses: ./.github/workflows/quality-reusable.yml
    with:
      preset: strict
    secrets: inherit

# Callee
on:
  workflow_call:
    inputs:
      preset:
        type: string
        default: standard
```

## Timeout Configuration

Always set `timeout-minutes` to prevent hung jobs:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 15
```

## Secret Management

Prefer OIDC over long-lived secrets:

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-arn: arn:aws:iam::role/GitHubActions
```
