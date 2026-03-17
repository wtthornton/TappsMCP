# PRD: Zeek Network Intelligence Service

<!-- docsmcp:start:executive-summary -->
## Executive Summary

HomeIQ has no visibility into network-layer behavior of IoT devices. The platform monitors 50+ smart home services but cannot see: which devices communicate with which cloud endpoints, MQTT traffic patterns across the HA backbone, network anomalies indicating compromised devices, per-device bandwidth consumption, or TLS security posture of IoT devices. This blind spot limits device-intelligence-service accuracy, prevents network-correlated energy analysis, and leaves security gaps undetected.

**Tech Stack:** TappMCP

<!-- docsmcp:end:executive-summary -->

<!-- docsmcp:start:problem-statement -->
## Problem Statement

HomeIQ has no visibility into network-layer behavior of IoT devices. The platform monitors 50+ smart home services but cannot see: which devices communicate with which cloud endpoints, MQTT traffic patterns across the HA backbone, network anomalies indicating compromised devices, per-device bandwidth consumption, or TLS security posture of IoT devices. This blind spot limits device-intelligence-service accuracy, prevents network-correlated energy analysis, and leaves security gaps undetected.

<!-- docsmcp:end:problem-statement -->

<!-- docsmcp:start:user-personas -->
## User Personas

1. **HomeIQ Platform Administrator (manages the Docker stack and HA instance)**
2. **Smart Home Power User (wants device insights and security visibility)**
3. **Energy-Conscious Homeowner (correlates network activity with power consumption)**
4. **Security-Aware User (wants alerts on suspicious device behavior)**

<!-- docsmcp:end:user-personas -->

<!-- docsmcp:start:solution-overview -->
## Solution Overview

Describe the proposed solution at a high level...

**Project Structure:** 47 packages, 837 modules, 3344 public APIs

<!-- docsmcp:end:solution-overview -->

<!-- docsmcp:start:phased-requirements -->
## Phased Requirements

### Phase 1: Phase 1 — Core Network Ingestion

Deploy Zeek container with JSON output, build zeek-network-service to parse conn.log and dns.log, write to InfluxDB, basic health dashboard integration

- Zeek Docker container with --net=host and BPF filter excluding Docker bridge
- JSON log output to shared Docker volume
- Python zeek-network-service following data-collector pattern (FastAPI, BaseServiceSettings, ServiceLifespan)
- Parse conn.log into network_connections InfluxDB measurement (tags: src_ip, dst_ip, proto; fields: duration, bytes_sent, bytes_recv)
- Parse dns.log into network_dns measurement (tags: device_ip, query_domain, query_type; fields: response_code, ttl)
- Background polling loop (30s interval) tailing Zeek JSON logs
- Health endpoint with Zeek process status, log freshness, write counts
- REST API: GET /current-stats, GET /devices, GET /health
- Port 8048 assignment

### Phase 2: Phase 2 — Device Fingerprinting

Add JA3/JA4, DHCP, and HASSH fingerprinting. Feed device-intelligence-service and device-database-client with auto-discovered device metadata.

- Install Zeek packages: ja3, ja4, hassh, KYD (DHCP fingerprinting)
- Parse ssl.log + ja3.log + ja4.log into network_device_fingerprints PostgreSQL table
- Parse dhcp.log + dhcpfp.log into device discovery records
- Parse software.log for user-agent and server version extraction
- REST API: GET /devices/{ip}/fingerprint, GET /devices/discovered
- Feed device-intelligence-service via data-api with fingerprint data
- Feed device-database-client with auto-discovered MAC/vendor/hostname
- Deduplication logic for device identity across DHCP renewals

### Phase 3: Phase 3 — MQTT and Protocol Intelligence

Enable Zeek MQTT analyzer for HA backbone monitoring. Add TLS certificate monitoring and protocol-level insights.

- Zeek MQTT analyzer enabled (mqtt_connect.log, mqtt_publish.log, mqtt_subscribe.log)
- Parse MQTT logs into network_mqtt InfluxDB measurement (tags: client_id, topic; fields: qos, payload_size)
- Parse x509.log and ssl.log for certificate monitoring
- REST API: GET /mqtt/topics, GET /mqtt/clients, GET /tls/certificates
- Alert generation for: rogue MQTT clients, expired certificates, weak TLS versions
- Feed automation-trace-service with MQTT trace data
- Certificate expiry tracking in PostgreSQL

### Phase 4: Phase 4 — Anomaly Detection and Security Baseline

Network baseline establishment, anomaly detection, and integration with proactive-agent-service for security alerting.

- Parse weird.log and notice.log for anomaly events
- Network baseline from known_hosts.log, known_services.log, known_certs.log
- New device detection alerts (device not in baseline)
- Beaconing detection from conn.log patterns (regular interval connections to external IPs)
- DNS anomaly detection (DGA domains, DNS tunneling indicators)
- Install zeek-flowmeter for ML-ready traffic features
- Feed proactive-agent-service with security events
- Feed ai-pattern-service with network behavioral patterns
- REST API: GET /anomalies, GET /baseline/devices, GET /security/alerts

<!-- docsmcp:end:phased-requirements -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

### AC: Zeek Docker container with --net=host and BPF filter excludi

```gherkin
Feature: zeek-docker-container-with-nethost-and-b
  Scenario: Zeek Docker container with --net=host and BPF filter excludi
    Given the system is in its initial state
    When zeek docker container with --net=host and bpf filter excluding docker bridge
    Then the expected outcome is achieved
```

### AC: JSON log output to shared Docker volume

```gherkin
Feature: json-log-output-to-shared-docker-volume
  Scenario: JSON log output to shared Docker volume
    Given the system is in its initial state
    When json log output to shared docker volume
    Then the expected outcome is achieved
```

### AC: Python zeek-network-service following data-collector pattern

```gherkin
Feature: python-zeek-network-service-following-da
  Scenario: Python zeek-network-service following data-collector pattern
    Given the system is in its initial state
    When python zeek-network-service following data-collector pattern (fastapi, baseservicesettings, servicelifespan)
    Then the expected outcome is achieved
```

### AC: Parse conn.log into network_connections InfluxDB measurement

```gherkin
Feature: parse-connlog-into-network-connections-i
  Scenario: Parse conn.log into network_connections InfluxDB measurement
    Given the system is in its initial state
    When parse conn.log into network_connections influxdb measurement (tags: src_ip, dst_ip, proto; fields: duration, bytes_sent, bytes_recv)
    Then the expected outcome is achieved
```

### AC: Parse dns.log into network_dns measurement (tags: device_ip,

```gherkin
Feature: parse-dnslog-into-network-dns-measuremen
  Scenario: Parse dns.log into network_dns measurement (tags: device_ip,
    Given the system is in its initial state
    When parse dns.log into network_dns measurement (tags: device_ip, query_domain, query_type; fields: response_code, ttl)
    Then the expected outcome is achieved
```

### AC: Background polling loop (30s interval) tailing Zeek JSON log

```gherkin
Feature: background-polling-loop-30s-interval-tai
  Scenario: Background polling loop (30s interval) tailing Zeek JSON log
    Given the system is in its initial state
    When background polling loop (30s interval) tailing zeek json logs
    Then the expected outcome is achieved
```

### AC: Health endpoint with Zeek process status, log freshness, wri

```gherkin
Feature: health-endpoint-with-zeek-process-status
  Scenario: Health endpoint with Zeek process status, log freshness, wri
    Given the system is in its initial state
    When health endpoint with zeek process status, log freshness, write counts
    Then the expected outcome is achieved
```

### AC: REST API: GET /current-stats, GET /devices, GET /health

```gherkin
Feature: rest-api-get-current-stats-get-devices-g
  Scenario: REST API: GET /current-stats, GET /devices, GET /health
    Given the system is in its initial state
    When rest api: get /current-stats, get /devices, get /health
    Then the expected outcome is achieved
```

### AC: Port 8048 assignment

```gherkin
Feature: port-8048-assignment
  Scenario: Port 8048 assignment
    Given the system is in its initial state
    When port 8048 assignment
    Then the expected outcome is achieved
```

### AC: Install Zeek packages: ja3, ja4, hassh, KYD (DHCP fingerprin

```gherkin
Feature: install-zeek-packages-ja3-ja4-hassh-kyd-
  Scenario: Install Zeek packages: ja3, ja4, hassh, KYD (DHCP fingerprin
    Given the system is in its initial state
    When install zeek packages: ja3, ja4, hassh, kyd (dhcp fingerprinting)
    Then the expected outcome is achieved
```

### AC: Parse ssl.log + ja3.log + ja4.log into network_device_finger

```gherkin
Feature: parse-ssllog-ja3log-ja4log-into-network-
  Scenario: Parse ssl.log + ja3.log + ja4.log into network_device_finger
    Given the system is in its initial state
    When parse ssl.log + ja3.log + ja4.log into network_device_fingerprints postgresql table
    Then the expected outcome is achieved
```

### AC: Parse dhcp.log + dhcpfp.log into device discovery records

```gherkin
Feature: parse-dhcplog-dhcpfplog-into-device-disc
  Scenario: Parse dhcp.log + dhcpfp.log into device discovery records
    Given the system is in its initial state
    When parse dhcp.log + dhcpfp.log into device discovery records
    Then the expected outcome is achieved
```

### AC: Parse software.log for user-agent and server version extract

```gherkin
Feature: parse-softwarelog-for-user-agent-and-ser
  Scenario: Parse software.log for user-agent and server version extract
    Given the system is in its initial state
    When parse software.log for user-agent and server version extraction
    Then the expected outcome is achieved
```

### AC: REST API: GET /devices/{ip}/fingerprint, GET /devices/discov

```gherkin
Feature: rest-api-get-devicesipfingerprint-get-de
  Scenario: REST API: GET /devices/{ip}/fingerprint, GET /devices/discov
    Given the system is in its initial state
    When rest api: get /devices/{ip}/fingerprint, get /devices/discovered
    Then the expected outcome is achieved
```

### AC: Feed device-intelligence-service via data-api with fingerpri

```gherkin
Feature: feed-device-intelligence-service-via-dat
  Scenario: Feed device-intelligence-service via data-api with fingerpri
    Given the system is in its initial state
    When feed device-intelligence-service via data-api with fingerprint data
    Then the expected outcome is achieved
```

### AC: Feed device-database-client with auto-discovered MAC/vendor/

```gherkin
Feature: feed-device-database-client-with-auto-di
  Scenario: Feed device-database-client with auto-discovered MAC/vendor/
    Given the system is in its initial state
    When feed device-database-client with auto-discovered mac/vendor/hostname
    Then the expected outcome is achieved
```

### AC: Deduplication logic for device identity across DHCP renewals

```gherkin
Feature: deduplication-logic-for-device-identity-
  Scenario: Deduplication logic for device identity across DHCP renewals
    Given the system is in its initial state
    When deduplication logic for device identity across dhcp renewals
    Then the expected outcome is achieved
```

### AC: Zeek MQTT analyzer enabled (mqtt_connect.log, mqtt_publish.l

```gherkin
Feature: zeek-mqtt-analyzer-enabled-mqtt-connectl
  Scenario: Zeek MQTT analyzer enabled (mqtt_connect.log, mqtt_publish.l
    Given the system is in its initial state
    When zeek mqtt analyzer enabled (mqtt_connect.log, mqtt_publish.log, mqtt_subscribe.log)
    Then the expected outcome is achieved
```

### AC: Parse MQTT logs into network_mqtt InfluxDB measurement (tags

```gherkin
Feature: parse-mqtt-logs-into-network-mqtt-influx
  Scenario: Parse MQTT logs into network_mqtt InfluxDB measurement (tags
    Given the system is in its initial state
    When parse mqtt logs into network_mqtt influxdb measurement (tags: client_id, topic; fields: qos, payload_size)
    Then the expected outcome is achieved
```

### AC: Parse x509.log and ssl.log for certificate monitoring

```gherkin
Feature: parse-x509log-and-ssllog-for-certificate
  Scenario: Parse x509.log and ssl.log for certificate monitoring
    Given the system is in its initial state
    When parse x509.log and ssl.log for certificate monitoring
    Then the expected outcome is achieved
```

### AC: REST API: GET /mqtt/topics, GET /mqtt/clients, GET /tls/cert

```gherkin
Feature: rest-api-get-mqtttopics-get-mqttclients-
  Scenario: REST API: GET /mqtt/topics, GET /mqtt/clients, GET /tls/cert
    Given the system is in its initial state
    When rest api: get /mqtt/topics, get /mqtt/clients, get /tls/certificates
    Then the expected outcome is achieved
```

### AC: Alert generation for: rogue MQTT clients, expired certificat

```gherkin
Feature: alert-generation-for-rogue-mqtt-clients-
  Scenario: Alert generation for: rogue MQTT clients, expired certificat
    Given the system is in its initial state
    When alert generation for: rogue mqtt clients, expired certificates, weak tls versions
    Then the expected outcome is achieved
```

### AC: Feed automation-trace-service with MQTT trace data

```gherkin
Feature: feed-automation-trace-service-with-mqtt-
  Scenario: Feed automation-trace-service with MQTT trace data
    Given the system is in its initial state
    When feed automation-trace-service with mqtt trace data
    Then the expected outcome is achieved
```

### AC: Certificate expiry tracking in PostgreSQL

```gherkin
Feature: certificate-expiry-tracking-in-postgresq
  Scenario: Certificate expiry tracking in PostgreSQL
    Given the system is in its initial state
    When certificate expiry tracking in postgresql
    Then the expected outcome is achieved
```

### AC: Parse weird.log and notice.log for anomaly events

```gherkin
Feature: parse-weirdlog-and-noticelog-for-anomaly
  Scenario: Parse weird.log and notice.log for anomaly events
    Given the system is in its initial state
    When parse weird.log and notice.log for anomaly events
    Then the expected outcome is achieved
```

### AC: Network baseline from known_hosts.log, known_services.log, k

```gherkin
Feature: network-baseline-from-known-hostslog-kno
  Scenario: Network baseline from known_hosts.log, known_services.log, k
    Given the system is in its initial state
    When network baseline from known_hosts.log, known_services.log, known_certs.log
    Then the expected outcome is achieved
```

### AC: New device detection alerts (device not in baseline)

```gherkin
Feature: new-device-detection-alerts-device-not-i
  Scenario: New device detection alerts (device not in baseline)
    Given the system is in its initial state
    When new device detection alerts (device not in baseline)
    Then the expected outcome is achieved
```

### AC: Beaconing detection from conn.log patterns (regular interval

```gherkin
Feature: beaconing-detection-from-connlog-pattern
  Scenario: Beaconing detection from conn.log patterns (regular interval
    Given the system is in its initial state
    When beaconing detection from conn.log patterns (regular interval connections to external ips)
    Then the expected outcome is achieved
```

### AC: DNS anomaly detection (DGA domains, DNS tunneling indicators

```gherkin
Feature: dns-anomaly-detection-dga-domains-dns-tu
  Scenario: DNS anomaly detection (DGA domains, DNS tunneling indicators
    Given the system is in its initial state
    When dns anomaly detection (dga domains, dns tunneling indicators)
    Then the expected outcome is achieved
```

### AC: Install zeek-flowmeter for ML-ready traffic features

```gherkin
Feature: install-zeek-flowmeter-for-ml-ready-traf
  Scenario: Install zeek-flowmeter for ML-ready traffic features
    Given the system is in its initial state
    When install zeek-flowmeter for ml-ready traffic features
    Then the expected outcome is achieved
```

### AC: Feed proactive-agent-service with security events

```gherkin
Feature: feed-proactive-agent-service-with-securi
  Scenario: Feed proactive-agent-service with security events
    Given the system is in its initial state
    When feed proactive-agent-service with security events
    Then the expected outcome is achieved
```

### AC: Feed ai-pattern-service with network behavioral patterns

```gherkin
Feature: feed-ai-pattern-service-with-network-beh
  Scenario: Feed ai-pattern-service with network behavioral patterns
    Given the system is in its initial state
    When feed ai-pattern-service with network behavioral patterns
    Then the expected outcome is achieved
```

### AC: REST API: GET /anomalies, GET /baseline/devices, GET /securi

```gherkin
Feature: rest-api-get-anomalies-get-baselinedevic
  Scenario: REST API: GET /anomalies, GET /baseline/devices, GET /securi
    Given the system is in its initial state
    When rest api: get /anomalies, get /baseline/devices, get /security/alerts
    Then the expected outcome is achieved
```

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:technical-constraints -->
## Technical Constraints

- Must follow existing data-collector patterns (BaseServiceSettings
- ServiceLifespan
- StandardHealthCheck)
- Two-container design (Zeek official image + Python sidecar)
- Shared Docker volume for log transfer
- No Kafka dependency (file-based polling to match existing patterns)
- Port 8048
- InfluxDB for time-series and PostgreSQL devices schema for metadata
- BPF filter must exclude homeiq-network Docker bridge traffic
- Zeek container requires --net=host for physical NIC access
- Resource budget: Zeek 2 cores + 4GB RAM and sidecar 384MB
- All 5 homeiq shared libs must be installed

<!-- docsmcp:end:technical-constraints -->

<!-- docsmcp:start:non-goals -->
## Non-Goals

- Replacing existing IDS/IPS solutions (Zeek is passive monitoring only)
- Monitoring inter-container Docker traffic (excluded by BPF filter)
- Kafka or message queue infrastructure
- Active network scanning or port scanning
- VPN or encrypted tunnel inspection
- Packet capture storage (PCAP retention)
- Real-time sub-second alerting (30s polling interval is sufficient)
- Custom Spicy protocol parsers for Matter/Thread/Zigbee (future epic)
- Integration with external SIEM platforms

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:boundary-system -->
## Boundary System

### Always Do

- Define actions that should always be taken...

### Ask First

- Define actions that require confirmation before proceeding...

### Never Do

- Define actions that are explicitly prohibited...

<!-- docsmcp:end:boundary-system -->

<!-- docsmcp:start:architecture-overview -->
## Architecture Overview

47 packages, 837 modules, 3344 public APIs

**Recent Activity:** 5 recent commits, latest: fix(tapps-mcp): clean up tapps_session_start inter

<!-- docsmcp:end:architecture-overview -->
