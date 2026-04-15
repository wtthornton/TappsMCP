# Epic 39: Agent Credential Vault — Runtime Secrets Management

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** Epic 1 (Core Executor), Epic 4 (Config Proposal Engine)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that agents can securely access external APIs (Home Assistant, SMTP, custom integrations) without embedding credentials in environment variables, Docker images, or LLM prompt context. Dynamically created agents need a zero-restart, API-driven way to manage secrets that follows OWASP LLM security guidance and 2026 best practices for agent credential isolation.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Deliver a first-class secrets management subsystem for AgentForge: encrypted-at-rest credential storage, CRUD API, per-agent scoping with least privilege, tool-level injection (never prompt-level), audit logging, and Docker Compose secrets fallback — enabling new integrations via a single API call with no container rebuild or restart.

**Tech Stack:** docs-mcp, Python >=3.12

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Agents created via POST /agents cannot reach external services unless their credentials are manually added to docker-compose.yml and containers are restarted. This blocks the entire smart-home agent suite (5 agents) and will block every future integration. No major agent framework (LangChain, CrewAI, AutoGen, OpenAI Agents SDK, Claude Agent SDK) ships a built-in secrets vault — this is greenfield infrastructure that pays for itself immediately.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Secrets can be created/read(metadata-only)/updated/deleted via REST API without container restart
- [ ] All secret values encrypted at rest using AES-256-GCM with HKDF-derived keys
- [ ] Secrets scoped per-agent or globally with least-privilege enforcement
- [ ] Credentials injected at tool execution layer — never appear in LLM prompt context (OWASP LLM07/LLM08)
- [ ] Audit log records every secret access (key + scope + timestamp + agent — never the value)
- [ ] Fallback chain: Secrets API → Docker /run/secrets/ mount → environment variables
- [ ] Agent config schema supports credential references (key names not values) with required/optional flags
- [ ] Missing required credentials fail fast with clear error before agent invocation
- [ ] MultiFernet-style key rotation supported without re-encrypting all secrets immediately
- [ ] Existing env-var-based credential injection continues working (backwards compatible)

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 39.1 -- Secrets Data Model and Encrypted Storage

**Points:** 5

Database table for secrets with AES-256-GCM encryption, HKDF key derivation from master secret, scope column (global/agent:{id}), and created/updated/accessed_at timestamps.

**Tasks:**
- [ ] Implement secrets data model and encrypted storage
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Secrets Data Model and Encrypted Storage is implemented, tests pass, and documentation is updated.

---

### 39.2 -- Secrets CRUD API Endpoints

**Points:** 5

POST/GET/PUT/DELETE /secrets endpoints. GET returns metadata only (key, scope, created_at) never values. Create and update accept plaintext values, encrypt before storage. Scoped access validation.

**Tasks:**
- [ ] Implement secrets crud api endpoints
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Secrets CRUD API Endpoints is implemented, tests pass, and documentation is updated.

---

### 39.3 -- Agent Credential References in Config Schema

**Points:** 3

Extend AgentConfig schema with optional credentials field: list of {key, scope, required} objects. Agents declare which credentials they need by key name. Validation at agent creation time warns if referenced secrets don't exist.

**Tasks:**
- [ ] Implement agent credential references in config schema
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Agent Credential References in Config Schema is implemented, tests pass, and documentation is updated.

---

### 39.4 -- Tool-Level Credential Injection in Orchestrator

**Points:** 8

Modify the task invocation pipeline to resolve credential references at tool execution time. Secrets fetched from vault, injected into tool implementation context (HTTP headers, connection strings), never into LLM system/user prompts. This is the critical security boundary.

**Tasks:**
- [ ] Implement tool-level credential injection in orchestrator
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Tool-Level Credential Injection in Orchestrator is implemented, tests pass, and documentation is updated.

---

### 39.5 -- Credential Fallback Chain

**Points:** 3

Three-tier resolution: 1) Secrets API (DB), 2) Docker mounted secrets at /run/secrets/, 3) Environment variables. Log which tier resolved each credential for debugging. Deprecation warnings for env-var tier.

**Tasks:**
- [ ] Implement credential fallback chain
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Credential Fallback Chain is implemented, tests pass, and documentation is updated.

---

### 39.6 -- Key Rotation and MultiFernet Support

**Points:** 3

Support adding new encryption keys without immediate re-encryption. MultiFernet-style decryption tries keys in order. Background task to re-encrypt secrets under current key. Key version tracking.

**Tasks:**
- [ ] Implement key rotation and multifernet support
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Key Rotation and MultiFernet Support is implemented, tests pass, and documentation is updated.

---

### 39.7 -- Audit Trail and Access Logging

**Points:** 3

Every secret read/write/delete logged to audit table: key name, scope, timestamp, requesting agent/user, operation type. Never log the secret value. Query endpoint for audit history with filtering.

**Tasks:**
- [ ] Implement audit trail and access logging
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Audit Trail and Access Logging is implemented, tests pass, and documentation is updated.

---

### 39.8 -- Docker Compose Secrets Integration

**Points:** 2

Document and implement reading from /run/secrets/ mount point. Update docker-compose.yml with secrets: top-level key examples. File-watch capability for hot-reload when mounted secrets change.

**Tasks:**
- [ ] Implement docker compose secrets integration
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Docker Compose Secrets Integration is implemented, tests pass, and documentation is updated.

---

### 39.9 -- Migration Path and Backwards Compatibility

**Points:** 2

Existing ANTHROPIC_API_KEY and other env vars continue working via fallback chain. Migration guide for moving env vars to secrets API. No breaking changes to existing agent definitions.

**Tasks:**
- [ ] Implement migration path and backwards compatibility
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Migration Path and Backwards Compatibility is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- AES-256-GCM via cryptography.hazmat.primitives.ciphers.aead.AESGCM — not Fernet (AES-128-CBC) per 2026 NIST guidance
- HKDF for key derivation from AGENTFORGE_MASTER_KEY env var (the one secret that stays in the environment)
- 96-bit nonces for GCM — never reuse
- OWASP Top 10 for LLM Applications v2.0: LLM07 (System Prompt Leakage) and LLM08 (Excessive Agency) drive the tool-level injection requirement
- No major agent framework has a built-in secrets vault as of 2026 — this is novel infrastructure
- Docker Compose v2 secrets mount to /run/secrets/ as files — app reads on demand
- For future: credential broker pattern with short-lived scoped tokens (OAuth2 client credentials flow)

**Project Structure:** 7 packages, 73 modules, 279 public APIs

**Key Dependencies:** tapps-core>=1.0.0, mcp[cli]>=1.26.0,<2, click>=8.3.1,<9, jinja2>=3.1.6,<4, gitpython>=3.1.44,<4, pydantic>=2.12.5,<3, structlog>=25.5.0,<26, pyyaml>=6.0.3,<7

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- HashiCorp Vault integration (future epic if needed)
- Hardware security module (HSM) support
- Multi-tenant credential isolation (AgentForge is single-tenant)
- Secrets UI in frontend (API-only for now)
- Automatic credential discovery or provisioning

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Zero credentials visible in LLM context (verified via prompt audit) | - | - | - |
| New integration onboarded via single API call (no restart) | - | - | - |
| All secrets encrypted at rest (verified via DB inspection) | - | - | - |
| 100% audit coverage on secret access operations | - | - | - |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:references -->
## References

- OWASP Top 10 for LLM Applications v2.0 (2025)
- NIST SP 800-38D (AES-GCM)
- Python cryptography library AESGCM docs
- Docker Compose secrets specification

<!-- docsmcp:end:references -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 39.1: Secrets Data Model and Encrypted Storage
2. Story 39.2: Secrets CRUD API Endpoints
3. Story 39.3: Agent Credential References in Config Schema
4. Story 39.4: Tool-Level Credential Injection in Orchestrator
5. Story 39.5: Credential Fallback Chain
6. Story 39.6: Key Rotation and MultiFernet Support
7. Story 39.7: Audit Trail and Access Logging
8. Story 39.8: Docker Compose Secrets Integration
9. Story 39.9: Migration Path and Backwards Compatibility

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Master key compromise exposes all secrets — mitigate with hardware-backed key storage roadmap | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Prompt injection could trick agents into calling tools that exfiltrate data even without seeing credentials directly | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Schema migration required for secrets and audit tables | High | High | Warning: Mitigation required - no automated recommendation available |
| Key rotation complexity if many secrets accumulate | Medium | Medium | Warning: Mitigation required - no automated recommendation available |

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
| Acceptance criteria pass rate | 0% | 100% | CI pipeline |
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->
