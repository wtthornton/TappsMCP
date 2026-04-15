# Epic 4: Backup and Recovery

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~3-4 days (1 developer)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that the server has automated, tested backups with Docker volume support, enabling recovery from data loss or corruption.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Deploy Kopia for automated encrypted backups of server config, Docker volumes, and databases with scheduled verification and restore testing.

**Tech Stack:** docs-mcp, Python >=3.12

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

No backup strategy exists. Trading data and AI agent state are at risk of permanent loss from disk failure, misconfiguration, or security incident.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Kopia installed and configured with encrypted repository
- [ ] Automated daily backups of server config and Docker volumes
- [ ] Database dumps via pre-snapshot hooks
- [ ] Retention policy: 7 daily and 4 weekly and 3 monthly
- [ ] Monthly restore test verified and documented

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 4.1 -- Install and Configure Kopia

**Points:** 3

Install Kopia, create encrypted repository (local + offsite S3/B2), configure global compression and encryption settings.

**Tasks:**
- [ ] Implement install and configure kopia
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Install and Configure Kopia is implemented, tests pass, and documentation is updated.

---

### 4.2 -- Configure Docker Volume Backups

**Points:** 3

Set up pre/post-snapshot hooks to stop containers, backup Docker volumes, and restart. Configure database dump hooks for postgres.

**Tasks:**
- [ ] Implement configure docker volume backups
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Configure Docker Volume Backups is implemented, tests pass, and documentation is updated.

---

### 4.3 -- Set Up Backup Scheduling and Retention

**Points:** 2

Configure systemd timers for daily backups. Set retention policy: 7 daily, 4 weekly, 3 monthly. Enable Kopia maintenance.

**Tasks:**
- [ ] Implement set up backup scheduling and retention
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Set Up Backup Scheduling and Retention is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Kopia chosen over Restic for built-in web UI and native hooks
- Use systemd timers not cron
- See docs/recommendations-2026-server-hardening.md Section 6

**Project Structure:** 7 packages, 73 modules, 279 public APIs

**Key Dependencies:** tapps-core>=1.0.0, mcp[cli]>=1.26.0,<2, click>=8.3.1,<9, jinja2>=3.1.6,<4, gitpython>=3.1.44,<4, pydantic>=2.12.5,<3, structlog>=25.5.0,<26, pyyaml>=6.0.3,<7

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Define what is explicitly out of scope for **Backup and Recovery**...

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

1. Story 4.1: Install and Configure Kopia
2. Story 4.2: Configure Docker Volume Backups
3. Story 4.3: Set Up Backup Scheduling and Retention

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Data loss during migration if rollback path untested | High | High | Warning: Mitigation required - no automated recommendation available |
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
