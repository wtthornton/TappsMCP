# Epic 5: Secrets Management

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~2-3 days (1 developer)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that API keys, credentials, and secrets are encrypted at rest, never committed in plaintext, and safely injected into services at runtime.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Deploy SOPS + age for encrypted secrets in git, audit existing Compose files for plaintext secrets, and establish a secrets rotation workflow.

**Tech Stack:** docs-mcp, Python >=3.12

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Trading API keys and Anthropic credentials are currently in environment variables or .env files with no encryption. A git leak or server compromise would expose all credentials.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] SOPS + age installed and age keypair generated
- [ ] All secrets encrypted in git via SOPS
- [ ] No plaintext secrets in Docker Compose files
- [ ] Secrets injected at runtime via file-based Docker secrets
- [ ] Rotation workflow documented

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 5.1 -- Install SOPS and age Keypair

**Points:** 2

Install SOPS and age. Generate age keypair, store private key securely on server only. Configure .sops.yaml for project.

**Tasks:**
- [ ] Implement install sops and age keypair
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Install SOPS and age Keypair is implemented, tests pass, and documentation is updated.

---

### 5.2 -- Encrypt Existing Secrets

**Points:** 2

Audit all .env files and Compose configs for plaintext secrets. Encrypt with SOPS. Update Compose to use file-based secrets.

**Tasks:**
- [ ] Implement encrypt existing secrets
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Encrypt Existing Secrets is implemented, tests pass, and documentation is updated.

---

### 5.3 -- Document Secrets Rotation Workflow

**Points:** 1

Document how to rotate secrets: re-encrypt with SOPS, update Compose, restart services. Add rotation reminders to health monitoring.

**Tasks:**
- [ ] Implement document secrets rotation workflow
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Document Secrets Rotation Workflow is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- age is the modern PGP replacement -- simpler key management
- SOPS encrypts values in-place within YAML/JSON/ENV
- Private key must never be accessible to the AI agent
- See docs/recommendations-2026-server-hardening.md Section 7

**Project Structure:** 7 packages, 73 modules, 279 public APIs

**Key Dependencies:** tapps-core>=1.0.0, mcp[cli]>=1.26.0,<2, click>=8.3.1,<9, jinja2>=3.1.6,<4, gitpython>=3.1.44,<4, pydantic>=2.12.5,<3, structlog>=25.5.0,<26, pyyaml>=6.0.3,<7

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Define what is explicitly out of scope for **Secrets Management**...

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 5 acceptance criteria met | 0/5 | 5/5 | Checklist review |
| All 3 stories completed | 0/3 | 3/3 | Sprint board |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 5.1: Install SOPS and age Keypair
2. Story 5.2: Encrypt Existing Secrets
3. Story 5.3: Document Secrets Rotation Workflow

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Deployment downtime if blue-green not configured | Medium | High | Warning: Mitigation required - no automated recommendation available |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| Files will be determined during story refinement | - | - |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:performance-targets -->
## Performance Targets

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Test coverage | baseline | >= 80% | pytest --cov |

<!-- docsmcp:end:performance-targets -->
