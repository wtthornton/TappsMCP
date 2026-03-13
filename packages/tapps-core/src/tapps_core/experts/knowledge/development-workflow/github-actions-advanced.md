# GitHub Actions Advanced Best Practices

## Overview

GitHub Actions is GitHub's native CI/CD platform. While basic workflows are straightforward, production-grade pipelines require careful attention to security hardening, artifact management, release automation, and dependency maintenance. This guide covers advanced patterns beyond introductory CI/CD setup.

## Security Hardening

### Least-Privilege Permissions

By default, `GITHUB_TOKEN` has broad read/write access. Always declare the minimum permissions at the workflow level and override per-job only where needed.

```yaml
# Workflow-level: restrict everything to read-only
permissions:
  contents: read

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - run: ruff check .

  release:
    runs-on: ubuntu-latest
    # Job-level: grant write only where needed
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v6
      - run: gh release create "$TAG" --generate-notes
        env:
          GH_TOKEN: ${{ github.token }}
```

**Key permissions and when to use them:**

| Permission | Use Case |
|---|---|
| `contents: read` | Checkout code (default for CI) |
| `contents: write` | Create releases, push tags |
| `packages: write` | Push to GHCR or GitHub Packages |
| `id-token: write` | OIDC trusted publishing (PyPI, cloud providers) |
| `security-events: write` | Upload SARIF to Security tab |
| `pull-requests: write` | Post PR comments, add labels |

### OIDC Trusted Publishing

Avoid long-lived API tokens for package registries. Use OpenID Connect (OIDC) to get short-lived credentials directly from GitHub's identity provider.

```yaml
# PyPI trusted publishing -- no API token needed
permissions:
  id-token: write

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi  # Enables environment protection rules
    steps:
      - uses: actions/download-artifact@v6
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
```

**Setup requirements:**
1. Configure a "trusted publisher" on PyPI under your project settings
2. Match the GitHub repository, workflow file name, and environment name
3. No `password` or `token` input needed -- the action handles OIDC exchange

### Environment Protection Rules

Use GitHub environments to gate deployments with required reviewers, wait timers, or branch restrictions.

```yaml
jobs:
  publish-testpypi:
    environment: testpypi  # No approval needed
    # ...

  publish-pypi:
    needs: publish-testpypi
    environment: pypi  # Requires manual approval
    # ...
```

**Configure in:** Repository Settings > Environments > [name] > Protection rules

## Artifact Management

### Version Compatibility

Always match `upload-artifact` and `download-artifact` major versions. Artifacts uploaded by one major version cannot be downloaded by a different one.

```yaml
# CORRECT: matching versions
- uses: actions/upload-artifact@v6    # Upload
- uses: actions/download-artifact@v6  # Download

# BROKEN: version mismatch
- uses: actions/upload-artifact@v6    # Upload with v6
- uses: actions/download-artifact@v4  # Cannot retrieve v6 artifacts
```

### Build-Once, Deploy-Many Pattern

Build artifacts once and reuse them across test and deployment jobs to ensure what you test is what you ship.

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - run: uv build
      - uses: actions/upload-artifact@v6
        with:
          name: dist
          path: dist/

  test-install:
    needs: build
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/download-artifact@v6
        with:
          name: dist
          path: dist/
      - run: pip install dist/*.whl
        shell: bash
      - run: my-cli --version

  publish:
    needs: test-install
    steps:
      - uses: actions/download-artifact@v6
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
```

### Build Artifact Verification

Inspect artifacts in CI logs for auditability.

```yaml
- run: uv build
- name: Verify build artifacts
  run: |
    ls -la dist/
    python -m zipfile -l dist/*.whl | head -20
```

## Release Automation

### Tag-Version Validation

Prevent publishing a package whose version doesn't match the git tag. This catches forgotten version bumps.

```yaml
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - name: Verify tag matches package version
        run: |
          TAG_VERSION="${GITHUB_REF#refs/tags/v}"
          PKG_VERSION=$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
          if [ "$TAG_VERSION" != "$PKG_VERSION" ]; then
            echo "::error::Tag version ($TAG_VERSION) does not match pyproject.toml version ($PKG_VERSION)"
            exit 1
          fi
```

### Automated GitHub Releases

Create GitHub Releases automatically after a successful publish, with auto-generated changelogs.

```yaml
github-release:
  needs: publish-pypi
  runs-on: ubuntu-latest
  permissions:
    contents: write
  steps:
    - uses: actions/checkout@v6
    - uses: actions/download-artifact@v6
      with:
        name: dist
        path: dist/
    - name: Create GitHub Release
      env:
        GH_TOKEN: ${{ github.token }}
      run: |
        gh release create "${{ github.ref_name }}" \
          --title "${{ github.ref_name }}" \
          --generate-notes \
          dist/*
```

**`--generate-notes`** auto-generates a changelog from merged PRs and commits since the last release.

### Multi-Stage Publishing Pipeline

Gate production publishing behind a staging step to catch issues early.

```yaml
# Flow: validate → build → test-install → TestPyPI → PyPI → GitHub Release
jobs:
  validate:
    # Tag-version check
  build:
    needs: validate
  test-install:
    needs: build
    # Cross-platform wheel install verification
  publish-testpypi:
    needs: test-install
    environment: testpypi
  publish-pypi:
    needs: publish-testpypi
    environment: pypi
  github-release:
    needs: publish-pypi
```

## Matrix Strategies

### fail-fast Considerations

```yaml
strategy:
  fail-fast: false  # CI: run all cells for full visibility
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
    python-version: ["3.12", "3.13", "3.14"]
```

| Setting | When to Use |
|---|---|
| `fail-fast: false` | CI/testing -- you want to see all failures across the matrix, not just the first |
| `fail-fast: true` | Release pipelines -- any failure should halt immediately to prevent a bad publish |

### Conditional Steps Within a Matrix

Run expensive or platform-specific steps only on certain matrix combinations.

```yaml
- name: Upload coverage
  if: matrix.os == 'ubuntu-latest' && matrix.python-version == '3.12'
  uses: codecov/codecov-action@v5
```

## Docker Image Workflows

### Dockerfile Linting

Catch anti-patterns before building with hadolint.

```yaml
jobs:
  lint-dockerfile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: hadolint/hadolint-action@v3.2.1
        with:
          dockerfile: Dockerfile
```

**Common issues hadolint catches:**
- Missing `--no-install-recommends` on `apt-get install`
- Using `latest` tags in base images
- Running as root without explicit `USER` instruction
- Multiple `RUN` layers that could be consolidated

### Vulnerability Scanning with Trivy

Scan built images for known CVEs and upload results to GitHub's Security tab.

```yaml
scan:
  runs-on: ubuntu-latest
  permissions:
    security-events: write
  steps:
    - uses: actions/checkout@v6
    - uses: docker/setup-buildx-action@v3
    - uses: docker/build-push-action@v6
      with:
        context: .
        load: true
        tags: my-image:scan
        cache-from: type=gha
    - uses: aquasecurity/trivy-action@master
      with:
        image-ref: my-image:scan
        format: sarif
        output: trivy-results.sarif
        severity: CRITICAL,HIGH
    - uses: github/codeql-action/upload-sarif@v3
      if: always()
      with:
        sarif_file: trivy-results.sarif
```

### Smart Path Triggers

Trigger Docker workflows not just on Dockerfile changes, but also when the code it packages changes.

```yaml
on:
  pull_request:
    paths:
      - "Dockerfile"
      - "docker-compose.yml"
      - "pyproject.toml"    # Dependency changes affect the image
      - "src/**"            # Source changes affect the image
```

### Docker Build Caching

Use GitHub Actions cache for fast incremental Docker builds.

```yaml
- uses: docker/build-push-action@v6
  with:
    context: .
    push: ${{ github.event_name == 'push' }}
    tags: ${{ steps.meta.outputs.tags }}
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

### Semver Image Tagging

Generate multiple tags from a single version tag push.

```yaml
- uses: docker/metadata-action@v6
  id: meta
  with:
    images: ghcr.io/${{ github.repository }}
    tags: |
      type=semver,pattern={{version}}       # v1.2.3 → 1.2.3
      type=semver,pattern={{major}}.{{minor}} # v1.2.3 → 1.2
      type=sha                                # sha-abc1234
```

## Concurrency and Efficiency

### Concurrency Groups

Cancel redundant workflow runs when new commits are pushed to the same branch or PR.

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

**When NOT to use `cancel-in-progress`:**
- Release/publish workflows (never cancel a publish mid-flight)
- Workflows with side effects (database migrations, deployments)

### Job Dependencies

Structure jobs as a DAG (directed acyclic graph) to maximize parallelism while maintaining correctness.

```yaml
jobs:
  lint:          # Runs first, fast
  test:
    needs: lint  # Runs after lint passes
  build:
    needs: test  # Runs after all tests pass
```

## Dependabot Configuration

### Ecosystem Selection

Use the correct ecosystem for your toolchain. Using `pip` when your project uses `uv` means Dependabot targets the wrong lockfile.

```yaml
version: 2
updates:
  # Match your actual package manager
  - package-ecosystem: "uv"      # For uv-based Python projects
    directory: "/"
    schedule:
      interval: "weekly"

  # Track GitHub Actions versions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"

  # Track base image updates in Dockerfiles
  - package-ecosystem: "docker"
    directory: "/"
    schedule:
      interval: "weekly"
```

### Dependency Grouping

Reduce PR noise by grouping related minor/patch updates into a single PR.

```yaml
- package-ecosystem: "uv"
  directory: "/"
  schedule:
    interval: "weekly"
  groups:
    dev-dependencies:
      patterns:
        - "pytest*"
        - "mypy"
        - "ruff"
        - "types-*"
      update-types:
        - "minor"
        - "patch"
```

## Coverage and Quality Gates

### Enforcing Coverage Thresholds in CI

Configure coverage thresholds in your project config and enforce them in CI, not just locally.

```yaml
# In pyproject.toml
[tool.coverage.report]
fail_under = 80

# In GitHub Actions
- name: Run tests with coverage
  run: uv run pytest tests/unit --cov=my_package --cov-report=xml -v
- name: Verify coverage threshold
  run: uv run coverage report --fail-under=80
```

### Separating Unit and Integration Tests

Run unit and integration tests as separate steps for clearer failure diagnosis.

```yaml
- name: Run unit tests
  run: uv run pytest tests/unit --cov=my_package --cov-report=xml -v
- name: Run integration tests
  run: uv run pytest tests/integration -v
```

## Common Pitfalls

### Anti-Patterns

1. **Overly permissive `GITHUB_TOKEN`**: Always set `permissions` at the workflow level
2. **Mismatched artifact action versions**: Keep `upload-artifact` and `download-artifact` on the same major version
3. **Wrong Dependabot ecosystem**: Match your actual package manager (`uv`, not `pip`)
4. **Missing path triggers on Docker workflows**: Source code changes affect the built image
5. **`fail-fast: true` in CI test matrices**: Hides failures on other platforms
6. **`fail-fast: false` in release pipelines**: Allows partial failures to continue
7. **No tag-version validation**: Leads to publishing packages with mismatched versions
8. **Long-lived API tokens**: Use OIDC trusted publishing where available
9. **No concurrency groups**: Wastes runner minutes on superseded commits
10. **Skipping TestPyPI**: Publish to a staging registry before production

### Debugging Workflows

- Use `::error::` and `::warning::` annotations to surface issues in the PR checks UI
- Add `if: always()` to cleanup steps that must run even after failures
- Use `actions/upload-artifact` to save logs or reports from failed runs
- Set `ACTIONS_STEP_DEBUG=true` in repository secrets for verbose step output

## Workflow Templates Reference

### Minimal Python CI

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy --strict src/
      - run: uv run pytest --cov -v
```

### Release Pipeline Skeleton

```yaml
name: Release
on:
  push:
    tags: ["v*"]
permissions:
  contents: write
  id-token: write
jobs:
  validate:    # Tag matches pyproject.toml version
  build:       # uv build → upload-artifact
  test-install: # download-artifact → pip install → smoke test
  publish-testpypi:
    environment: testpypi
    # pypa/gh-action-pypi-publish with repository-url
  publish-pypi:
    needs: publish-testpypi
    environment: pypi
    # pypa/gh-action-pypi-publish
  github-release:
    needs: publish-pypi
    # gh release create --generate-notes
```

### Docker Build + Scan

```yaml
name: Docker
on:
  push:
    tags: ["v*"]
  pull_request:
    paths: ["Dockerfile", "src/**"]
permissions:
  packages: write
  contents: read
  security-events: write
jobs:
  lint-dockerfile:  # hadolint
  build:            # docker/build-push-action with gha cache
  scan:             # trivy → SARIF upload (PRs only)
```
