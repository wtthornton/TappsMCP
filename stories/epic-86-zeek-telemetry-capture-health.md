# Epic 86: Zeek 8.x Native Telemetry & Capture Health Dashboard

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P2 — Medium
**Estimated LOE:** ~1 week (1 developer)
**Dependencies:** Epic 79 (Production Alerting & SLA — COMPLETE), Epic 72 (Zeek Core Network Ingestion — COMPLETE), Epic 82 (Zeek Container Docker Healthcheck — COMPLETE)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that the HomeIQ observability stack gains direct visibility into Zeek's packet capture engine health — not just the zeek-network-service application metrics, but the underlying capture process metrics (packet drops, memory usage, event queue depth, connection stats). This closes the gap between "is the Python service alive?" and "is Zeek actually capturing packets reliably?" — enabling proactive alerting before packet loss degrades network security monitoring.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Enable Zeek 8.x's built-in telemetry framework to expose Prometheus-format metrics on port 9911, integrate those metrics into the existing Prometheus/Grafana/AlertManager pipeline from Epic 79, and create a Grafana dashboard panel for Zeek capture health alongside existing SLA monitoring.

**Tech Stack:** TappMCP

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Today, Epic 79's zeek-alerts.yml monitors the zeek-network-service Python application (anomaly rates, TLS failures, DNS throughput) but has no visibility into the Zeek capture engine itself. If Zeek drops packets due to memory pressure, AF_PACKET ring buffer exhaustion, or event queue saturation, the alerting pipeline is blind until downstream log parsing gaps appear — minutes to hours later. Zeek 8.x ships a built-in telemetry framework (`@load frameworks/telemetry`) that exposes real-time Prometheus-format metrics, giving us sub-second visibility into capture health.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Zeek process exposes Prometheus metrics on port 9911 via @load frameworks/telemetry
- [ ] Prometheus scrapes Zeek telemetry endpoint at 30s interval with correct labels
- [ ] Recording rules compute 5m rolling averages for packet drops and event queue depth
- [ ] Alert rules fire on packet drop rate >0.1% and event queue depth >10000
- [ ] Grafana dashboard displays Zeek capture health panels (packets received/dropped/memory/event queue/connections)
- [ ] Dashboard is auto-provisioned alongside existing SLA dashboard
- [ ] All changes work with Zeek's network_mode: host constraint
- [ ] zeek-alerts.yml updated to include capture-level alert rules

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 86.1 -- Enable Zeek Telemetry Framework in local.zeek

**Points:** 2

Add @load frameworks/telemetry and redef Telemetry::metrics_port = 9911 to the Zeek site config. Verify metrics endpoint responds with Prometheus text format.

**Tasks:**
- [ ] Implement enable zeek telemetry framework in local.zeek
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Enable Zeek Telemetry Framework in local.zeek is implemented, tests pass, and documentation is updated.

---

### 86.2 -- Docker Networking — Expose Telemetry Port to Prometheus

**Points:** 3

Solve the host-network-to-bridge connectivity challenge. Add extra_hosts entry for Prometheus container, or use host gateway. Expose port 9911 from host-networked Zeek to bridge-networked Prometheus. Update compose.yml and document the approach.

**Tasks:**
- [ ] Implement docker networking — expose telemetry port to prometheus
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Docker Networking — Expose Telemetry Port to Prometheus is implemented, tests pass, and documentation is updated.

---

### 86.3 -- Prometheus Scrape Config for Zeek Telemetry

**Points:** 2

Add zeek-telemetry scrape job to prometheus.yml targeting the Zeek native metrics endpoint on port 9911. Apply appropriate labels (service=zeek, group=data-collectors, tier=2).

**Tasks:**
- [ ] Implement prometheus scrape config for zeek telemetry
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Prometheus Scrape Config for Zeek Telemetry is implemented, tests pass, and documentation is updated.

---

### 86.4 -- Zeek Capture Health Recording Rules

**Points:** 2

Add recording rules to zeek-alerts.yml for rolling capture metrics: zeek:packets:received_rate_5m, zeek:packets:dropped_rate_5m, zeek:packets:drop_ratio_5m, zeek:memory:usage_bytes, zeek:event_queue:depth_avg_5m, zeek:connections:active.

**Tasks:**
- [ ] Implement zeek capture health recording rules
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Zeek Capture Health Recording Rules is implemented, tests pass, and documentation is updated.

---

### 86.5 -- Zeek Capture Health Alert Rules

**Points:** 3

Add alert rules for capture degradation: ZeekPacketDropHigh (drop ratio >0.1%, critical), ZeekMemoryPressure (>80% of container limit, warning), ZeekEventQueueSaturated (depth >10000, warning), ZeekCaptureStalled (received_rate = 0 for >2m, critical).

**Tasks:**
- [ ] Implement zeek capture health alert rules
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Zeek Capture Health Alert Rules is implemented, tests pass, and documentation is updated.

---

### 86.6 -- Grafana Zeek Capture Health Dashboard

**Points:** 3

Create zeek-capture-health.json dashboard with panels: Packets Received/Dropped rate, Drop Ratio gauge, Memory Usage, Event Queue Depth, Active Connections by protocol, and a combined health status panel. Auto-provision via existing dashboard provisioner.

**Tasks:**
- [ ] Implement grafana zeek capture health dashboard
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Grafana Zeek Capture Health Dashboard is implemented, tests pass, and documentation is updated.

---

### 86.7 -- Integration Verification & Documentation

**Points:** 2

Verify end-to-end: Zeek telemetry → Prometheus scrape → recording rules evaluate → alerts can fire → Grafana renders. Update TECH_STACK.md with port 9911 assignment. Add smoke test to healthcheck.sh.

**Tasks:**
- [ ] Implement integration verification & documentation
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Integration Verification & Documentation is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Zeek 8.x telemetry uses @load frameworks/telemetry — this is a built-in framework (no zkg package needed)
- Telemetry::metrics_port = 9911 opens an HTTP endpoint serving Prometheus text format (text/plain 0.0.4)
- Zeek container uses network_mode: host — port 9911 is on the host not the Docker bridge. Prometheus (on homeiq-network bridge) must reach it via host.docker.internal or extra_hosts
- Key Zeek 8.x telemetry metric families: zeek_packets_received_total (counter) / zeek_packets_dropped_total (counter) / zeek_active_connections (gauge) / zeek_event_queue_length (gauge) / zeek_memory_usage_bytes (gauge) / zeek_timers_pending (gauge)
- Existing zeek-alerts.yml already has app-level alerts from zeek-network-service:8048/metrics — this epic adds capture-engine-level alerts from Zeek itself on :9911
- Port 9911 is not yet assigned in TECH_STACK.md — reserve it for Zeek telemetry

**Project Structure:** 47 packages, 837 modules, 3344 public APIs

### Expert Recommendations

- **Security Expert** (67%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (59%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Modifying zeek-network-service Python application metrics (already handled by Epic 72)
- Adding OpenTelemetry or OTLP export from Zeek (native Prometheus is sufficient)
- Custom Zeek scripts for additional metric instrumentation beyond built-in telemetry
- Alerting on individual connection-level events (handled by existing zeek-alerts.yml)

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Lines | Recent Commits | Public Symbols |
|------|-------|----------------|----------------|
| `domains/data-collectors/zeek-network-service/zeek-config/local.zeek` | *(not found)* | - | - |
| `domains/data-collectors/compose.yml` | *(not found)* | - | - |
| `infrastructure/prometheus/prometheus.yml` | *(not found)* | - | - |
| `infrastructure/prometheus/zeek-alerts.yml` | *(not found)* | - | - |
| `infrastructure/grafana/dashboards/sla-overview.json` | *(not found)* | - | - |
| `domains/data-collectors/zeek-network-service/Dockerfile.zeek` | *(not found)* | - | - |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Packet drop visibility | Blind | Sub-30s | Prometheus scrape |
| Alert MTTR for capture issues | Hours (log gap detection) | Minutes (direct metric alert) | AlertManager |
| Dashboard load time | N/A | <3s | Grafana |
| Metric cardinality | 0 Zeek-native | ~20 metric families | Prometheus |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:stakeholders -->
## Stakeholders

| Role | Person | Responsibility |
|------|--------|----------------|
| Owner | Platform Team | Implementation and testing |
| Consumer | Security Monitoring | Zeek capture health visibility |
| Consumer | SRE/Oncall | Alert response for capture degradation |

<!-- docsmcp:end:stakeholders -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 86.1: Enable Zeek Telemetry Framework in local.zeek
2. Story 86.2: Docker Networking — Expose Telemetry Port to Prometheus
3. Story 86.3: Prometheus Scrape Config for Zeek Telemetry
4. Story 86.4: Zeek Capture Health Recording Rules
5. Story 86.5: Zeek Capture Health Alert Rules
6. Story 86.6: Grafana Zeek Capture Health Dashboard
7. Story 86.7: Integration Verification & Documentation

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Zeek 8.1.1 telemetry framework may expose fewer metrics than documented in 8.x dev builds — validate available metric families before writing recording rules | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Host-network-to-bridge-network connectivity may require platform-specific workarounds (Docker Desktop vs native Linux) — test on deployment target | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Telemetry endpoint adds ~2MB RSS to Zeek process — within existing 4GB limit but should be monitored | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| If Zeek is under extreme load the telemetry HTTP server may become unresponsive — Prometheus scrape timeout (10s) handles this gracefully | Medium | Medium | Warning: Mitigation required - no automated recommendation available |

**Expert-Identified Risks:**

- **Security Expert**: *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*

<!-- docsmcp:end:risk-assessment -->
