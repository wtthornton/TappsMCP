# OpenClaw Mission Control — Product Requirements Document

> **Version:** 1.1 — Draft (Research-Updated)
> **Date:** 2026-03-02
> **Author:** Auto-generated from research of [Jonathan Tsai's OpenClaw Command Center](https://www.jontsai.com/2026/02/12/building-mission-control-for-my-ai-workforce-introducing-openclaw-command-center), 9+ community dashboard projects, the [OpenClaw Agent Teams RFC](https://github.com/openclaw/openclaw/discussions/10036), and the broader [OpenClaw](https://github.com/openclaw/openclaw) ecosystem.
> **Status:** Draft for Review

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Vision & Goals](#3-vision--goals)
4. [Target Users](#4-target-users)
5. [OpenClaw Platform Context](#5-openclaw-platform-context)
6. [Feature Requirements](#6-feature-requirements)
7. [Architecture & Technical Design](#7-architecture--technical-design)
8. [Security Model](#8-security-model)
9. [UI/UX Design](#9-uiux-design)
10. [Integration Points](#10-integration-points)
11. [Deployment & Distribution](#11-deployment--distribution)
12. [Competitive Landscape](#12-competitive-landscape)
13. [Phased Roadmap](#13-phased-roadmap)
14. [Success Metrics](#14-success-metrics)
15. [Open Questions](#15-open-questions)
16. [References](#16-references)

---

## 1. Executive Summary

**OpenClaw Mission Control** is a centralized operations dashboard for managing, monitoring, and orchestrating AI agents running on the [OpenClaw](https://github.com/openclaw/openclaw) personal AI assistant framework. Inspired by Jonathan Tsai's "Command Center" concept — described as *"the air traffic control tower for your AI workforce"* — this project aims to provide a unified, self-hosted web interface that gives operators real-time visibility into agent sessions, cost/quota management, task scheduling, topic tracking, and multi-agent coordination.

OpenClaw (248k+ GitHub stars, MIT license) is the dominant open-source personal AI assistant framework. It runs a single Gateway process per operator, connecting to 21+ messaging platforms and executing agent logic with tool access. However, **there is no first-party GUI** — operators manage everything via CLI, config files, and chat commands. Mission Control fills this gap.

### Core Value Proposition

| Problem | Mission Control Solution |
|---|---|
| No visibility into what agents are doing | Real-time session dashboard with token/cost tracking |
| Manual quota management → surprise overage bills | LLM Fuel Gauges + quota-aware scheduling |
| CLI-only cron/task management | Visual scheduler with advanced scheduling primitives |
| No unified view across multiple agents/instances | Multi-instance aggregation dashboard |
| Topic/project tracking scattered across Slack threads | Cerebro topic detection and organization |
| No approval workflow for sensitive operations | Governance layer with human-in-the-loop approvals |
| Agents stuck in loops burn money undetected | Loop detection watchdog with auto-kill circuit breaker |
| Agent memory/workspace opaque to operator | Memory browser with semantic search and workspace file inspector |

---

## 2. Problem Statement

Operators running OpenClaw AI agents at scale (multiple instances, dozens of scheduled tasks, multiple LLM providers) face several pain points:

1. **Blind operations** — No dashboard showing what agents are doing right now, how many tokens they've consumed, or what tasks are queued. Operators rely on log files and chat history.

2. **Cost surprises** — LLM API quotas reset on irregular schedules. Without tracking, operators hit overage charges ($100s–$1000s/month) unexpectedly.

3. **Config-file orchestration** — Cron jobs, agent configurations, model routing, and channel settings all live in YAML/JSON files edited manually. No visual management.

4. **Context fragmentation** — Conversations with agents happen across Slack, Telegram, Discord, etc. No unified view of what topics are being worked on.

5. **No governance** — Sensitive agent actions (file writes, shell commands, purchases, external API calls) have no approval workflow beyond per-session tool permissions.

6. **Scaling complexity** — Running 5+ OpenClaw instances across multiple machines requires SSH-ing into each host. No centralized multi-instance view.

7. **Runaway agents burn money silently** — Agents can get stuck in infinite loops (one documented incident: [1,535 identical tool calls in 2 hours, $150 wasted, 3GB memory](https://github.com/openclaw/openclaw/issues/16808)) with no detection or circuit breaker. OpenClaw's watchdog monitors process existence but not behavioral patterns.

8. **No memory/workspace visibility** — Agent memory files, workspace documents, and vector search indices are opaque. Debugging agent behavior requires SSH + manual file inspection across `~/.openclaw/agents/*/memory/` directories.

---

## 3. Vision & Goals

### Vision

> A lightweight, self-hosted "air traffic control" dashboard that makes managing an AI workforce as intuitive as managing a Kanban board — with the operational depth of a production monitoring system.

### Goals

| # | Goal | Success Criteria |
|---|---|---|
| G1 | Real-time visibility | Operators see all active sessions, tokens, costs, and system vitals within 2 seconds of state change |
| G2 | Cost control | Zero surprise LLM overage charges through proactive quota tracking and scheduling |
| G3 | Visual task management | Create, edit, pause, and monitor cron jobs without touching config files |
| G4 | Multi-instance support | Single dashboard aggregating state from 1–10+ OpenClaw Gateway instances |
| G5 | Topic intelligence | Auto-detect and organize agent conversations by project/topic |
| G6 | Governance | Configurable approval workflows for sensitive agent actions |
| G7 | Minimal footprint | <1 MB total bundle, no build step, zero external CDN calls |
| G8 | Security-first | Localhost-only by default, optional auth layers, no telemetry |

### Non-Goals (v1)

- Replacing the OpenClaw CLI entirely
- Multi-tenant / multi-user access control (single operator model)
- Mobile-native apps (responsive web is sufficient)
- LLM model fine-tuning or training management
- Building a new agent framework (we leverage OpenClaw's existing runtime)

---

## 4. Target Users

### Primary: Solo AI Power Users

- Run 1–5 OpenClaw instances on personal hardware (Mac Studio, Mac Mini, Linux VMs)
- Use 3+ messaging channels (Slack, Telegram, Discord)
- Have 10–50+ scheduled cron tasks
- Spend $50–$500/month on LLM API costs
- Technical enough to self-host but want visual management

### Secondary: Small Team Operators

- Run OpenClaw for a team of 2–5 people
- Need audit trails and approval workflows
- Manage shared infrastructure (gateways on cloud VMs)
- Want centralized visibility without granting everyone CLI access

### Tertiary: Framework Contributors / Power Users

- Building custom OpenClaw skills and integrations
- Need debugging visibility (session transcripts, tool call traces, error rates)
- Want performance metrics for optimization

---

## 5. OpenClaw Platform Context

Understanding the OpenClaw platform is essential for building Mission Control. Here is the relevant architecture:

### 5.1 Gateway Architecture

The **Gateway** is OpenClaw's central control plane — a multiplexed WebSocket/HTTP server (default port `18789`) that owns all state:

```
┌─────────────────────────────────────────────────────┐
│                   OpenClaw Gateway                   │
│                  (ws://127.0.0.1:18789)              │
│                                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │ Sessions │ │ Channels │ │   Cron   │ │ Memory │  │
│  │ Manager  │ │ Manager  │ │ Service  │ │ Search │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │  Agent   │ │  Tools   │ │  Nodes   │ │ Config │  │
│  │ Runtime  │ │ Registry │ │ Manager  │ │ Loader │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────┘  │
└─────────────────────────────────────────────────────┘
         ▲              ▲              ▲
         │              │              │
    ┌────┘    ┌────────┘    ┌────────┘
    │         │              │
┌───────┐ ┌───────┐   ┌──────────┐
│  CLI  │ │ Slack │   │ iOS/Mac  │
│Client │ │ Bot   │   │  Nodes   │
└───────┘ └───────┘   └──────────┘
```

### 5.2 WebSocket RPC Protocol

All communication uses typed WebSocket frames:

| Frame Type | Direction | Purpose |
|---|---|---|
| `RequestFrame` | client → server | RPC invocation |
| `ResponseFrame` | server → client | RPC return values |
| `EventFrame` | server → client | Push notifications |
| `InvokeFrame` | server → client | Tool/node invocations |
| `InvokeResponseFrame` | client → server | Tool/node results |

**RPC Namespaces:**
- `agent.*` — Agent lifecycle (start, stop, reset)
- `chat.*` — Message send/receive, history
- `sessions.*` — Session CRUD, listing, preview
- `cron.*` — Job management (add, update, remove, run)
- `config.*` — Configuration read/write
- `nodes.*` — Device node management
- `mesh.*` — Multi-gateway coordination

### 5.3 Session Model

Sessions are persisted conversation threads keyed by channel + account + peer:

```
Session Key Format: agent:<agentId>:<channel>:<peer>
Storage: ~/.openclaw/agents/<agentId>/sessions/*.jsonl
Metadata: ~/.openclaw/sessions.json
```

Sessions support reset policies (daily, idle timeout) and context window compaction.

### 5.4 Cron Service

Built-in scheduler persisting jobs to `~/.openclaw/cron/`:

```json
{
  "id": "daily-standup",
  "schedule": "0 9 * * 1-5",
  "agent": "main",
  "action": "inject",
  "message": "Run the morning standup routine",
  "channel": "slack:#team-standup",
  "enabled": true
}
```

Execution modes: `inject` (into existing session) or `spawn` (isolated agent turn).

### 5.5 Security Model

- **Single-operator trust model** — one trusted operator per Gateway
- **Loopback binding by default** — Gateway on `127.0.0.1`
- **Auth required** — Token or password, fail-closed
- **DM pairing** — Unknown senders must be approved
- **Tool permissions** — `safe` / `ask` / `security` approval levels
- **Sandbox support** — Docker container isolation for untrusted sessions

### 5.6 State & Storage Locations

| Data | Location |
|---|---|
| Gateway config | `~/.openclaw/openclaw.json` |
| Agent configs | `~/.openclaw/agents/<id>/` |
| Session metadata | `~/.openclaw/sessions.json` |
| Session transcripts | `~/.openclaw/agents/<id>/sessions/*.jsonl` |
| Cron jobs | `~/.openclaw/cron/` |
| Memory | `~/.openclaw/agents/<id>/memory/` |
| Credentials | `~/.openclaw/credentials/` |
| Logs | `/tmp/openclaw/openclaw-YYYY-MM-DD.log` |

---

## 6. Feature Requirements

### 6.1 Real-Time Session Dashboard (P0 — Must Have)

**Description:** Live view of all active and recent agent sessions across connected Gateway instances.

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| SESS-1 | Display active sessions with agent name, channel, peer, model, status | P0 |
| SESS-2 | Show token count (input/output) per session, updating in real-time | P0 |
| SESS-3 | Show estimated cost per session (based on model pricing) | P0 |
| SESS-4 | Display session duration and last activity timestamp | P0 |
| SESS-5 | Color-code session status (active/idle/error/completed) | P1 |
| SESS-6 | Click to expand session → show recent message transcript | P1 |
| SESS-7 | Session search and filtering by agent, channel, date range | P1 |
| SESS-8 | Session reset / kill action from dashboard | P2 |

**Data Source:** `sessions.*` RPC namespace, `EventFrame` push events.

### 6.2 Runaway Agent Detection & Circuit Breaker (P0 — Must Have)

**Description:** Real-time behavioral watchdog that detects stuck agents and prevents runaway cost. Inspired by [OpenClaw Issue #16808](https://github.com/openclaw/openclaw/issues/16808) (1,535 identical calls, $150 wasted) and the [TokPinch cost proxy](https://dev.to/tobiasbond/how-i-built-a-cost-proxy-to-stop-openclaw-from-burning-my-api-budget-25i3) pattern.

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| LOOP-1 | Track sliding window of recent tool calls per session (tool + argsHash) | P0 |
| LOOP-2 | Detect exact repetition loops (same tool + args >N times in M calls, default N=10, M=20) | P0 |
| LOOP-3 | Detect alternating cycle loops (ping-pong between two tool calls) | P0 |
| LOOP-4 | Detect hollow growth (token count rising without productive tool results) | P1 |
| LOOP-5 | Configurable per-session cost ceiling (e.g., $5/session hard limit) | P0 |
| LOOP-6 | Auto-pause session on loop detection, notify operator with one-click resume | P0 |
| LOOP-7 | Auto-kill session at 2x threshold (e.g., 20 identical calls) with Telegram/Slack alert | P1 |
| LOOP-8 | Budget enforcement: daily/monthly spend limits with request blocking when exceeded | P1 |
| LOOP-9 | Smart model downgrading: route low-complexity messages (pings, "hi") to cheapest model | P2 |
| LOOP-10 | Dashboard alert banner for active loop detections and paused sessions | P0 |

**Detection Algorithm:**
```
recentCalls: Array<{ tool: string, argsHash: string, timestamp: number }>
// Sliding window of last M calls per session
// Flag: same (tool, argsHash) appears > N times
// Escalation: warn → pause → kill
```

**Data Source:** `EventFrame` tool call events, session token counters.

### 6.3 LLM Fuel Gauges — Cost & Quota Intelligence (P0 — Must Have)

**Description:** Real-time tracking of LLM API usage, quota consumption, and cost projections.

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| FUEL-1 | Display current quota usage percentage per provider (Anthropic, OpenAI, etc.) | P0 |
| FUEL-2 | Visual gauge/progress bar showing remaining quota capacity | P0 |
| FUEL-3 | Track cumulative daily/weekly/monthly spend across all sessions | P0 |
| FUEL-4 | Show cost breakdown by model (Opus, Sonnet, Haiku, GPT-4, local) | P0 |
| FUEL-5 | Quota reset countdown timer (e.g., "Resets in 3d 4h") | P1 |
| FUEL-6 | Cost projection: "At current rate, you'll hit quota in X hours" | P1 |
| FUEL-7 | Historical cost graph (daily/weekly/monthly trends) | P2 |
| FUEL-8 | Alerting threshold configuration (warn at 80%, critical at 95%) | P2 |
| FUEL-9 | Cost per task/topic attribution (if topic tracking is active) | P3 |

**Data Source:** Provider API usage endpoints, session token counts with model pricing tables.

### 6.4 System Vitals Monitor (P0 — Must Have)

**Description:** Hardware and process health monitoring for Gateway host(s).

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| SYS-1 | CPU usage (overall and per-process for Gateway/Node) | P0 |
| SYS-2 | Memory usage (RSS, heap) for Gateway process | P0 |
| SYS-3 | Disk usage for OpenClaw data directory (`~/.openclaw/`) | P0 |
| SYS-4 | Gateway uptime and version | P0 |
| SYS-5 | Connected channels status (connected/disconnected/error) | P1 |
| SYS-6 | Connected nodes status (online/offline, capabilities) | P1 |
| SYS-7 | Network bandwidth usage (WebSocket, HTTP) | P3 |

**Data Source:** Node.js `process.memoryUsage()`, `os` module, custom Gateway metrics endpoint.

### 6.5 Cron & Task Scheduler UI (P0 — Must Have)

**Description:** Visual management of OpenClaw cron jobs with advanced scheduling primitives.

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| CRON-1 | List all cron jobs with schedule, agent, status, last-run, next-run | P0 |
| CRON-2 | Create new cron job via form (schedule, message, agent, channel) | P0 |
| CRON-3 | Edit existing cron job inline | P0 |
| CRON-4 | Enable/disable cron jobs with toggle | P0 |
| CRON-5 | Delete cron jobs with confirmation | P0 |
| CRON-6 | Manual "Run Now" trigger for any job | P0 |
| CRON-7 | Job execution history (last 50 runs with status, duration, output preview) | P1 |
| CRON-8 | Advanced scheduling primitives (see below) | P1 |
| CRON-9 | Visual calendar/timeline view of scheduled jobs | P2 |
| CRON-10 | Job dependency chains (run B after A completes) | P3 |

**Advanced Scheduling Primitives (CRON-8):**

These are inspired by Jonathan Tsai's production patterns:

| Primitive | Description |
|---|---|
| `run-if-idle` | Execute only when no active sessions are running |
| `run-if-not-run-since` | Ensure minimum freshness (e.g., "at least once per 4 hours") |
| `run-at-least-X-per-period` | SLA enforcement (e.g., "at least 3 times per day") |
| `skip-if-last-run-within` | Debounce (e.g., "skip if ran in last 30 minutes") |
| `conflict-avoidance` | Prevent jobs from overlapping with specific other jobs |
| `priority-queue` | Critical jobs preempt low-priority background work |
| `quota-aware` | Defer execution when quota usage exceeds threshold |

**Data Source:** `cron.*` RPC namespace.

### 6.6 Cerebro — Topic Tracking System (P1 — Should Have)

**Description:** Named after Professor X's machine. Auto-detects conversation topics from agent interactions and organizes them for project-level visibility.

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| TOPIC-1 | Auto-detect topics from session messages (keyword extraction, clustering) | P1 |
| TOPIC-2 | Display topic cards with thread count and last activity | P1 |
| TOPIC-3 | Jump-to-conversation: click topic → see relevant sessions/threads | P1 |
| TOPIC-4 | Manual topic tagging and merging | P2 |
| TOPIC-5 | Topic-level cost aggregation (total tokens/$ spent per topic) | P2 |
| TOPIC-6 | Topic archival and lifecycle management | P3 |
| TOPIC-7 | Topic-based agent routing (auto-assign topics to specialized agents) | P3 |

**Implementation Notes:** For Slack integration, requires `slack.capabilities.threading: all` in OpenClaw config. Topic detection can use TF-IDF or simple keyword frequency over session transcripts.

### 6.7 LLM Router — Model Selection Intelligence (P1 — Should Have)

**Description:** Visual configuration and monitoring of the model routing layer.

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| LLM-1 | Display current routing rules (task type → model mapping) | P1 |
| LLM-2 | Visual editor for routing rules | P1 |
| LLM-3 | Show model usage distribution (pie/bar chart) | P1 |
| LLM-4 | Cost savings calculator (cloud vs. local model attribution) | P2 |
| LLM-5 | Model health status (API reachable, latency, error rate) | P2 |
| LLM-6 | A/B testing: route percentage of tasks to different models and compare quality | P3 |

**Routing Rule Examples:**

| Task Pattern | Model | Rationale |
|---|---|---|
| Complex reasoning, planning | Claude Opus 4.6 | Best quality |
| Code generation, boilerplate | Local (Qwen 3 32B) | Zero API cost |
| RAG / embeddings | Local (nomic-embed) | Zero API cost |
| Documentation, summaries | Claude Sonnet 4.6 | Good quality, lower cost |
| Quick classification | Claude Haiku 4.5 | Fastest, cheapest |

### 6.8 Multi-Instance Aggregation (P1 — Should Have)

**Description:** Connect to multiple OpenClaw Gateway instances and display unified state.

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| MULTI-1 | Register multiple Gateway endpoints (host:port + auth token) | P1 |
| MULTI-2 | Unified dashboard showing all instances with instance labels | P1 |
| MULTI-3 | Instance health indicator (connected/disconnected/degraded) | P1 |
| MULTI-4 | Filter/group views by instance | P1 |
| MULTI-5 | Cross-instance cost aggregation | P2 |
| MULTI-6 | Cross-instance topic correlation | P3 |

**Architecture Note:** Each Gateway exposes its own WebSocket. Mission Control maintains parallel WebSocket connections and merges state client-side.

### 6.9 Governance & Approval Workflows (P1 — Should Have)

**Description:** Human-in-the-loop approval system for sensitive agent actions. Research shows this is table-stakes for production deployments — upgraded from P2 to P1 based on [enterprise AI governance patterns](https://www.permit.io/blog/human-in-the-loop-for-ai-agents-best-practices-frameworks-use-cases-and-demo) and the [frank8ai watchdog system](https://github.com/frank8ai/openclaw-mission-control).

**Graduated Autonomy Model** (shadow → assisted → autonomous):

| Mode | Behavior | Use Case |
|---|---|---|
| **Shadow** | Agent recommends actions, dashboard shows what *would* happen, no execution | Onboarding new agents, building trust |
| **Assisted** | Agent acts with mandatory human approval for configured tools | Production with sensitive operations |
| **Autonomous** | Agent acts freely within approved boundaries, audit-only | Proven agents with established trust |

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| GOV-1 | Approval queue showing pending sensitive actions | P1 |
| GOV-2 | Approve/deny actions from dashboard with optional comment | P1 |
| GOV-3 | Configurable approval rules (which tools/actions require approval) | P1 |
| GOV-4 | Immutable audit trail (append-only JSONL with auditId) | P1 |
| GOV-5 | Graduated autonomy levels per agent (shadow/assisted/autonomous) | P1 |
| GOV-6 | One-time confirmation codes for destructive operations (generate + execute pattern) | P2 |
| GOV-7 | Approval timeout configuration (auto-deny after N minutes) | P2 |
| GOV-8 | Notification integration (Telegram/Slack/Discord push on pending approval) | P2 |
| GOV-9 | Rollback journal: snapshot state before approved writes, keyed by auditId | P2 |

**Data Source:** Gateway tool call events, custom approval state store.

### 6.10 Subagent Hierarchy & Team Coordination (P1 — Should Have)

**Description:** Visualize and manage parent→orchestrator→worker agent trees. Based on [OpenClaw's subagent model](https://docs.openclaw.ai/tools/subagents) (maxSpawnDepth up to 5, maxChildrenPerAgent up to 20) and the [Agent Teams RFC](https://github.com/openclaw/openclaw/discussions/10036).

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| SUB-1 | Visual agent hierarchy tree showing parent→child relationships with live/idle indicators | P1 |
| SUB-2 | Per-agent metrics: token count, cost, duration, model, status | P1 |
| SUB-3 | Subagent spawn/terminate controls from dashboard | P1 |
| SUB-4 | Announce chain visibility (see results flowing up the hierarchy) | P2 |
| SUB-5 | Agent Teams task board (shared task list with dependency tracking, if Teams RFC is adopted) | P2 |
| SUB-6 | Inter-agent message viewer (peer-to-peer messages between teammates) | P2 |
| SUB-7 | Resource limit visualization (current children vs. maxChildrenPerAgent, spawn depth) | P2 |

**Data Source:** `sessions.*` RPC, subagent EventFrames, `~/.openclaw/teams/` (if Agent Teams enabled).

### 6.11 Memory & Workspace Browser (P1 — Should Have)

**Description:** Browse, search, and inspect agent memory and workspace files. Key feature from [robsannaa/mission-control](https://github.com/robsannaa/openclaw-mission-control) (Cmd+K semantic search) and [TenacitOS](https://github.com/carlosazaustre/tenacitOS) (file browser with in-browser editing).

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| MEM-1 | Browse agent memory files (MEMORY.md, memory/*.md) per agent | P1 |
| MEM-2 | Full-text search across memory and workspace files | P1 |
| MEM-3 | Vector/semantic search via OpenClaw's memorySearch (BM25 + sqlite-vec) | P2 |
| MEM-4 | Workspace file browser with preview (markdown rendering, code highlighting) | P2 |
| MEM-5 | Memory file editing with save-back to agent workspace | P2 |
| MEM-6 | Daily journal viewer (agent reflection entries) | P3 |

**Data Source:** Agent workspace filesystem via Gateway, `memorySearch` tool results.

### 6.12 Agent Configuration Manager (P2 — Nice to Have)

**Description:** Visual editor for agent configurations, system prompts, and tool permissions.

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| CONF-1 | View and edit agent system prompts | P2 |
| CONF-2 | Configure tool permissions per agent (allow/deny lists) | P2 |
| CONF-3 | Model profile management (API keys, auth profiles) | P2 |
| CONF-4 | Channel configuration (enable/disable, DM policies) | P2 |
| CONF-5 | Configuration diff view (show changes before applying) | P3 |
| CONF-6 | Configuration version history and rollback | P3 |

### 6.13 Privacy Controls (P1 — Should Have)

**Description:** Controls for safe screenshots and demos.

**Requirements:**

| ID | Requirement | Priority |
|---|---|---|
| PRIV-1 | One-click "demo mode" that masks sensitive data (API keys, names, costs) | P1 |
| PRIV-2 | Configurable masking rules (which fields to redact) | P2 |
| PRIV-3 | Session transcript redaction for export/sharing | P3 |

---

## 7. Architecture & Technical Design

### 7.1 Design Principles

Following the philosophy established by Jonathan Tsai's Command Center:

1. **Minimal footprint** — ~200 KB total, no build dependencies
2. **Vanilla stack** — No React/Vue/Angular. ES modules + vanilla JS
3. **Zero external calls** — No CDN, no telemetry, no analytics
4. **Localhost-first** — Secure by default, optional auth layers
5. **SSE for real-time** — Server-Sent Events, not polling
6. **Single-file server** — Node.js backend in a single module

### 7.2 System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Mission Control Server                      │
│                    (Node.js, port 3777)                        │
│                                                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │   SSE Hub    │  │  REST API    │  │  Static File Server  │ │
│  │ (real-time)  │  │ (/api/*)     │  │  (dashboard SPA)     │ │
│  └──────┬──────┘  └──────┬───────┘  └──────────────────────┘ │
│         │                │                                    │
│  ┌──────┴────────────────┴───────┐                           │
│  │       Gateway Connector        │                           │
│  │  (WebSocket client per GW)     │                           │
│  └──────┬────────────────────────┘                           │
│         │                                                     │
│  ┌──────┴──────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │   State     │  │   Quota      │  │  Topic Detector      │ │
│  │   Aggregator│  │   Tracker    │  │  (Cerebro)           │ │
│  └─────────────┘  └──────────────┘  └──────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐  ┌──────────────┐    ┌──────────────┐
│  Gateway #1  │  │  Gateway #2  │    │  Gateway #N  │
│  (localhost)  │  │  (remote)    │    │  (remote)    │
└──────────────┘  └──────────────┘    └──────────────┘
```

### 7.3 Component Breakdown

#### Backend (Node.js)

| Component | Responsibility |
|---|---|
| `server.js` | HTTP/SSE server, static file serving, routing |
| `gateway-connector.js` | WebSocket client connecting to OpenClaw Gateway(s) |
| `state-aggregator.js` | Merge state from multiple gateways into unified model |
| `quota-tracker.js` | LLM provider quota polling and cost calculation |
| `loop-detector.js` | Sliding-window tool call analysis, circuit breaker enforcement |
| `watchdog.js` | Cron health monitoring, config drift detection, auto-recovery escalation |
| `alert-engine.js` | Smart alert banners (high costs, failed crons, context overflow, loops, offline gateway) |
| `topic-detector.js` | Session transcript analysis for topic extraction |
| `config.js` | Mission Control configuration loading |

#### Frontend (Vanilla JS + ES Modules)

| Module | Responsibility |
|---|---|
| `app.js` | Application bootstrap, SSE connection, routing |
| `dashboard.js` | Main dashboard layout and widget orchestration |
| `sessions.js` | Session list and detail components |
| `fuel-gauges.js` | LLM quota visualization widgets |
| `cron-manager.js` | Cron job CRUD interface |
| `cerebro.js` | Topic tracking visualization |
| `system-vitals.js` | CPU/memory/disk gauges |
| `subagent-tree.js` | Agent hierarchy tree visualization |
| `memory-browser.js` | Memory file browser with search |
| `governance.js` | Approval queue, audit trail, autonomy controls |
| `config-editor.js` | Agent configuration forms |
| `alerts.js` | Smart alert banners and notification center |
| `privacy.js` | Demo mode masking logic |

#### Shared

| File | Purpose |
|---|---|
| `protocol.js` | OpenClaw WebSocket RPC frame encoding/decoding |
| `pricing.js` | LLM model pricing tables (updated periodically) |
| `utils.js` | Date formatting, number formatting, DOM helpers |

### 7.4 Data Flow

```
1. Mission Control Server starts → reads config (gateways, auth tokens)
2. For each gateway:
   a. Opens WebSocket connection (ws://host:port)
   b. Authenticates (token/password)
   c. Subscribes to EventFrames (session updates, cron events)
   d. Polls sessions.list, cron.list periodically (2s cadence)
3. State Aggregator merges data from all gateways
4. SSE Hub pushes deltas to connected browser clients
5. Browser renders updates incrementally (no full page reloads)
6. User actions (cron CRUD, session reset) → REST API → RPC to Gateway
```

### 7.5 Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend runtime | Node.js 22+ | Match OpenClaw's runtime, share protocol code |
| HTTP framework | None (built-in `http` module) | Minimal dependencies |
| Real-time | Server-Sent Events (SSE) | Simpler than WebSocket for server→client push |
| Frontend | Vanilla JS + ES modules | Zero build step, minimal bundle |
| Styling | CSS custom properties (see [Style Guide](OPENCLAW_MC_STYLE_GUIDE.md)) | Dark-first, responsive, zero-dependency |
| Storage | SQLite (cost history, audit trail, alerts), JSON (config), in-memory (live state) | SQLite for persistence (TenacitOS pattern), no external DB |
| Package manager | npm | Standard Node.js tooling |

### 7.6 Gateway Communication Protocol

Mission Control acts as a **WebSocket RPC client** to OpenClaw Gateways:

```javascript
// Connect to Gateway
const ws = new WebSocket('ws://127.0.0.1:18789');

// Authenticate
ws.send(JSON.stringify({
  type: 'connect',
  params: { auth: { token: process.env.OPENCLAW_GATEWAY_TOKEN } }
}));

// Send RPC request
ws.send(JSON.stringify({
  type: 'request',
  id: crypto.randomUUID(),
  method: 'sessions.list',
  params: {}
}));

// Receive response
ws.on('message', (data) => {
  const frame = JSON.parse(data);
  if (frame.type === 'response') { /* handle */ }
  if (frame.type === 'event') { /* push to SSE clients */ }
});
```

**Key RPC Methods Used:**

| Method | Purpose |
|---|---|
| `sessions.list` | List all sessions with metadata |
| `sessions.history` | Get message history for a session |
| `sessions.send` | Send message to a session |
| `agent.reset` | Reset an agent session |
| `cron.list` | List all cron jobs |
| `cron.add` | Create a new cron job |
| `cron.update` | Modify an existing cron job |
| `cron.remove` | Delete a cron job |
| `cron.run` | Manually trigger a cron job |
| `config.get` | Read Gateway configuration |
| `config.set` | Write Gateway configuration |
| `nodes.list` | List connected device nodes |
| `sessions.spawn` | Spawn a subagent session |
| `sessions.history` | Get full message history (for loop detection, transcript viewer) |

---

## 8. Security Model

### 8.1 Threat Model

Mission Control inherits OpenClaw's **single-operator trust model**:

| Trust Boundary | Assumption |
|---|---|
| Dashboard operator | Fully trusted (same person as Gateway operator) |
| Browser → MC Server | Localhost or trusted network |
| MC Server → Gateway | Authenticated WebSocket (token/password) |
| External network | Not exposed by default |

### 8.2 Authentication Layers

| Mode | Description | Use Case |
|---|---|---|
| **None** (localhost) | No auth when bound to `127.0.0.1` | Personal machine, default |
| **Token** | Bearer token in HTTP header | LAN/Tailscale access |
| **Tailscale** | Identity from Tailscale headers | Remote access, zero-config |
| **Cloudflare Access** | JWT validation via CF headers | Public access with SSO |
| **Password + TOTP MFA** | PBKDF2 hashing + optional TOTP second factor | Hardened remote access (from [tugcantopaloglu's dashboard](https://github.com/tugcantopaloglu/openclaw-dashboard)) |

### 8.3 Security Controls

| Control | Implementation |
|---|---|
| API keys never in UI | Masked in all views, never sent to frontend |
| No external calls | Zero telemetry, no CDN, no analytics |
| CORS restricted | Only same-origin requests accepted |
| CSP headers | Strict Content-Security-Policy |
| Gateway tokens | Stored server-side only, never in browser |
| Rate limiting | Basic request throttling on REST API |
| Login lockout | 5 failed attempts → 15-minute lockout (TenacitOS pattern) |
| Command allowlist | Read-only terminal blocks dangerous commands (env, curl, rm, node, python) |

---

## 9. UI/UX Design

> **Design System:** All colors, typography, spacing, components, and motion rules are defined in the companion [Design System Style Guide](OPENCLAW_MC_STYLE_GUIDE.md). This section covers layout structure and interaction patterns. The style guide is the canonical source of truth for all visual implementation.

### 9.1 Layout

```
┌─────────────────────────────────────────────────────────────┐
│  [Logo] Mission Control          [Demo Mode] [Settings] [?] │
├────────┬────────────────────────────────────────────────────┤
│        │                                                     │
│  Nav   │   Main Content Area                                 │
│        │                                                     │
│  [D]   │   ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  [S]   │   │ Sessions │ │  Fuel    │ │ System Vitals    │  │
│  [C]   │   │  Active  │ │ Gauges   │ │ CPU/Mem/Disk     │  │
│  [T]   │   │  3 / 10  │ │ 67%     │ │ ████░░ 42%       │  │
│  [R]   │   └──────────┘ └──────────┘ └──────────────────┘  │
│  [G]   │                                                     │
│  [⚙]  │   ┌─────────────────────────────────────────────┐  │
│        │   │              Session List                    │  │
│        │   │ ┌─────────────────────────────────────────┐ │  │
│        │   │ │ 🟢 main/slack/#general  opus  12.4k tok │ │  │
│        │   │ │ 🟢 main/telegram/+1555  sonnet 3.2k tok │ │  │
│        │   │ │ 🟡 research/slack/#data  opus  45.1k tok│ │  │
│        │   │ │ ⚪ helper/discord/#dev   idle            │ │  │
│        │   │ └─────────────────────────────────────────┘ │  │
│        │   └─────────────────────────────────────────────┘  │
│        │                                                     │
│  Nav:  │   ┌──────────────────────────────────────────────┐ │
│  D=Dash│   │          Cron Jobs (next 24h)                │ │
│  S=Sess│   │  09:00 daily-standup ✅  Last: 2m ago        │ │
│  C=Cron│   │  12:00 inbox-sweep   ⏳  Next: 3h 22m       │ │
│  T=Top │   │  18:00 daily-report  ⏳  Next: 9h 22m       │ │
│  R=Rout│   └──────────────────────────────────────────────┘ │
│  G=Gov │                                                     │
│  ⚙=Cfg│                                                     │
├────────┴────────────────────────────────────────────────────┤
│  Gateway: localhost:18789 ✅  │  Uptime: 14d 3h  │  v0.1.0  │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 Design Tokens

See [Style Guide — Color System](OPENCLAW_MC_STYLE_GUIDE.md#color-system) for the complete token reference. Key tokens summarized here for context:

| Category | Examples | Reference |
|---|---|---|
| Backgrounds | `--bg-primary` `#0d1117`, `--bg-secondary` `#161b22` | [Color System](OPENCLAW_MC_STYLE_GUIDE.md#color-system) |
| Text | `--text-primary` `#f0f6fc`, `--text-secondary` `#8b949e` | [Color System](OPENCLAW_MC_STYLE_GUIDE.md#color-system) |
| Status | `--status-green` `#3fb950`, `--status-amber` `#d29922`, `--status-red` `#f85149` | [Color System](OPENCLAW_MC_STYLE_GUIDE.md#color-system) |
| Typography | System sans-serif (body), JetBrains Mono (metrics) | [Typography](OPENCLAW_MC_STYLE_GUIDE.md#typography) |
| Spacing | 4px base unit, 8/12/16/24/32/48px scale | [Spacing & Layout](OPENCLAW_MC_STYLE_GUIDE.md#spacing--layout) |
| Components | Buttons, badges, gauges, tables, alerts, modals | [Components](OPENCLAW_MC_STYLE_GUIDE.md#components) |
| Data Viz | Inline SVG only — sparklines, bar charts, gauge arcs, trees | [Data Visualization](OPENCLAW_MC_STYLE_GUIDE.md#data-visualization) |

### 9.3 Responsive Breakpoints

See [Style Guide — Layout Patterns](OPENCLAW_MC_STYLE_GUIDE.md#layout-patterns) for full layout specifications.

| Breakpoint | Layout |
|---|---|
| >= 1200px | Full sidebar (200px) + main content grid |
| 768-1199px | Collapsed sidebar (48px icons only) + main content |
| < 768px | Bottom tab bar (56px) + stacked single-column cards |

### 9.4 Implementation Constraints

Per the [Style Guide — Implementation Constraints](OPENCLAW_MC_STYLE_GUIDE.md#implementation-constraints):

- **Total bundle target:** < 220KB (max 365KB) — HTML < 5KB, CSS < 15KB, JS < 100KB, Font ~95KB
- **No backdrop blur**, no Sass/PostCSS/Tailwind, no external CDN calls
- **Minimal animation:** Only `fadeIn`, `slideDown`, `countUp`, `pulse` permitted. `prefers-reduced-motion` disables all
- **Accessibility:** WCAG 2.2 AA minimum. Color-independent status indicators (shape + text alongside color)
- **Browser support:** Last 2 versions of Chrome/Edge, Firefox, Safari

---

## 10. Integration Points

### 10.1 OpenClaw Gateway (Primary)

- **Protocol:** WebSocket RPC (JSON frames)
- **Port:** 18789 (configurable)
- **Auth:** Token or password
- **Capabilities:** Full session/cron/config/node management

### 10.2 LLM Provider APIs (Cost Tracking)

| Provider | Endpoint | Data |
|---|---|---|
| Anthropic | `api.anthropic.com/v1/usage` | Token usage, quota |
| OpenAI | `api.openai.com/v1/usage` | Token usage, quota |
| Local (Ollama) | `localhost:11434/api/tags` | Model list, no cost |

### 10.3 Messaging Platforms (Read-Only Context)

Mission Control does **not** directly connect to Slack/Telegram/etc. It reads session data through the Gateway, which already handles channel connections.

### 10.4 OpenTelemetry (Optional — Advanced Observability)

OpenClaw's Diagnostic-OTel plugin exports traces, metrics, and logs via OTLP. Mission Control can optionally consume these for deeper observability:

| Signal | Data Available |
|---|---|
| Traces | Model call spans, tool execution spans, webhook processing |
| Metrics | Token usage counters, cost histograms, context size, run duration, queue depth |
| Logs | Structured gateway logs via OTLP |

**Integration pattern:** Mission Control can either (a) consume OTel data directly as an OTLP receiver, or (b) connect to an existing OTel backend (SigNoz, Grafana) for historical analytics. This is the path to production-grade observability without reinventing metrics collection. See [monitoring OpenClaw with OpenTelemetry](https://signoz.io/blog/monitoring-openclaw-with-opentelemetry/).

### 10.5 ClawHub (Optional)

If the operator uses ClawHub skills, Mission Control can display installed skills and their usage statistics.

### 10.6 TappsMCP Integration (Optional)

For projects using TappsMCP alongside OpenClaw:
- Display code quality scores from `tapps_score_file` results
- Show quality gate pass/fail status
- Integrate security scan results into the governance approval queue

---

## 11. Deployment & Distribution

### 11.1 Installation Methods

**Method 1: ClawHub (Recommended)**
```bash
clawhub install <our-org>/mission-control
```

**Method 2: npm Global**
```bash
npm install -g openclaw-mission-control
mission-control start
```

**Method 3: Git Clone**
```bash
git clone https://github.com/<our-org>/openclaw-mission-control
cd openclaw-mission-control
node server.js
```

**Method 4: Docker**
```bash
docker run -p 3777:3777 \
  -e OPENCLAW_GATEWAY_URL=ws://host.docker.internal:18789 \
  -e OPENCLAW_GATEWAY_TOKEN=your-token \
  ghcr.io/<our-org>/mission-control:latest
```

### 11.2 Configuration

```json
// mission-control.json
{
  "port": 3777,
  "gateways": [
    {
      "name": "Primary",
      "url": "ws://127.0.0.1:18789",
      "token": "${OPENCLAW_GATEWAY_TOKEN}"
    },
    {
      "name": "Research VM",
      "url": "ws://research.tailnet:18789",
      "token": "${RESEARCH_GATEWAY_TOKEN}"
    }
  ],
  "auth": {
    "mode": "none",
    "token": ""
  },
  "refresh_interval_ms": 2000,
  "quota_tracking": {
    "anthropic_api_key": "${ANTHROPIC_API_KEY}",
    "openai_api_key": "${OPENAI_API_KEY}"
  },
  "features": {
    "cerebro": true,
    "governance": false,
    "cost_tracking": true
  }
}
```

### 11.3 System Requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| Node.js | 22+ | 22 LTS |
| Memory | 64 MB | 128 MB |
| Disk | 10 MB | 50 MB (with logs) |
| OpenClaw | 1.x | Latest stable |
| OS | Linux, macOS, Windows (WSL) | Linux/macOS |

---

## 12. Competitive Landscape

### 12.1 Existing Mission Control Projects (9+ analyzed)

| Project | Stars | Stack | Key Strength | Key Gap |
|---|---|---|---|---|
| [Tsai's Command Center](https://github.com/jontsai/openclaw-command-center) | — | Vanilla JS, SSE | Production-proven, ~200KB, advanced scheduling primitives | Single-instance, no governance, personal tool |
| [abhi1693/mission-control](https://github.com/abhi1693/openclaw-mission-control) | 1.3k | Next.js + Python, Docker | Team-oriented, API-first, approval workflows | Heavy (Docker required), complex setup |
| [robsannaa/mission-control](https://github.com/robsannaa/openclaw-mission-control) | — | Next.js 16, React 19 | Zero-config auto-discovery, vector memory search (Cmd+K), subagent management, Tailscale UI, gateway diagnostics | Large dependency tree |
| [TenacitOS](https://github.com/carlosazaustre/tenacitOS) | — | Next.js 15, React Three Fiber | 3D office viz, SQLite cost analytics, memory/file browser, notification center | Novelty 3D UI may distract |
| [mudrii/openclaw-dashboard](https://github.com/mudrii/openclaw-dashboard) | 60 | Vanilla HTML/JS, Go+Python backends | True zero-dependency, SVG charts, immutable state snapshots, 5-level model attribution, AI chat panel | No governance or team features |
| [frank8ai/mission-control](https://github.com/frank8ai/openclaw-mission-control) | — | Next.js, Linear integration | Watchdog incident detection, workspace-guard (config drift), audit trail with rollback journal, confirmation codes for destructive ops | Tightly coupled to Linear |
| [ClawDeck](https://github.com/clawdeckio/clawdeck) | — | Rails + Hotwired | Kanban UI, real-time Turbo updates | Ruby stack, limited monitoring |
| [ClawSuite](https://clawsuite.io/) | — | Self-hosted | Multi-model chat (switch mid-thread), sub-agent timeline, gateway management | Closed ecosystem |
| [Clawtrol](https://github.com/) | 18 | TypeScript | Remote screen viewing for headless machines, modular panel architecture | Small community |
| [LobsterBoard](https://github.com/) | 382 | JavaScript | 50+ drag-and-drop widgets | BSL 1.1 license (not MIT) |
| [AI Maestro](https://github.com/) | 324 | TypeScript | Peer-mesh networking, Agent Messaging Protocol (agent-to-agent direct comms) | Enterprise complexity |

### 12.2 Key Patterns Borrowed from Competitors

| Pattern | Source | Why It Matters |
|---|---|---|
| **Immutable state snapshots** | mudrii/dashboard | Prevents fetch/render race conditions in real-time UI |
| **5-level model cost attribution** | mudrii/dashboard | Accurate cost: session override → subagent model → cron model → agent default → global default |
| **Zero-config auto-discovery** | robsannaa/MC | `which openclaw` + common paths + `~/.openclaw` — eliminates setup friction |
| **Watchdog with escalation ladder** | frank8ai/MC | Gentle restart → aggressive recovery → emergency kill — auto-heals without operator |
| **Workspace-guard** | frank8ai/MC | Detects config drift (e.g., workspace pointing to `/tmp/empty`) and auto-repairs |
| **Confirmation codes for writes** | frank8ai/MC | `npm run tasks -- confirm` → `--confirm "CONFIRM <CODE>"` — prevents accidental destructive actions |
| **Graduated autonomy** | Enterprise AI patterns | Shadow → assisted → autonomous — build trust before granting agent freedom |
| **Smart model downgrading** | TokPinch proxy | Route "hi" pings from Opus ($15/MTok) to Haiku ($0.80/MTok) = 95% savings on low-value calls |

### 12.3 Our Differentiation

| Differentiator | Details |
|---|---|
| **Zero-dependency minimal stack** | Following Tsai + mudrii pattern: vanilla JS, no build step, <500KB |
| **Loop detection circuit breaker** | No competitor has behavioral watchdog for stuck agents — only process-level monitoring |
| **Multi-instance first** | Designed for 1–10+ gateways from day one |
| **Advanced scheduling primitives** | `run-if-idle`, `quota-aware`, `conflict-avoidance` beyond basic cron |
| **Graduated governance** | Shadow → assisted → autonomous model with immutable audit trail |
| **Subagent tree + Agent Teams** | Visual hierarchy + RFC-based team coordination (unique combination) |
| **Memory browser with semantic search** | Cmd+K workspace search without external vector DB |
| **Cerebro topic intelligence** | Auto-organization of agent work by project/topic |
| **TappsMCP integration** | Code quality and security scanning in the governance pipeline |
| **Open source (MIT)** | Self-hosted, no vendor lock-in, no BSL restrictions |

---

## 13. Phased Roadmap

### Phase 1: Foundation + Safety (Weeks 1–3)

**Goal:** Minimal viable dashboard with session visibility, system vitals, **and loop detection**. Safety-first: the circuit breaker ships in v0.1 because a dashboard without cost protection is a liability.

| Epic | Description | Effort |
|---|---|---|
| E1 | Project scaffolding (Node.js server, static serving, config loader, SQLite init) | 2 days |
| E2 | Gateway Connector (WebSocket client, auth, RPC protocol, auto-reconnect) | 3 days |
| E3 | Session Dashboard (list, status, token counts, real-time updates via SSE) | 3 days |
| E4 | System Vitals (CPU, memory, disk, gateway uptime, channel status) | 2 days |
| E5 | **Loop Detection & Circuit Breaker** (sliding window detector, pause/kill, alert banner) | 3 days |
| E6 | Basic UI shell (nav, layout, dark theme, responsive, smart alert banners) | 2 days |

**Deliverable:** Dashboard with live sessions, system health, and runaway agent protection.

### Phase 2: Cost Intelligence & Scheduling (Weeks 4–6)

**Goal:** LLM cost tracking with budget enforcement and visual cron management.

| Epic | Description | Effort |
|---|---|---|
| E7 | LLM Fuel Gauges (provider quota polling, cost calculation, gauges) | 3 days |
| E8 | **Budget Enforcement** (daily/monthly limits, per-session ceilings, request blocking) | 2 days |
| E9 | **5-Level Cost Attribution** (session→subagent→cron→agent→global model resolution) | 2 days |
| E10 | Cron Manager UI (list, CRUD, run-now, execution history) | 4 days |
| E11 | Advanced Scheduling Primitives (run-if-idle, quota-aware, conflict-avoidance) | 3 days |

**Deliverable:** Full cost visibility with budget enforcement and visual task scheduling.

### Phase 3: Agent Hierarchy & Memory (Weeks 7–9)

**Goal:** Subagent management, memory browser, and multi-gateway support.

| Epic | Description | Effort |
|---|---|---|
| E12 | Multi-Gateway Connector (parallel connections, state merging) | 3 days |
| E13 | **Subagent Hierarchy Tree** (visual parent→child tree, metrics, spawn/terminate) | 3 days |
| E14 | **Memory & Workspace Browser** (file browser, full-text search, markdown preview) | 3 days |
| E15 | Privacy Controls (demo mode, field masking) | 1 day |

**Deliverable:** Multi-instance dashboard with agent hierarchy visualization and memory browser.

### Phase 4: Governance & Intelligence (Weeks 10–13)

**Goal:** Approval workflows, topic tracking, and configuration management.

| Epic | Description | Effort |
|---|---|---|
| E16 | **Governance Engine** (graduated autonomy, approval queue, immutable audit trail, rollback journal) | 5 days |
| E17 | Cerebro Topic Detector (keyword extraction, clustering, topic cards, cost attribution) | 4 days |
| E18 | LLM Router Visualization (routing rules, model distribution, health status) | 2 days |
| E19 | Agent Config Editor (system prompts, tool permissions, channels, diff view) | 3 days |
| E20 | Session Inspector (transcript viewer, tool call traces) | 2 days |
| E21 | Documentation & Distribution (README, ClawHub package, Docker image) | 2 days |

**Deliverable:** Production-ready Mission Control with governance, topic intelligence, and configuration management.

### Phase 5: Advanced Features (Weeks 14+)

| Epic | Description |
|---|---|
| E22 | **Watchdog & Self-Healing** (cron health monitoring, config drift detection, escalation ladder) |
| E23 | **Agent Teams Integration** (shared task board, peer messaging, if OpenClaw Agent Teams RFC lands) |
| E24 | Historical analytics (SQLite-backed cost trends, usage patterns, session statistics) |
| E25 | **OpenTelemetry Integration** (optional OTLP consumer for traces/metrics/logs) |
| E26 | Smart model downgrading proxy (route pings to cheapest model, 95% savings on low-value calls) |
| E27 | Alerting system (quota thresholds, error rates, downtime → Telegram/Slack/Discord push) |
| E28 | TappsMCP integration (quality scores, security scans in governance pipeline) |
| E29 | Voice harness integration (STT/TTS for hands-free operation) |

---

## 14. Success Metrics

### Adoption Metrics

| Metric | Target (6 months) |
|---|---|
| GitHub stars | 1,000+ |
| ClawHub installs | 500+ |
| Active users (weekly) | 200+ |
| Contributors | 15+ |

### Operational Metrics

| Metric | Target |
|---|---|
| Dashboard load time | < 500ms |
| SSE update latency | < 100ms |
| Memory footprint | < 128 MB RSS |
| Bundle size | < 500 KB |
| Gateway reconnect time | < 5 seconds |

### User Impact Metrics

| Metric | Measurement |
|---|---|
| LLM cost savings | User-reported reduction in overage charges |
| Time saved on cron management | Reduction in CLI config edits |
| Incident detection time | Time from error to operator awareness |
| Topic organization satisfaction | Survey / GitHub discussions feedback |

---

## 15. Open Questions

### Resolved by Research

| # | Question | Resolution |
|---|---|---|
| Q1 | Build on Tsai's Command Center or start fresh? | **Start fresh, borrow patterns.** Tsai's is a personal tool. mudrii/dashboard proves zero-dep vanilla JS works at higher quality with Go backend + immutable state pattern. Borrow the architectural patterns (SSE, state snapshots, 2s refresh) but own the codebase. |
| Q5 | Do we need SQLite or is in-memory sufficient? | **SQLite required.** TenacitOS proves SQLite (better-sqlite3) is the right persistence layer — cost history, audit trail, alert state, and topic data all need persistence across restarts. In-memory for live state, SQLite for everything historical. |
| Q6 | Support Next.js/Docker as alternative? | **No.** Our differentiation is zero-dependency simplicity. The Next.js ecosystem (abhi1693, robsannaa, TenacitOS) is well-served. The gap is a production-grade dashboard that works with `node server.js`. |
| Q8 | Governance approvals via Slack/Discord? | **Yes, as P2.** frank8ai's pattern shows Telegram/Slack notifications for pending approvals are essential for mobile operators. Dashboard is primary, notifications are supplementary. |

### Still Open

| # | Question | Impact | Status |
|---|---|---|---|
| Q2 | Should multi-instance support use Gateway mesh protocol or parallel connections? | Architecture | **Open** — mesh.* RPC namespace exists but is undocumented. Default to parallel connections. |
| Q3 | What LLM provider APIs expose quota/usage data? | Cost tracking | **Partially resolved** — OpenClaw tracks tokens in session JSONL files. Provider APIs (Anthropic/OpenAI) have usage endpoints but rate-limited. Session-based counting may be sufficient. |
| Q4 | Cerebro topic detection: client-side or server-side? | Performance | **Open** — Server-side for privacy. TF-IDF over session transcripts is lightweight enough for Node.js. |
| Q7 | How do we handle Gateway protocol version changes? | Compatibility | **Open** — Need version negotiation. mudrii solves this with a `refresh.sh` script that reads raw files instead of RPC. Consider both paths. |
| Q9 | Should we include a built-in chat panel to agents? | Scope | **Open** — mudrii and ClawSuite both route chat through Gateway's OpenAI-compatible endpoint. Low effort, high value for debugging. |
| Q10 | Should the Go backend pattern (mudrii) replace or complement Node.js? | Architecture | **Open** — Go binary is 6.2MB, 37K req/s, embedded HTML, stale-while-revalidate caching. Node.js matches OpenClaw's runtime. Could offer both. |
| Q11 | Should we support the OpenClaw Agent Teams RFC natively or wait for upstream? | Timing | **Open** — RFC is in PR #27382 with active implementation. Building now risks API churn, but early support differentiates. |

---

## 16. References

### Primary Sources

- [Jonathan Tsai — Building Mission Control for My AI Workforce](https://www.jontsai.com/2026/02/12/building-mission-control-for-my-ai-workforce-introducing-openclaw-command-center) — The blog post that inspired this project
- [YouTube Video](https://youtu.be/RhLpV6QDBFE?si=2DoBvFtdY9CDyeLw) — Video walkthrough of the Command Center
- [OpenClaw GitHub](https://github.com/openclaw/openclaw) — Core framework (248k+ stars)
- [OpenClaw Documentation](https://docs.openclaw.ai/) — Official docs

### Architecture References

- [OpenClaw Architecture Overview (DeepWiki)](https://deepwiki.com/openclaw/openclaw) — Detailed Gateway internals
- [OpenClaw Gateway Protocol](https://openclawcn.com/en/docs/gateway/protocol/) — WebSocket RPC specification
- [OpenClaw Security Model](https://docs.openclaw.ai/gateway/security) — Authentication and authorization
- [OpenClaw Cron Service](https://docs.openclaw.ai/automation/cron-jobs) — Scheduling system

### Existing Implementations

- [abhi1693/openclaw-mission-control](https://github.com/abhi1693/openclaw-mission-control) — Next.js + Python, Docker, team-oriented
- [robsannaa/openclaw-mission-control](https://github.com/robsannaa/openclaw-mission-control) — Next.js 16, auto-discovery, vector memory search, subagent management
- [TenacitOS](https://github.com/carlosazaustre/tenacitOS) — Next.js 15, 3D office viz, SQLite cost analytics
- [mudrii/openclaw-dashboard](https://github.com/mudrii/openclaw-dashboard) — Zero-dependency, Go+Python backends, immutable state pattern
- [frank8ai/openclaw-mission-control](https://github.com/frank8ai/openclaw-mission-control) — Watchdog, incident detection, Linear integration, audit trail
- [ClawDeck](https://github.com/clawdeckio/clawdeck) — Rails-based Kanban dashboard
- [ClawSuite](https://clawsuite.io/) — Multi-model chat, agent orchestration
- [ClawControl](https://clawcontrol.dev/) — Commercial managed control plane
- [Claw Desktop](https://claw.so/) — Electron desktop app
- [Best OpenClaw Dashboards Comparison](https://www.bitdoze.com/best-openclaw-dashboards/) — 9-project landscape analysis

### Critical Safety & Cost References

- [OpenClaw Issue #16808: Stuck Agent Loop Detection](https://github.com/openclaw/openclaw/issues/16808) — 1,535 identical calls, $150 wasted, proposed detection algorithm
- [TokPinch Cost Proxy](https://dev.to/tobiasbond/how-i-built-a-cost-proxy-to-stop-openclaw-from-burning-my-api-budget-25i3) — Budget enforcement, loop detection, smart model downgrading
- [Monitoring OpenClaw with OpenTelemetry](https://signoz.io/blog/monitoring-openclaw-with-opentelemetry/) — OTel integration patterns
- [OpenClaw Token Use & Costs](https://docs.openclaw.ai/reference/token-use) — Official token tracking docs

### Multi-Agent & Orchestration References

- [Agent Teams RFC](https://github.com/openclaw/openclaw/discussions/10036) — Coordinated multi-agent with shared state, peer messaging, task dependencies
- [OpenClaw Subagents](https://docs.openclaw.ai/tools/subagents) — Parent→orchestrator→worker hierarchy, resource limits
- [Deterministic Subagent Spawning](https://github.com/openclaw/openclaw/issues/18136) — Bypassing LLM decision for reliable orchestration
- [Mission Control Agent Squads](https://www.dan-malone.com/blog/mission-control-ai-agent-squads) — Heartbeat coordination, @mention routing

### Governance & Enterprise Patterns

- [Human-in-the-Loop for AI Agents](https://www.permit.io/blog/human-in-the-loop-for-ai-agents-best-practices-frameworks-use-cases-and-demo) — HITL/HOTL/HIC models, graduated autonomy
- [2026 Guide to Agentic Workflow Architectures](https://www.stack-ai.com/blog/the-2026-guide-to-agentic-workflow-architectures) — Shadow → assisted → autonomous patterns

### Related Architecture

- [OpenClaw System Architecture Explained](https://ppaolo.substack.com/p/openclaw-system-architecture-overview) — Deep dive blog post
- [Complete OpenClaw Architecture That Scales](https://medium.com/@rentierdigital/the-complete-openclaw-architecture-that-actually-scales-memory-cron-jobs-dashboard-and-the-c96e00ab3f35) — Production patterns
- [OpenClaw Memory Architecture](https://medium.com/@shivam.agarwal.in/agentic-ai-openclaw-moltbot-clawdbots-memory-architecture-explained-61c3b9697488) — BM25 + vector search internals

---

*This PRD is a living document. Update as research continues and decisions are made on the open questions above.*
