# GitHub Security Features

## CodeQL Code Scanning

CodeQL performs semantic analysis on code:

```yaml
- uses: github/codeql-action/init@v3
  with:
    languages: ["python"]
    queries: +security-extended

- uses: github/codeql-action/autobuild@v3

- uses: github/codeql-action/analyze@v3
```

### Incremental Analysis (GA September 2025)

CodeQL analyzes only changed files on PRs, making it fast enough
to be a required check.

### Copilot Autofix

CodeQL findings can include Copilot-generated fix suggestions.
Enable in repository settings under Code Security.

## Secret Scanning

Detects committed secrets (API keys, tokens, passwords):

- **Push protection** (GA August 2025) blocks pushes containing secrets
- **Custom patterns** allow organization-specific secret formats
- **Delegated bypass** lets admins review and allow specific pushes
- **Validity checks** verify if detected secrets are still active

## Dependabot

### Security Updates

Automatic PRs for vulnerable dependencies:

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      security:
        applies-to: security-updates
        patterns: ["*"]
```

### uv Support (GA 2025)

Dependabot natively supports `uv` as a package ecosystem:
- Version updates: March 2025
- Security updates: December 2025

## Artifact Attestations

SLSA Level 2-3 supply chain security:

```yaml
- uses: actions/attest-build-provenance@v2
  with:
    subject-path: dist/*.whl
```

Verify attestations:

```bash
gh attestation verify dist/package.whl --owner org
```

## Security Overview Dashboard

Organization-level view of all security alerts across repositories.
Available on GitHub Enterprise Cloud.

## Copilot Security Integration

Copilot's coding agent includes built-in security checks:

- **Self-review security**: Agent runs CodeQL, secret scanning, and dependency
  checks before opening PRs
- **Copilot Autofix**: Automatically generates fix suggestions for CodeQL
  findings, Dependabot alerts, and secret scanning alerts
- **Security campaign mode**: Organization-wide Copilot Autofix campaigns
  to remediate vulnerability classes at scale

## GitHub Secret Protection and Code Security

Standalone products (2026) for organizations:
- **Secret Protection** — secret scanning + push protection
- **Code Security** — CodeQL + Dependabot + security overview

## SLSA Provenance (Built-in)

GitHub Actions now has built-in SLSA provenance generation:

```yaml
- uses: actions/attest-build-provenance@v2
  with:
    subject-path: dist/*.whl
```

- SLSA Level 2-3 attestations generated automatically
- Verify with `gh attestation verify`
- Supports both file artifacts and container images
- Provenance stored in GitHub's attestation API
