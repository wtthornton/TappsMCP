---
last_reviewed: 2026-03-24
---

# EU AI Act — developer-oriented overview

## Purpose

This note orients engineering teams on how the **EU Artificial Intelligence Act** intersects with software delivery. It is **not legal advice**. Pair with organizational legal/privacy review for binding obligations.

## Scope recap

The Act applies along a **risk-based ladder** (minimal → limited → high-risk → unacceptable). Most general-purpose coding assistants in the IDE are **not** “high-risk AI systems” by themselves, but **products you ship** may be if they perform regulated functions (biometrics, critical infrastructure, employment scoring, etc.).

## Practical buckets for builders

### 1. GPAI (general-purpose AI) providers vs deployers

- **Model/API vendors** face transparency, documentation, and (for systemic models) additional obligations.
- **Application teams** integrating models are often **deployers** or **users** under the Act: you must map whether your product falls into a high-risk **use case** listed in Annex III.

### 2. High-risk systems

If your product is high-risk:

- **Quality management** and **risk management** processes are expected throughout the lifecycle.
- **Data governance** for training/validation must be documented where you control those datasets.
- **Human oversight**, **accuracy/robustness/cybersecurity**, and **logging** (proportionate, privacy-preserving) are recurring themes.
- **Conformity assessment** paths depend on category; coordinate with legal early.

### 3. Prohibited practices

Unacceptable-risk practices (e.g. certain manipulative or social-scoring uses) must be **designed out**—not mitigated post hoc.

## Interplay with GDPR

- Processing **personal data** for training, fine-tuning, inference logging, or user profiling remains under **GDPR** (lawful basis, DPIA, data subject rights, retention).
- **DPIAs** should explicitly cover **AI-specific risks** (automated decision-making, re-identification, prompt logging, vendor subprocessors).
- See [GDPR Requirements and Compliance](gdpr.md) for baseline privacy engineering.

## Interplay with product security

- **Robustness and cybersecurity** expectations in the AI Act align with secure SDLC work: supply chain for models, secrets handling, prompt/tool injection defenses, and incident response.
- For implementation patterns, consult the **security** expert knowledge on **AI and agent security** (`ai-agent-security.md`).

## Documentation you should maintain (engineering)

1. **System card / model fact sheet** — intended use, limits, known failure modes, evaluation summaries.
2. **Change log** for prompts, tools, and model versions affecting user-facing behavior.
3. **Map of data flows** — what personal data hits which environments (edge, backend, third-party APIs).
4. **Human oversight points** — where a human must approve, review, or override.

## Timeline awareness

Deadlines and delegated acts evolve. Treat dates in static knowledge as **indicative**; verify against current EU official texts and your counsel. The GDPR knowledge file’s “Recent Developments” section tracks high-level 2025–2026 legislative motion.

## Further reading (authoritative)

- Consolidated text and annexes — verify on **EUR-Lex** under the official Regulation (EU) 2024/1689.
- EDPB/European Data Protection Supervisor guidance where AI processing involves personal data.
