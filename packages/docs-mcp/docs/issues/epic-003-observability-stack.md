# Epic 3: Observability Stack

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P2 - Medium
**Estimated LOE:** ~1-2 weeks (1 developer)
**Dependencies:** Epic 1

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that the server has production-grade monitoring, alerting, and log aggregation to detect issues before they cause service outages.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Deploy Prometheus, node_exporter, cAdvisor, Grafana, Loki, and Alloy for comprehensive metrics, container monitoring, and log aggregation.

**Tech Stack:** docs-mcp, Python >=3.12

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Story 1.4 provides basic psutil-based health checks but lacks persistent metrics, historical dashboards, container-level visibility, and centralized logging. Production workloads require a full observability stack.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Prometheus scrapes node_exporter and cAdvisor metrics
- [ ] Grafana dashboards show host and container metrics
- [ ] Loki receives container logs via Alloy
- [ ] PSI memory pressure metrics are collected and alerted on
- [ ] Alert rules fire for disk >80% and memory >85% and container down

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 3.1 -- Deploy Prometheus and node_exporter

**Points:** 3

Deploy Prometheus and node_exporter via Docker Compose. Configure scrape targets and retention.

**Tasks:**
- [ ] Implement deploy prometheus and node_exporter
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Deploy Prometheus and node_exporter is implemented, tests pass, and documentation is updated.

---

### 3.2 -- Deploy cAdvisor for Container Metrics

**Points:** 2

Deploy cAdvisor and configure Prometheus scraping for per-container CPU, memory, network, and disk metrics.

**Tasks:**
- [ ] Implement deploy cadvisor for container metrics
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Deploy cAdvisor for Container Metrics is implemented, tests pass, and documentation is updated.

---

### 3.3 -- Deploy Grafana with Dashboards

**Points:** 3

Deploy Grafana, configure Prometheus and Loki data sources, import node_exporter and Docker dashboards.

**Tasks:**
- [ ] Implement deploy grafana with dashboards
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Deploy Grafana with Dashboards is implemented, tests pass, and documentation is updated.

---

### 3.4 -- Deploy Loki and Alloy for Log Aggregation

**Points:** 3

Deploy Loki for log storage and Grafana Alloy as the collection agent. Configure Docker log forwarding.

**Tasks:**
- [ ] Implement deploy loki and alloy for log aggregation
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Deploy Loki and Alloy for Log Aggregation is implemented, tests pass, and documentation is updated.

---

### 3.5 -- Configure PSI Monitoring and Alert Rules

**Points:** 2

Enable PSI metrics in node_exporter, configure systemd-oomd, create Prometheus alert rules for disk, memory, swap, and container health.

**Tasks:**
- [ ] Implement configure psi monitoring and alert rules
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Configure PSI Monitoring and Alert Rules is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Total resource budget ~200MB RAM for the full stack
- Alloy replaces deprecated Grafana Agent
- node_exporter supports PSI since v1.5
- Bind all monitoring UIs to 127.0.0.1 or Tailscale only

**Project Structure:** 7 packages, 73 modules, 279 public APIs

**Key Dependencies:** tapps-core>=1.0.0, mcp[cli]>=1.26.0,<2, click>=8.3.1,<9, jinja2>=3.1.6,<4, gitpython>=3.1.44,<4, pydantic>=2.12.5,<3, structlog>=25.5.0,<26, pyyaml>=6.0.3,<7

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Define what is explicitly out of scope for **Observability Stack**...

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

1. Story 3.1: Deploy Prometheus and node_exporter
2. Story 3.2: Deploy cAdvisor for Container Metrics
3. Story 3.3: Deploy Grafana with Dashboards
4. Story 3.4: Deploy Loki and Alloy for Log Aggregation
5. Story 3.5: Configure PSI Monitoring and Alert Rules

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
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->
