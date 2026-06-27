# 25. Light domain playbooks (not RAG experts)

Date: 2026-06-26

## Status

Accepted

## Context

EPIC-94 removed the RAG-backed expert consultation system (`tapps_consult_expert`, vector indices, business experts). Agents lost domain-shaped workflows (testing, security, frontend) without losing the shared TAPPS quality pipeline. [ADR-0014](0014-brain-central-doc-rag-big-bang.md) explicitly excludes reviving EPIC-94 expert consultation. Industry practice (2026) favors **skills + static playbooks + deterministic tools** over vector personas for code work.

## Decision

Ship a **light playbook layer**:

1. **Bundled markdown playbooks** in `tapps_core.playbooks.data` with a registry in `tapps_core.playbooks.registry`.
2. **MCP tool** `tapps_domain_playbook(domain)` — deterministic file lookup + metadata (deferred on `nlt-build`).
3. **Skills** `tapps-domain-*` and `tapps-flow-*` orchestrating existing TAPPS tools; all close with `/tapps-finish-task`.
4. **Checklist task types** `qa` and `frontend` for policy variants.
5. **DocsMCP enrichment** via static playbook excerpts (no network in sync path).

Persona voice remains optional via [agency-agents](https://github.com/msitarzewski/agency-agents) — not forked into `tapps_init`.

## Consequences

**Positive:** Domain routing restored; ADR-0004 preserved; no per-repo vector indices; epic/story enrichment useful again.

**Negative:** Playbook content must be maintained manually; no LLM-synthesized “expert answers.”

**Neutral:** Tool count 42 → 43; `nlt-build` deferred tools +1.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Full EPIC-94 RAG revival | Violates ADR-0004/0014; stale indices; duplicates Context7 |
| 112 personas in tapps_init | Maintenance fork of agency-agents |
| Role-specific quality gates | Agents bypass shared pipeline |
