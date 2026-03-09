# Epic 63: Auto Expert Generator

**Status:** In Progress
**Priority:** P3
**LOE:** ~2-3 weeks
**Dependencies:** Epic 43-45 (Business Expert Foundation/Consultation/Lifecycle), Epic 4 (Project Context)

---

## Problem Statement

TappsMCP ships 17 built-in technical experts covering broad domains (security, testing, performance, etc.), and Epics 43-45 added business expert support via manual YAML configuration. However, users must manually identify which custom experts their project needs and write `experts.yaml` entries by hand. This creates friction in the onboarding flow — most users never create business experts because they don't know what gaps exist.

The project profiler (`project/profiler.py`) already detects tech stacks, frameworks, domains, and project types. The AST parser extracts imports, classes, decorators, and patterns. Together, these can automatically identify project-specific expertise gaps and generate expert configurations with starter knowledge.

## Solution

Add an `auto_generate` action to `tapps_manage_experts` that:

1. **Analyzes** the codebase via the existing project profiler and AST parser
2. **Identifies gaps** between detected domains/frameworks and existing experts (builtin + business)
3. **Generates** business expert YAML entries for uncovered domains
4. **Scaffolds** knowledge directories with starter content derived from detected patterns
5. **Optionally enriches** starter knowledge via Context7/llms.txt doc lookups

## Architecture

### Module: `experts/auto_generator.py` (new, in tapps-core)

```
ProjectProfile + TechStack + ExpertRegistry
         ↓
   Gap Analysis (what domains lack expert coverage?)
         ↓
   Expert Suggestion (generate ExpertConfig entries)
         ↓
   Knowledge Scaffolding (create starter .md files)
         ↓
   Optional: Doc Enrichment (Context7/llms.txt for framework best practices)
```

### Integration Points

- **Input:** `ProjectProfile` from `project/profiler.py` (tech stack, frameworks, domains, project type)
- **Gap detection:** Compare detected domains against `ExpertRegistry.get_all_experts()` (builtin + registered business)
- **Output:** List of `BusinessExpertEntry` configs + scaffolded knowledge dirs
- **MCP tool:** New `auto_generate` action in `tapps_manage_experts`
- **Init integration:** Optional auto-generation during `tapps_init` when no `experts.yaml` exists

---

## Stories

### Story 63.1: Gap Analysis Engine

**File:** `packages/tapps-core/src/tapps_core/experts/auto_generator.py`

Implement `ExpertGapAnalyzer` that:
- Takes a `ProjectProfile` and current `ExpertRegistry`
- Maps detected frameworks/libraries to expert domains using pattern rules
- Identifies domains with no expert coverage (neither builtin nor business)
- Produces `ExpertSuggestion` objects with: domain, name, keywords, rationale, confidence

**Pattern rules** (framework → domain mapping):
- FastAPI/Flask/Django/Express → `api-design-integration` (builtin, skip)
- SQLAlchemy/Prisma/TypeORM → `database-data-management` (builtin, skip)
- Celery/RQ/Dramatiq → `task-queue` (no builtin → suggest)
- Stripe/PayPal SDK → `payments` (no builtin → suggest)
- Auth0/Keycloak/JWT libs → `authentication` (no builtin → suggest)
- GraphQL (Strawberry/Ariadne) → `graphql-api` (no builtin → suggest)
- gRPC → `grpc-services` (no builtin → suggest)
- Kafka/RabbitMQ/NATS → `message-broker` (no builtin → suggest)
- Elasticsearch/Meilisearch → `search-engine` (no builtin → suggest)
- S3/MinIO/GCS → `object-storage` (no builtin → suggest)

Also detect structural patterns:
- Heavy `async/await` usage → suggest `async-patterns` expert if no coverage
- Multiple microservice dirs → suggest `microservice-architecture` expert
- ML model files (.h5, .pt, .onnx) → `ml-ops` expert

**Acceptance Criteria:**
- [ ] Gap analysis identifies uncovered domains from profile
- [ ] Builtin expert domains are excluded from suggestions
- [ ] Already-registered business experts are excluded
- [ ] Each suggestion includes rationale and confidence score
- [ ] At least 15 framework→domain mapping rules
- [ ] Structural pattern detection (async, microservice, ML)
- [ ] Unit tests: 20+

### Story 63.2: Expert Configuration Generator

**File:** `packages/tapps-core/src/tapps_core/experts/auto_generator.py`

Implement `generate_expert_configs()` that:
- Takes `ExpertSuggestion` list from gap analysis
- Generates valid `BusinessExpertEntry` objects
- Auto-generates expert_id: `expert-{domain-slug}`
- Auto-generates keywords from detected libraries + domain terms
- Respects the 20-expert limit from `BusinessExpertsConfig`
- Ranks suggestions by confidence, takes top N

**Acceptance Criteria:**
- [ ] Generated configs pass `BusinessExpertsConfig` validation
- [ ] Keywords include detected library names + domain synonyms
- [ ] expert_id follows `expert-{slug}` convention
- [ ] Respects 20-expert max limit
- [ ] Unit tests: 10+

### Story 63.3: Knowledge Scaffolding with Enrichment

**File:** `packages/tapps-core/src/tapps_core/experts/auto_generator.py`

Implement `scaffold_expert_knowledge()` that:
- Creates knowledge directory at `.tapps-mcp/knowledge/{domain}/`
- Generates `overview.md` with domain-specific starter content
- Generates `best-practices.md` with framework-specific guidance derived from detected patterns
- Generates `common-patterns.md` listing detected code patterns (decorators, base classes, etc.)
- Content is deterministic (no LLM calls) — uses templates with detected framework/library names

**Template structure for overview.md:**
```markdown
---
title: {Domain Name} Overview
tags: [{domain}, {framework1}, {framework2}]
updated: {date}
---

# {Domain Name}

## Technologies Detected
- {framework1}: {description}
- {library1}: {description}

## Key Concepts
{domain-specific bullet points from template}

## Project Context
This expert was auto-generated based on detected usage of {frameworks} in this project.
```

**Acceptance Criteria:**
- [ ] Knowledge dirs created with README.md + overview.md + best-practices.md
- [ ] Content references actual detected frameworks/libraries
- [ ] Templates cover all supported domain suggestions
- [ ] Files pass RAG safety checks
- [ ] Idempotent (doesn't overwrite existing files)
- [ ] Unit tests: 15+

### Story 63.4: MCP Tool Integration

**File:** `packages/tapps-mcp/src/tapps_mcp/server_expert_tools.py`

Add `auto_generate` action to `tapps_manage_experts`:

```python
tapps_manage_experts(action="auto_generate", dry_run=True)
```

Parameters:
- `dry_run: bool = True` — preview suggestions without writing files
- `max_experts: int = 5` — maximum experts to generate
- `include_knowledge: bool = True` — scaffold knowledge directories

Response includes:
- `suggestions`: list of domain suggestions with rationale
- `generated`: list of expert configs written (empty if dry_run)
- `scaffolded`: list of knowledge directories created
- `skipped_builtin`: domains already covered by builtin experts
- `skipped_existing`: domains already in business experts

**Acceptance Criteria:**
- [ ] `auto_generate` action works in dry_run and live modes
- [ ] Structured response with suggestions and rationale
- [ ] Writes valid experts.yaml (merges with existing)
- [ ] Scaffolds knowledge directories
- [ ] Integration tests: 10+

### Story 63.5: Init Integration

**File:** `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`

During `tapps_init`, after project profiling:
- If no `experts.yaml` exists and profile detects uncovered domains
- Suggest auto-generation with a note in the init result
- If elicitation is available, ask user whether to auto-generate
- Record auto-generated experts in init result for transparency

**Acceptance Criteria:**
- [ ] Init detects when auto-generation would be beneficial
- [ ] Suggestion included in init result
- [ ] Elicitation question when supported
- [ ] Tests: 5+

---

## Non-Goals

- LLM-powered knowledge generation (all content is template-based and deterministic)
- Automatic expert removal (only adds, never removes)
- Overriding builtin experts
- Fetching external documentation at generation time (deferred to consultation)

## Testing Strategy

- Unit tests for gap analysis, config generation, knowledge scaffolding
- Integration tests for MCP tool action
- Fixture-based project profiles for various archetypes (API service, ML project, microservice)
- Validate generated configs pass Pydantic validation
- Verify idempotency (running twice doesn't duplicate)

## Estimated Test Count: 60+
