---
name: tapps-research
user-invocable: true
description: >-
  Research a technical question using domain experts and library docs.
  Combines expert consultation with docs lookup for comprehensive answers.
allowed-tools: mcp__tapps-mcp__tapps_lookup_docs
argument-hint: "[question]"
context: fork
model: claude-sonnet-4-6
---

Research a technical question using TappsMCP:

1. Call `mcp__tapps-mcp__tapps_lookup_docs` with the primary library or framework
2. For multi-domain questions, call `tapps_lookup_docs` once per relevant domain
3. Synthesize findings into a clear, actionable answer
4. Include confidence notes and suggest follow-up lookups if needed
