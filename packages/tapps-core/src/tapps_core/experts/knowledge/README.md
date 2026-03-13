# Built-in Expert Knowledge Bases

This directory contains knowledge bases for built-in framework experts. These knowledge bases provide technical domain expertise that ships with TappsMCP.

**Last reviewed**: 2026-03. Keep content current with latest practices; remove or replace deprecated material.

## Structure

Each expert has its own subdirectory containing markdown knowledge files:

```
knowledge/
├── security/                      # Security Expert (5 files)
│   ├── modern-security-patterns.md
│   ├── owasp-top10.md
│   ├── secure-coding-practices.md
│   ├── threat-modeling.md
│   └── vulnerability-patterns.md
├── performance/                   # Performance Expert (8 files)
│   ├── optimization-patterns.md
│   ├── caching.md
│   ├── scalability.md
│   ├── api-performance.md
│   ├── database-performance.md
│   ├── resource-management.md
│   ├── profiling.md
│   └── anti-patterns.md
├── testing/                       # Testing Expert (11 files)
│   ├── best-practices.md
│   ├── test-strategies.md
│   ├── test-design-patterns.md
│   ├── test-automation.md
│   ├── mocking.md
│   ├── test-data.md
│   ├── coverage-analysis.md
│   ├── test-maintenance.md
│   ├── mcp-testing-patterns.md
│   ├── modern-testing-patterns.md
│   └── test-configuration-and-urls.md
├── data-privacy-compliance/       # Data Privacy Expert (10 files)
│   ├── gdpr.md
│   ├── ccpa.md
│   ├── hipaa.md
│   ├── privacy-by-design.md
│   ├── consent-management.md
│   ├── data-minimization.md
│   ├── data-retention.md
│   ├── data-subject-rights.md
│   ├── anonymization.md
│   └── encryption-privacy.md
├── accessibility/                 # Accessibility Expert (9 files)
│   ├── wcag-2.1.md
│   ├── wcag-2.2.md
│   ├── semantic-html.md
│   ├── aria-patterns.md
│   ├── keyboard-navigation.md
│   ├── screen-readers.md
│   ├── color-contrast.md
│   ├── accessible-forms.md
│   └── testing-accessibility.md
├── user-experience/               # UX Design Expert (19 files)
│   ├── ux-principles.md
│   ├── user-research.md
│   ├── user-journeys.md
│   ├── information-architecture.md
│   ├── interaction-design.md
│   ├── prototyping.md
│   ├── usability-heuristics.md
│   ├── usability-testing.md
│   ├── design-systems.md
│   ├── modern-css.md
│   ├── accessibility-wcag22.md
│   ├── performance-ux.md
│   ├── ai-ux-patterns.md
│   ├── motion-animation.md
│   ├── dark-mode-theming.md
│   ├── form-patterns.md
│   ├── responsive-mobile.md
│   ├── frontend-architecture.md
│   └── industry-landscape.md
├── observability-monitoring/      # Observability Expert (8 files)
│   ├── distributed-tracing.md
│   ├── metrics-and-monitoring.md
│   ├── logging-strategies.md
│   ├── apm-tools.md
│   ├── slo-sli-sla.md
│   ├── alerting-patterns.md
│   ├── observability-best-practices.md
│   └── open-telemetry.md
├── api-design-integration/        # API Design Expert (14 files)
│   ├── restful-api-design.md
│   ├── graphql-patterns.md
│   ├── grpc-best-practices.md
│   ├── api-versioning.md
│   ├── rate-limiting.md
│   ├── api-gateway-patterns.md
│   ├── api-security-patterns.md
│   ├── contract-testing.md
│   ├── fastapi-patterns.md
│   ├── fastapi-testing.md
│   ├── websocket-patterns.md
│   ├── mqtt-patterns.md
│   ├── async-protocol-patterns.md
│   └── external-api-integration.md
├── cloud-infrastructure/          # Cloud Infrastructure Expert (11 files)
│   ├── cloud-native-patterns.md
│   ├── containerization.md
│   ├── container-health-checks.md
│   ├── kubernetes-patterns.md
│   ├── kubernetes-security-patterns.md
│   ├── infrastructure-as-code.md
│   ├── serverless-architecture.md
│   ├── multi-cloud-strategies.md
│   ├── cost-optimization.md
│   ├── disaster-recovery.md
│   └── dockerfile-patterns.md
├── database-data-management/      # Database Expert (12 files)
│   ├── database-design.md
│   ├── sql-optimization.md
│   ├── nosql-patterns.md
│   ├── data-modeling.md
│   ├── migration-strategies.md
│   ├── scalability-patterns.md
│   ├── backup-and-recovery.md
│   ├── acid-vs-cap.md
│   ├── influxdb-patterns.md
│   ├── influxdb-connection-patterns.md
│   ├── flux-query-optimization.md
│   └── time-series-modeling.md
├── software-architecture/         # Software Architecture Expert (4 files)
│   ├── mcp-server-architecture.md
│   ├── microservices-patterns.md
│   ├── service-communication.md
│   └── docker-compose-patterns.md
├── code-quality-analysis/         # Code Quality & Analysis Expert (5 files)
│   ├── static-analysis-patterns.md
│   ├── code-metrics.md
│   ├── complexity-analysis.md
│   ├── technical-debt-patterns.md
│   └── quality-gates.md
├── development-workflow/          # Development Workflow Expert (6 files)
│   ├── ci-cd-patterns.md
│   ├── git-workflows.md
│   ├── build-strategies.md
│   ├── deployment-patterns.md
│   ├── automation-best-practices.md
│   └── github-actions-advanced.md
├── documentation-knowledge-management/ # Documentation & Knowledge Management Expert (4 files)
│   ├── documentation-standards.md
│   ├── api-documentation-patterns.md
│   ├── knowledge-management.md
│   └── technical-writing-guide.md
├── github/                        # GitHub Platform Expert (10 files)
│   ├── github-actions-ci-patterns.md
│   ├── github-actions-best-practices.md
│   ├── github-agentic-workflows.md
│   ├── github-copilot-agent-setup.md
│   ├── github-issues-and-forms.md
│   ├── github-mcp-integration.md
│   ├── github-projects-api.md
│   ├── github-pull-requests.md
│   ├── github-rulesets-and-governance.md
│   └── github-security-features.md
├── agent-learning/                # Agent Learning Best Practices (4 files)
│   ├── adaptive-learning-patterns.md
│   ├── best-practices.md
│   ├── pattern-extraction.md
│   └── prompt-optimization.md
└── ai-frameworks/                 # AI Frameworks Expert (6 files)
    ├── agent-orchestration-patterns.md
    ├── llm-integration-patterns.md
    ├── mcp-patterns.md
    ├── model-optimization.md
    ├── openvino-patterns.md
    └── rag-patterns.md
```

## Knowledge Base Format

Knowledge files are written in Markdown format. The RAG system uses:

- **Headers** (`#`, `##`, `###`) to structure knowledge and prioritize search results
- **Code blocks** for examples
- **Lists** for checklists and guidelines
- **Plain text** for explanations

## Usage

Built-in experts automatically load knowledge from this directory when:
1. The expert is activated
2. RAG is enabled for the expert
3. The expert's `primary_domain` matches a subdirectory name

## Adding Knowledge

To add knowledge to a built-in expert:

1. Create or edit markdown files in the expert's subdirectory
2. Use clear headers and structure
3. Include code examples where relevant
4. Keep content focused and actionable
5. Update this README if adding new experts

## RAG Index Rebuild

When you edit knowledge files, the vector RAG index (used by `tapps_consult_expert`) is **not** automatically refreshed. To pick up changes:

1. Delete the domain index for the edited expert, e.g.:
   - `{project_root}/.tapps-mcp/rag_index/{domain_slug}/` (e.g. `security/`, `testing-strategies/`)
2. Or delete the entire `rag_index` folder to rebuild all domains:
   - `{project_root}/.tapps-mcp/rag_index/`

The next `tapps_consult_expert` call for that domain will rebuild the index from the current files. See [ARCHITECTURE_CACHE_AND_RAG.md](../../../../docs/ARCHITECTURE_CACHE_AND_RAG.md) for full details.

## Persona Guidelines (Expert Config)

- **Purpose:** Persona defines the expert's identity and default stance. It is prepended to consultation answers (italic) when set in `ExpertConfig`.
- **Format:** 1–3 sentences. Role + default stance. No markdown, no code in persona text.
- **Examples:**
  - **Security Expert:** "Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design."
  - **Testing Expert:** "Senior test architect focused on comprehensive test strategies and quality assurance. Default to recommending tests for critical paths; never approve untested behavior in production code."
  - **Accessibility Expert:** "Senior accessibility specialist focused on WCAG 2.2 AA compliance and inclusive design. Default to assuming diverse abilities and assistive technology usage; never approve inaccessible interfaces."
- **Reference:** See `ExpertRegistry.BUILTIN_EXPERTS` in `packages/tapps-core/src/tapps_core/experts/registry.py`. For agency-style personas, see [TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md](../../../../../../docs/reviews/TAPPS-EXPERTS-VS-AGENCY-PERSONAS-SUMMARY.md).

## Knowledge Base Best Practices

- **Be specific**: Include concrete examples and patterns
- **Be current**: Keep knowledge up to date with latest practices (review annually; 2026 baseline)
- **Be comprehensive**: Cover common scenarios and edge cases
- **Be structured**: Use headers and sections for easy navigation
- **Be actionable**: Provide clear guidance and checklists

## Knowledge Enrichment Patterns

Beyond core technical content (patterns, examples, anti-patterns), knowledge files can include enrichment sections that make expert consultation answers more actionable. Use these patterns when adding or updating knowledge files.

### Success metrics / Definition of done

Add a `## Success metrics` section with concrete, measurable thresholds that define "what good looks like" for the domain. Use bullet lists with specific numbers where possible.

**When to add:** Any domain where users ask "how do I know this is good enough?" -- testing (coverage targets), performance (latency budgets), security (zero critical findings), accessibility (WCAG level), code quality (complexity limits).

**Example files:** `testing/best-practices.md`, `performance/optimization-patterns.md`, `code-quality-analysis/quality-gates.md`

### Typical steps / Recommended process

Add a `## Typical steps` or `## Recommended process` section with a numbered list of 5-8 sequential steps that guide the user through a workflow. Each step should be one line with a brief explanation.

**When to add:** Any domain with a multi-step workflow -- security reviews, API design, database migrations, CI/CD setup, testing strategy planning.

**Example files:** `testing/test-strategies.md`, `security/threat-modeling.md`, `api-design-integration/restful-api-design.md`

### Deliverable templates (checklists, report outlines)

Add a `## Checklist` or `## Template` section with a markdown checkbox list (10-15 items) or a report outline that users can copy and adapt. Checklists work well for review processes; templates work well for deliverables.

**When to add:** Domains with review or audit processes -- security reviews, testing sign-off, accessibility audits, code quality gates.

**Example files:** `security/secure-coding-practices.md`, `testing/best-practices.md`, `accessibility/testing-accessibility.md`

### When-to-use guidance

Each expert domain already has a description in the registry. Optionally, the first knowledge file in a domain can include a brief "Use this expert when..." note to help RAG match ambiguous queries to the right domain.

## References

- [Knowledge Base Guide](../../../docs/KNOWLEDGE_BASE_GUIDE.md)
- [Expert Configuration Guide](../../../docs/EXPERT_CONFIG_GUIDE.md)

