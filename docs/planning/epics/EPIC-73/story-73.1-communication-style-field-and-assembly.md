# Story 73.1 — Add communication_style field and wire into answer assembly

<!-- docsmcp:start:user-story -->
> **As a** TappMCP maintainer, **I want** experts to optionally define a communication style or example phrases, **so that** consultation answers use domain-appropriate tone and phrasing.
<!-- docsmcp:end:user-story -->

**Points:** 2 | **Size:** S

## Description

Add optional `communication_style: str = ""` to ExpertConfig and business config. In engine, after persona and critical_rules, if set append "Respond in this style: {communication_style}". Add pilot values for Testing and Security. Add unit tests and update docs. Keep preamble concise.

## Tasks

- [ ] Add optional `communication_style` to ExpertConfig and business entry
- [ ] Wire into engine after persona and critical_rules
- [ ] Add pilot values for Testing and Security in registry
- [ ] Unit tests for with/without field; update knowledge README or EXPERT_CONFIG_GUIDE

## Acceptance Criteria

- [ ] Optional field added and wired; default empty; backward compatible
- [ ] At least 2 experts have non-empty communication_style
- [ ] Tests pass; documentation updated

## Definition of Done

- [ ] Schema, engine, registry, docs, and tests updated
