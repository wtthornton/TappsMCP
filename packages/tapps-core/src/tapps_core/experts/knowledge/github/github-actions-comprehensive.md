# GitHub Actions Comprehensive Guide

## Overview

GitHub Actions is a CI/CD platform integrated with GitHub repositories. This guide
covers workflow security, CI patterns for Python projects, reusable workflows,
artifacts v4, release automation, performance optimization, and production best
practices.

## Workflow Security

### Action Version Pinning

Always SHA-pin third-party actions to prevent supply chain attacks.
GitHub recommends **immutable actions** -- pinning to full SHA ensures
the action code cannot change after you reference it:

```yaml
# Bad - mutable tag can be redirected to malicious code
- uses: actions/checkout@v4

# Good - SHA-pinned to specific release (actions/checkout v4.2.2)
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2
```

Key SHA pins for common actions (as of early 2026):

| Action | Version | SHA |
|---|---|---|
| actions/checkout | v4.2.2 | `11bd71901bbe5b1630ceea73d27597364c9af683` |
| actions/setup-python | v5.4.0 | `a26af69be951a213d495a4c3e4e4022e16d87065` |
| actions/upload-artifact | v4.6.0 | `65c4c4a1ddee5b72f698fdd19549f0f0fb45cf08` |
| actions/download-artifact | v4.3.0 | `fa0a91b85d4f404e444e00e005971372dc801d16` |
| actions/cache | v4.2.0 | `1bd1e32a3bdc45362d1e726936510720a7c30a57` |

Use Dependabot to auto-update SHA pins:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "ci"
```

### Minimal Permissions

Always declare explicit permissions at the workflow or job level:

```yaml
permissions:
  contents: read
  pull-requests: write
```

Never use `permissions: write-all`. The default token has broad permissions
that violate least-privilege. Set `permissions: {}` at workflow level and
grant per-job:

```yaml
permissions: {}  # default deny

jobs:
  test:
    permissions:
      contents: read
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

  deploy:
    permissions:
      contents: read
      id-token: write
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
```

### Secret Management

Prefer OIDC over long-lived secrets for cloud provider authentication:

```yaml
permissions:
  id-token: write
  contents: read

steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::role/GitHubActions
      aws-region: us-east-1
```

### Environment Protection Rules

Use environments for deployment gates:

```yaml
jobs:
  deploy-prod:
    environment:
      name: production
      url: https://app.example.com
    runs-on: ubuntu-latest
    steps:
      - run: deploy.sh
```

Configure protection rules in repository settings:
- Required reviewers (1+ approvals)
- Wait timer (delay before deployment)
- Branch restrictions (only from main)

### Workflow Token Hardening

```yaml
# Restrict GITHUB_TOKEN scope per job
jobs:
  lint:
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false  # don't leave token in git config
```

## Python CI Patterns

### Standard Python CI Workflow

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
      fail-fast: false
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v --cov=src --cov-report=xml
      - name: Upload coverage
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-${{ matrix.python-version }}
          path: coverage.xml
```

### Using uv for Fast Dependency Installation

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install uv
        run: pip install uv
      - name: Install dependencies
        run: uv sync --frozen
      - name: Run tests
        run: uv run pytest tests/ -v --cov
      - name: Lint
        run: uv run ruff check src/
      - name: Type check
        run: uv run mypy --strict src/
```

### Dependency Caching

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
    cache: "pip"  # Built-in pip caching

# Or for uv
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- uses: astral-sh/setup-uv@v4
  with:
    enable-cache: true
```

### Parallel Test Execution

Split tests across multiple runners for speed:

```yaml
strategy:
  matrix:
    shard: [1, 2, 3, 4]
steps:
  - run: pytest tests/ --splits 4 --group ${{ matrix.shard }}
```

Using pytest-xdist within a single runner:

```yaml
steps:
  - run: pytest tests/ -n auto -v
```

### Quality Gate Job

```yaml
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install uv && uv sync --frozen
      - name: Ruff lint
        run: uv run ruff check src/ --output-format=github
      - name: Ruff format
        run: uv run ruff format --check src/
      - name: Type check
        run: uv run mypy --strict src/
      - name: Security scan
        run: uv run bandit -r src/ --skip B101
      - name: Test with coverage
        run: uv run pytest tests/ --cov=src --cov-report=term-missing --cov-fail-under=80
```

## Concurrency Control

### Cancel Superseded Runs

Cancel previous runs on the same PR when new commits are pushed:

```yaml
concurrency:
  group: ci-${{ github.head_ref || github.ref }}
  cancel-in-progress: true
```

### Environment Concurrency

Prevent concurrent deployments to the same environment:

```yaml
concurrency:
  group: deploy-production
  cancel-in-progress: false  # don't cancel running deployments
```

## Artifacts v4

### Key Changes from v3

Artifacts v3 was deprecated January 2025. Key v4 differences:

- Artifacts are immutable (no overwrite with same name)
- 10 GB per artifact, 50 GB per repository
- `retention-days` default is 90 (configurable)
- `if-no-files-found: warn` prevents silent failures
- Cross-workflow artifact sharing via API

### Upload Artifacts

```yaml
- name: Upload test results
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: test-results-${{ matrix.python-version }}
    path: |
      coverage.xml
      test-results/
    retention-days: 30
    if-no-files-found: warn

- name: Upload quality report
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: quality-report
    path: .tapps-mcp/reports/
    retention-days: 30
    if-no-files-found: ignore
```

### Download Artifacts

```yaml
- name: Download artifact
  uses: actions/download-artifact@v4
  with:
    name: quality-report
    path: reports/
```

### Merge Multiple Artifacts

```yaml
- name: Download all coverage reports
  uses: actions/download-artifact@v4
  with:
    pattern: coverage-*
    merge-multiple: true
    path: coverage/
```

## Conditional Jobs

### Branch-Based Conditions

```yaml
jobs:
  lint:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - run: ruff check src/

  deploy:
    needs: [test, lint]
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - run: deploy.sh
```

### Path-Based Triggers

```yaml
on:
  push:
    paths:
      - "src/**"
      - "tests/**"
      - "pyproject.toml"
    paths-ignore:
      - "docs/**"
      - "*.md"
```

### Skip CI

```yaml
# Skip workflow for documentation-only changes
on:
  push:
    paths-ignore:
      - "**.md"
      - "docs/**"
      - ".github/ISSUE_TEMPLATE/**"
```

## Job Outputs and Communication

### Passing Data Between Jobs

```yaml
jobs:
  check:
    runs-on: ubuntu-latest
    outputs:
      score: ${{ steps.quality.outputs.score }}
      passed: ${{ steps.quality.outputs.passed }}
    steps:
      - id: quality
        run: |
          SCORE=85
          echo "score=$SCORE" >> "$GITHUB_OUTPUT"
          if [ "$SCORE" -ge 70 ]; then
            echo "passed=true" >> "$GITHUB_OUTPUT"
          else
            echo "passed=false" >> "$GITHUB_OUTPUT"
          fi

  gate:
    needs: check
    if: needs.check.outputs.passed == 'true'
    runs-on: ubuntu-latest
    steps:
      - run: echo "Quality gate passed with score ${{ needs.check.outputs.score }}"
```

### Job Summary

```yaml
steps:
  - name: Post summary
    run: |
      echo "## Quality Report" >> $GITHUB_STEP_SUMMARY
      echo "| File | Score | Status |" >> $GITHUB_STEP_SUMMARY
      echo "|---|---|---|" >> $GITHUB_STEP_SUMMARY
      echo "| src/main.py | 85 | Pass |" >> $GITHUB_STEP_SUMMARY
```

## Reusable Workflows

### Creating a Reusable Workflow

Support up to 10 nested levels and 50 total workflows per run:

```yaml
# .github/workflows/quality-reusable.yml
name: Quality Check
on:
  workflow_call:
    inputs:
      preset:
        type: string
        default: standard
        description: "Quality gate preset"
      python-version:
        type: string
        default: "3.12"
    secrets:
      CODECOV_TOKEN:
        required: false

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ inputs.python-version }}
      - run: pip install uv && uv sync --frozen
      - run: uv run ruff check src/
      - run: uv run mypy --strict src/
      - run: uv run pytest tests/ --cov --cov-fail-under=80
```

### Calling a Reusable Workflow

```yaml
# .github/workflows/ci.yml
jobs:
  quality:
    uses: ./.github/workflows/quality-reusable.yml
    with:
      preset: strict
      python-version: "3.12"
    secrets: inherit
```

### Cross-Repository Reusable Workflows

```yaml
jobs:
  quality:
    uses: org/shared-workflows/.github/workflows/python-quality.yml@main
    with:
      preset: standard
    secrets: inherit
```

## Timeout Configuration

Always set `timeout-minutes` to prevent hung jobs:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - run: pytest tests/ -v

  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - run: deploy.sh
```

Step-level timeouts:

```yaml
steps:
  - name: Run slow tests
    timeout-minutes: 5
    run: pytest tests/ -m slow -v
```

## Runner Updates

### Ubuntu 24.04 as Default

As of late 2025, `ubuntu-latest` maps to **Ubuntu 24.04 (Noble Numbat)**.
Ubuntu 22.04 remains available as `ubuntu-22.04` but will be deprecated.
Update workflows that depend on specific OS packages or library versions.

```yaml
jobs:
  test:
    runs-on: ubuntu-latest  # Ubuntu 24.04
    steps:
      - uses: actions/checkout@v4
      - run: pytest tests/ -v

  # Pin to specific version if needed
  legacy:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
```

### Larger Runners (GA)

GitHub-hosted larger runners are generally available for all plans.
Available in 4, 8, 16, 32, and 64 vCPU configurations:

```yaml
jobs:
  heavy-test:
    runs-on: ubuntu-latest-16-cores  # 16 vCPU, 64 GB RAM
    steps:
      - uses: actions/checkout@v4
      - run: pytest tests/ -n 16 -v

  # GPU runners for ML workloads
  ml-test:
    runs-on: ubuntu-gpu-nc4as-t4  # NVIDIA T4 GPU
    steps:
      - run: python -m pytest tests/gpu/ -v
```

Larger runner labels:
- `ubuntu-latest-4-cores`, `ubuntu-latest-8-cores`, `ubuntu-latest-16-cores`
- `ubuntu-latest-32-cores`, `ubuntu-latest-64-cores`
- GPU variants available for ML workloads

### Arm64 Runners

GitHub Arm64 runners (GA 2025) are 37% cheaper and free for public repos:

```yaml
jobs:
  test:
    runs-on: ubuntu-24.04-arm
    steps:
      - uses: actions/checkout@v4
      - run: pytest tests/ -v
```

### Matrix with Multiple Architectures

```yaml
strategy:
  matrix:
    include:
      - runner: ubuntu-latest
        arch: x64
      - runner: ubuntu-24.04-arm
        arch: arm64
      - runner: ubuntu-latest-16-cores
        arch: x64-large
```

## Release Automation

### Automated PyPI Publishing

```yaml
name: Release
on:
  push:
    tags:
      - "v*"

permissions:
  id-token: write  # for trusted publishing

jobs:
  publish:
    runs-on: ubuntu-latest
    environment:
      name: pypi
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build
      - run: python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

### Release Notes Generation

```yaml
name: Release Notes
on:
  release:
    types: [published]

jobs:
  notes:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Generate changelog
        run: |
          git log --pretty=format:"- %s" $(git describe --tags --abbrev=0 HEAD^)..HEAD > RELEASE_NOTES.md
      - name: Update release
        run: gh release edit ${{ github.event.release.tag_name }} --notes-file RELEASE_NOTES.md
        env:
          GH_TOKEN: ${{ github.token }}
```

### Docker Image Publishing

```yaml
name: Docker
on:
  push:
    tags: ["v*"]

jobs:
  docker:
    runs-on: ubuntu-latest
    permissions:
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.ref_name }}
```

## Composite Actions

### Creating a Composite Action

```yaml
# .github/actions/setup-python-project/action.yml
name: Setup Python Project
description: Install Python and project dependencies
inputs:
  python-version:
    default: "3.12"
    description: Python version
runs:
  using: composite
  steps:
    - uses: actions/setup-python@v5
      with:
        python-version: ${{ inputs.python-version }}
    - name: Install uv
      shell: bash
      run: pip install uv
    - name: Install dependencies
      shell: bash
      run: uv sync --frozen
```

### Using the Composite Action

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: ./.github/actions/setup-python-project
    with:
      python-version: "3.12"
  - run: uv run pytest tests/ -v
```

## TappsMCP CI Integration

### Quality Report Upload

```yaml
- name: Run TappsMCP validation
  run: uv run tapps-mcp validate --preset standard --output json > report.json

- name: Upload quality report
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: quality-report
    path: report.json
    retention-days: 30
    if-no-files-found: ignore
```

### TappsMCP as MCP Server in CI

```yaml
- name: Start TappsMCP server
  run: |
    uv run tapps-mcp serve &
    sleep 2
  env:
    TAPPS_MCP_PROJECT_ROOT: ${{ github.workspace }}
```

## Performance Optimization

### Caching Strategies

```yaml
# Cache uv packages
- uses: astral-sh/setup-uv@v4
  with:
    enable-cache: true
    cache-dependency-glob: "uv.lock"

# Cache pre-commit hooks
- uses: actions/cache@v4
  with:
    path: ~/.cache/pre-commit
    key: pre-commit-${{ hashFiles('.pre-commit-config.yaml') }}
```

### Minimize Checkout Depth

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 1  # shallow clone for speed
```

### Conditional Step Execution

```yaml
- name: Run expensive checks
  if: github.event_name == 'push' && github.ref == 'refs/heads/main'
  run: uv run pytest tests/ -m slow -v
```

## SLSA Provenance Generation

GitHub Actions has built-in support for SLSA (Supply-chain Levels for
Software Artifacts) provenance generation, providing verifiable build
attestations:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
      attestations: write
    steps:
      - uses: actions/checkout@v4
      - run: python -m build
      - name: Generate SLSA provenance
        uses: actions/attest-build-provenance@v2
        with:
          subject-path: dist/*

  # For container images
  docker:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      packages: write
      attestations: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v6
        id: push
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}:latest
      - uses: actions/attest-build-provenance@v2
        with:
          subject-name: ghcr.io/${{ github.repository }}
          subject-digest: ${{ steps.push.outputs.digest }}
          push-to-registry: true
```

Verify provenance:

```bash
gh attestation verify dist/package.whl --owner org-name
gh attestation verify oci://ghcr.io/org/image:tag --owner org-name
```

## Anti-Patterns

### No Permissions Block

Missing permissions defaults to broad token access. Always declare explicitly.

### Mutable Action References

Using `@v4` or `@main` instead of SHA pins enables supply chain attacks.

### Missing Timeouts

Without `timeout-minutes`, hung jobs consume Actions minutes indefinitely.

### Sequential Independent Jobs

Running lint, test, and security scan sequentially wastes time.
Use separate jobs that run in parallel.

### Hardcoded Secrets

Never put secrets in workflow files. Use repository or environment secrets.

## Quick Reference

| Pattern | Configuration |
|---|---|
| SHA-pin actions | `uses: action@sha  # v4.1.1` |
| Minimal permissions | `permissions: { contents: read }` |
| Cancel superseded | `concurrency: { group: ..., cancel-in-progress: true }` |
| Timeout | `timeout-minutes: 15` |
| Artifact upload | `uses: actions/upload-artifact@v4` |
| Reusable workflow | `uses: ./.github/workflows/reusable.yml` |
| OIDC auth | `permissions: { id-token: write }` |
| Arm64 runner | `runs-on: ubuntu-24.04-arm` |
| Path filter | `on: push: paths: ["src/**"]` |
