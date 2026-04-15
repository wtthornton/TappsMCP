# Epic 2: System Hardening

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~1 week (1 developer)
**Dependencies:** Epic 1

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that the server meets CIS Level 1 baseline security, with hardened SSH, kernel protections, intrusion prevention, and automatic security patching before hosting production workloads.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Apply CIS Ubuntu 24.04 benchmarks, harden SSH, configure kernel sysctl protections, deploy CrowdSec IPS, and enable unattended security upgrades.

**Tech Stack:** docs-mcp, Python >=3.12

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

The 2026-04-08 audit and subsequent research found no CIS compliance, default SSH config, no IPS, and manual patching. These are baseline requirements for any internet-connected server.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] USG CIS Level 1 audit passes with no critical findings
- [ ] SSH accepts only ed25519 keys and listens on Tailscale interface only
- [ ] CrowdSec is active with firewall bouncer and SSH scenario
- [ ] Kernel sysctl hardening applied and persisted
- [ ] Unattended-upgrades configured with auto-reboot

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 2.1 -- Run CIS Level 1 Audit and Remediate

**Points:** 5

Install USG and run CIS Ubuntu 24.04 Level 1 Server audit. Remediate findings, excluding Docker-incompatible rules.

**Tasks:**
- [ ] Implement run cis level 1 audit and remediate
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Run CIS Level 1 Audit and Remediate is implemented, tests pass, and documentation is updated.

---

### 2.2 -- Harden SSH Configuration

**Points:** 2

Restrict SSH to ed25519 keys only, disable password auth and root login, bind to Tailscale interface, set MaxAuthTries 3.

**Tasks:**
- [ ] Implement harden ssh configuration
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Harden SSH Configuration is implemented, tests pass, and documentation is updated.

---

### 2.3 -- Deploy CrowdSec IPS

**Points:** 3

Install CrowdSec with firewall bouncer and SSH scenario. Configure ban duration and shared threat intelligence.

**Tasks:**
- [ ] Implement deploy crowdsec ips
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Deploy CrowdSec IPS is implemented, tests pass, and documentation is updated.

---

### 2.4 -- Apply Kernel Sysctl Hardening

**Points:** 2

Configure and persist kernel hardening via sysctl: ASLR, ptrace restriction, kptr_restrict, rp_filter, syncookies, unprivileged BPF.

**Tasks:**
- [ ] Implement apply kernel sysctl hardening
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Apply Kernel Sysctl Hardening is implemented, tests pass, and documentation is updated.

---

### 2.5 -- Configure Unattended Security Upgrades

**Points:** 2

Configure unattended-upgrades for security pocket with email notifications and scheduled auto-reboot.

**Tasks:**
- [ ] Implement configure unattended security upgrades
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Configure Unattended Security Upgrades is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Server runs Ubuntu 24.04.4 LTS
- Tailscale IP is 100.83.30.91
- Docker requires net.ipv4.ip_forward=1 so CIS rule must be excluded
- See docs/recommendations-2026-server-hardening.md for full research

**Project Structure:** 7 packages, 73 modules, 279 public APIs

**Key Dependencies:** tapps-core>=1.0.0, mcp[cli]>=1.26.0,<2, click>=8.3.1,<9, jinja2>=3.1.6,<4, gitpython>=3.1.44,<4, pydantic>=2.12.5,<3, structlog>=25.5.0,<26, pyyaml>=6.0.3,<7

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Define what is explicitly out of scope for **System Hardening**...

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 5 acceptance criteria met | 0/5 | 5/5 | Checklist review |
| All 5 stories completed | 0/5 | 5/5 | Sprint board |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 2.1: Run CIS Level 1 Audit and Remediate
2. Story 2.2: Harden SSH Configuration
3. Story 2.3: Deploy CrowdSec IPS
4. Story 2.4: Apply Kernel Sysctl Hardening
5. Story 2.5: Configure Unattended Security Upgrades

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Authentication bypass if token validation incomplete | Medium | High | Warning: Mitigation required - no automated recommendation available |
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
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->
