# Epic 43: tapps-brain v3.4.0 — Postgres-Native Memory Layer

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 — High
**Estimated LOE:** ~1 week (1 developer)
**Dependencies:** tapps-brain v3.4.0 local repo at ../tapps-brain

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that AgentForge runs a clean, modern tapps-brain v3.4.0 integration from the start — no SQLite, no legacy shims, no migration debt. The local tapps-brain repo is two versions ahead of the published GitHub release (v3.4.0 vs v3.2.0) and has fully dropped SQLite in favor of Postgres-native persistence with pgvector HNSW, tsvector FTS, and a unified AgentBrain API. This epic installs that version cleanly and rewrites the AgentForge brain layer to use it idiomatically.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Replace the current tapps-brain v3.2.0 SQLite-based integration with a clean v3.4.0 Postgres-native implementation. Vendor the v3.4.0 wheel built from the local repo, add pgvector as a required Docker service, rewrite backend/memory/brain.py to use the unified AgentBrain API, and update the full test and deployment stack.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

tapps-brain v3.4.0 removes SQLite entirely (ADR-007) in favor of Postgres with pgvector HNSW and tsvector FTS — better recall quality, one engine to audit, and a sidecar-ready HTTP adapter with live monitoring dashboard. The v3.4.0 wheel is buildable today from the local repo but has not been published to GitHub yet. Starting clean avoids retrofitting a migration path that tapps-brain explicitly does not support.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] tapps-brain v3.4.0 wheel is vendored in vendor/ and installed via uv sync --frozen
- [ ] All AgentForge Docker services start with Postgres as a required service (no hive profile gate)
- [ ] backend/memory/brain.py uses AgentBrain exclusively — no AsyncMemoryStore or HiveStore imports
- [ ] TAPPS_BRAIN_DATABASE_URL is wired into every service in docker-compose.yml
- [ ] All backend tests pass with a real Postgres DSN (no SQLite brain fixtures)
- [ ] /health endpoint reports brain.postgres as connected
- [ ] TAPPS_BRAIN_CONCERNS.md issue #1 (Docker build blocker) is marked resolved

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 43.1 -- Vendor tapps-brain v3.4.0 wheel

**Points:** 2

Build wheel from local repo, replace vendor/tapps_brain-3.2.0, update pyproject.toml source and version constraint, regenerate uv.lock

**Tasks:**
- [ ] Implement vendor tapps-brain v3.4.0 wheel
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Vendor tapps-brain v3.4.0 wheel is implemented, tests pass, and documentation is updated.

---

### 43.2 -- Postgres as required Docker service

**Points:** 3

Promote pgvector service out of hive profile, add TAPPS_BRAIN_DATABASE_URL per instance, add TAPPS_BRAIN_AUTO_MIGRATE=1, fix tapps-hive-migrate to not reference ../tapps-brain

**Tasks:**
- [ ] Implement postgres as required docker service
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Postgres as required Docker service is implemented, tests pass, and documentation is updated.

---

### 43.3 -- Rewrite brain.py with clean AgentBrain API

**Points:** 5

Replace AsyncMemoryStore + HiveStore with AgentBrain, rewrite create_brain_bridge() factory, BrainBridge wraps AgentBrain, remove all SQLite-era assumptions

**Tasks:**
- [ ] Implement rewrite brain.py with clean agentbrain api
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Rewrite brain.py with clean AgentBrain API is implemented, tests pass, and documentation is updated.

---

### 43.4 -- Settings — expose Postgres DSN, remove SQLite brain paths

**Points:** 2

Add brain_database_url to Settings, remove SQLite brain path settings, update .env.example

**Tasks:**
- [ ] Implement settings — expose postgres dsn, remove sqlite brain paths
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Settings — expose Postgres DSN, remove SQLite brain paths is implemented, tests pass, and documentation is updated.

---

### 43.5 -- Test suite — Postgres-native brain fixtures

**Points:** 3

Replace SQLite brain fixtures with Postgres, integration tests for save/recall round-trip, unit tests mock AgentBrain

**Tasks:**
- [ ] Implement test suite — postgres-native brain fixtures
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Test suite — Postgres-native brain fixtures is implemented, tests pass, and documentation is updated.

---

### 43.6 -- Docs and deployment guide update

**Points:** 2

Update DEPLOYMENT.md, HIVE_DEPLOYMENT.md, INSTALL_GUIDE.md; mark TAPPS_BRAIN_CONCERNS issue #1 resolved

**Tasks:**
- [ ] Implement docs and deployment guide update
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Docs and deployment guide update is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- tapps-brain v3.4.0 is Postgres-only per ADR-007 — no SQLite anywhere in the stack
- AgentBrain(agent_id
- project_dir
- hive_dsn=...) is the unified v3.4.0 API — replaces separate AsyncMemoryStore + HiveStore
- TAPPS_BRAIN_AUTO_MIGRATE=1 triggers schema migrations on container startup — no separate migrate service needed
- The v3.4.0 wheel must be built with uv build from ../tapps-brain then copied to vendor/
- The Dockerfile.http sidecar and brain-visual dashboard are out of scope for this epic but the service is ready when needed
- tapps-hive-migrate currently references build context ../tapps-brain which is outside Docker compose context — this is a pre-existing breakage that 43.2 fixes

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Publishing tapps-brain v3.4.0 to GitHub releases
- Migrating existing SQLite brain data (no migration tool exists; fresh start)
- Deploying the tapps-brain HTTP sidecar (Dockerfile.http) or brain-visual dashboard
- OTel / observability integration (tapps-brain v3.4.0 has OTel spans but AgentForge does not yet consume them)

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Lines | Recent Commits | Public Symbols |
|------|-------|----------------|----------------|
| `uv.lock` | *(not found)* | - | - |
| `vendor/` | *(not found)* | - | - |
| `docker-compose.yml` | *(not found)* | - | - |
| `Dockerfile.full` | *(not found)* | - | - |
| `Dockerfile.api` | *(not found)* | - | - |
| `backend/memory/brain.py` | *(not found)* | - | - |
| `backend/memory/brain_pool.py` | *(not found)* | - | - |
| `backend/config.py` | *(not found)* | - | - |
| `docs/DEPLOYMENT.md` | *(not found)* | - | - |
| `docs/HIVE_DEPLOYMENT.md` | *(not found)* | - | - |
| `docs/INSTALL_GUIDE.md` | *(not found)* | - | - |
| `docs/TAPPS_BRAIN_CONCERNS.md` | *(not found)* | - | - |
| `pyproject.toml` | 66 | 5 recent: 0578ad3 release: v2.4.0 — enhanced performance ... | - |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 7 acceptance criteria met | 0/7 | 7/7 | Checklist review |
| All 6 stories completed | 0/6 | 6/6 | Sprint board |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 43.1: Vendor tapps-brain v3.4.0 wheel
2. Story 43.2: Postgres as required Docker service
3. Story 43.3: Rewrite brain.py with clean AgentBrain API
4. Story 43.4: Settings — expose Postgres DSN, remove SQLite brain paths
5. Story 43.5: Test suite — Postgres-native brain fixtures
6. Story 43.6: Docs and deployment guide update

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| AgentBrain sync API vs BrainBridge async surface — AgentBrain.remember/recall are synchronous; BrainBridge wraps them in asyncio.to_thread | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| brain.py is ~1100 lines with circuit breakers and retry logic that must be preserved during the API swap | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| psycopg[binary] must be available in the Docker runtime image — verify it is pulled in by the wheel or add explicitly | Medium | Medium | Warning: Mitigation required - no automated recommendation available |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:performance-targets -->
## Performance Targets

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Test coverage | baseline | >= 80% | pytest --cov |
| Acceptance criteria pass rate | 0% | 100% | CI pipeline |
| Quality gate score | N/A | >= 70/100 | tapps_quality_gate |
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->
