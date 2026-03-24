---
last_reviewed: 2026-03-24
---

# Modularization and boundaries

## Goals

- **Change isolation** — Teams can evolve modules without constant cross-team releases.
- **Testability** — Clear seams for unit vs integration tests.
- **Operational clarity** — Failure domains and scaling units are obvious.

## Patterns

### Modular monolith

- **Single deployable** with **strict package/module boundaries** enforced by lint rules or dependency matrices.
- Prefer **domain modules** over technical layers when the product is domain-heavy.
- Use **anti-corruption layers** at integration points (external APIs, legacy DBs).

### Microservices (when earned)

- Extract when **independent scaling**, **team ownership**, or **release cadence** truly differ.
- Pay the **network + ops** tax deliberately: tracing, idempotent messaging, contract tests.

### Bounded contexts (DDD)

- Align **ubiquitous language** and **aggregates** with business capabilities.
- **Context maps** document upstream/downstream relationships (open host, conformist, ACL).

## Boundary tests

- **Import rules** — e.g. inner domains must not import outer UI shells.
- **Contract tests** at module APIs (consumer-driven where possible).
- **Performance budgets** per module for hot paths.

## Migration

- **Strangler fig** for legacy: route traffic slice-by-slice behind stable facades.
- **Feature flags** decouple rollout from deployment.

## UX and API alignment

- Stable **public API** surfaces (REST/GraphQL/events) should match **published** module contracts; coordinate with **api-design-integration** expert content.
