# Built-in Expert Knowledge Bases

This directory contains knowledge bases for built-in framework experts. These knowledge bases provide technical domain expertise that ships with TappsMCP.

**Last reviewed**: 2026-02. Keep content current with latest practices; remove or replace deprecated material.

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
├── user-experience/               # UX Expert (8 files)
│   ├── ux-principles.md
│   ├── user-research.md
│   ├── user-journeys.md
│   ├── information-architecture.md
│   ├── interaction-design.md
│   ├── prototyping.md
│   ├── usability-heuristics.md
│   └── usability-testing.md
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

## Knowledge Base Best Practices

- **Be specific**: Include concrete examples and patterns
- **Be current**: Keep knowledge up to date with latest practices (review annually; 2026 baseline)
- **Be comprehensive**: Cover common scenarios and edge cases
- **Be structured**: Use headers and sections for easy navigation
- **Be actionable**: Provide clear guidance and checklists

## References

- [Knowledge Base Guide](../../../docs/KNOWLEDGE_BASE_GUIDE.md)
- [Expert Configuration Guide](../../../docs/EXPERT_CONFIG_GUIDE.md)

