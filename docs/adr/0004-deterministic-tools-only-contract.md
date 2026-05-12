# 4. Deterministic-tools-only contract

Date: 2026-05-02

## Status

accepted

## Context

A code-quality MCP server can deliver value either by (a) calling LLMs internally to score, summarize, or rewrite code, or (b) running deterministic checkers (ruff, mypy, bandit, radon, vulture, pylint, pip-audit, AST analyzers) and aggregating their structured output. Approach (a) gives richer responses but makes the same input produce different outputs across runs, makes test fixtures brittle, introduces token cost, and forces the consuming agent to trust an opaque sub-LLM's judgment.

## Decision

**All TappsMCP and DocsMCP tools are deterministic.** No LLM calls in the tool execution chain. Same input — same output. When an external checker is missing on the system, the tool falls back to AST-based analysis and marks the result with `degraded: true` so callers can react. Generated content (READMEs, ADRs, epics) is template-driven, not LLM-rewritten — `docs_generate_*` tools accept fields and emit deterministic markdown.

## Consequences

**Positive:** Test fixtures are stable; CI is reproducible; no provider lock-in. Consumers (agents, scripts, CI jobs) can trust tool output as a fact source instead of as a recommendation. Zero per-call cost beyond local CPU.

**Negative:** Tools cannot summarize or explain in natural language — that work stays on the consuming agent. Some quality signals (e.g. "is this comment misleading?") are out of scope. Acceptable: those judgments belong in the agent layer, not the tool layer.
