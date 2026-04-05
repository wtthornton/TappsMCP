"""Auto-generate business expert suggestions from codebase analysis.

Analyzes a project's tech stack, frameworks, and code patterns to identify
domains not covered by built-in or existing business experts, then generates
expert configurations and scaffolds knowledge directories.

Epic 63 — all content is deterministic (no LLM calls).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from tapps_core.experts.business_config import (
    BusinessExpertEntry,
    BusinessExpertsConfig,
)
from tapps_core.experts.business_knowledge import scaffold_knowledge_directory
from tapps_core.experts.models import ExpertConfig
from tapps_core.experts.registry import ExpertRegistry

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Framework-to-domain mapping rules
# ---------------------------------------------------------------------------

# Maps detected framework/library names to suggested expert domains.
# Domains already covered by builtin experts are marked with _BUILTIN_DOMAIN.
_BUILTIN_DOMAIN = "__builtin__"

_FRAMEWORK_DOMAIN_MAP: dict[str, str] = {
    # Task queues / background jobs
    "celery": "task-queue",
    "rq": "task-queue",
    "dramatiq": "task-queue",
    "huey": "task-queue",
    "arq": "task-queue",
    # Payments
    "stripe": "payments",
    "paypal": "payments",
    "braintree": "payments",
    "square": "payments",
    # Authentication
    "authlib": "authentication",
    "python-jose": "authentication",
    "pyjwt": "authentication",
    "passlib": "authentication",
    "python-social-auth": "authentication",
    "auth0": "authentication",
    "keycloak": "authentication",
    # GraphQL
    "strawberry": "graphql-api",
    "ariadne": "graphql-api",
    "graphene": "graphql-api",
    "sgqlc": "graphql-api",
    # gRPC
    "grpcio": "grpc-services",
    "grpc": "grpc-services",
    "protobuf": "grpc-services",
    "betterproto": "grpc-services",
    # Message brokers
    "kafka": "message-broker",
    "confluent-kafka": "message-broker",
    "aiokafka": "message-broker",
    "pika": "message-broker",
    "aio-pika": "message-broker",
    "nats-py": "message-broker",
    "kombu": "message-broker",
    # Search
    "elasticsearch": "search-engine",
    "opensearch-py": "search-engine",
    "meilisearch": "search-engine",
    "typesense": "search-engine",
    "whoosh": "search-engine",
    # Object storage
    "minio": "object-storage",
    "google-cloud-storage": "object-storage",
    "azure-storage-blob": "object-storage",
    # Caching
    "redis": "caching",
    "memcached": "caching",
    "aiocache": "caching",
    "cachetools": "caching",
    # Email
    "sendgrid": "email-notifications",
    "mailgun": "email-notifications",
    "aiosmtplib": "email-notifications",
    # WebSockets / real-time
    "websockets": "real-time",
    "socketio": "real-time",
    "channels": "real-time",
    "sse-starlette": "real-time",
    # Scheduling / cron
    "apscheduler": "scheduling",
    "schedule": "scheduling",
    "croniter": "scheduling",
    # Feature flags
    "flagsmith": "feature-flags",
    "launchdarkly": "feature-flags",
    "unleash": "feature-flags",
    # Builtin-covered domains (detected but skipped)
    "fastapi": _BUILTIN_DOMAIN,
    "flask": _BUILTIN_DOMAIN,
    "django": _BUILTIN_DOMAIN,
    "express": _BUILTIN_DOMAIN,
    "sqlalchemy": _BUILTIN_DOMAIN,
    "prisma": _BUILTIN_DOMAIN,
    "pytest": _BUILTIN_DOMAIN,
    "boto3": _BUILTIN_DOMAIN,
    "kubernetes": _BUILTIN_DOMAIN,
    "tensorflow": _BUILTIN_DOMAIN,
    "pytorch": _BUILTIN_DOMAIN,
    "torch": _BUILTIN_DOMAIN,
    "scikit-learn": _BUILTIN_DOMAIN,
    "prometheus-client": _BUILTIN_DOMAIN,
    "opentelemetry": _BUILTIN_DOMAIN,
}

# Structural pattern detections
_STRUCTURAL_PATTERNS: dict[str, dict[str, Any]] = {
    "ml-ops": {
        "file_extensions": [".h5", ".pt", ".onnx", ".pkl", ".joblib", ".safetensors"],
        "dir_patterns": ["models/", "model/", "checkpoints/", "weights/"],
        "description": "ML model lifecycle, training pipelines, model serving, and MLOps.",
    },
}

# ---------------------------------------------------------------------------
# Domain metadata for knowledge scaffolding
# ---------------------------------------------------------------------------

_DOMAIN_METADATA: dict[str, dict[str, str]] = {
    "task-queue": {
        "expert_name": "Task Queue Expert",
        "description": "Background job processing, task scheduling, retry strategies, and queue management.",
        "key_concepts": (
            "- Task serialization and deserialization\n"
            "- Retry policies and dead-letter queues\n"
            "- Worker scaling and concurrency\n"
            "- Task priority and rate limiting\n"
            "- Monitoring and observability for async tasks"
        ),
    },
    "payments": {
        "expert_name": "Payments Expert",
        "description": "Payment processing, billing integration, subscription management, and PCI compliance.",
        "key_concepts": (
            "- Payment gateway integration patterns\n"
            "- Idempotency in payment processing\n"
            "- Webhook handling and event verification\n"
            "- Subscription lifecycle management\n"
            "- PCI DSS compliance requirements"
        ),
    },
    "authentication": {
        "expert_name": "Authentication Expert",
        "description": "Identity management, OAuth2/OIDC flows, JWT handling, and session security.",
        "key_concepts": (
            "- OAuth2 authorization code and PKCE flows\n"
            "- JWT token validation and rotation\n"
            "- Session management and CSRF protection\n"
            "- Multi-factor authentication patterns\n"
            "- Role-based and attribute-based access control"
        ),
    },
    "graphql-api": {
        "expert_name": "GraphQL API Expert",
        "description": "GraphQL schema design, resolvers, subscriptions, and API performance.",
        "key_concepts": (
            "- Schema-first vs code-first design\n"
            "- N+1 query problem and DataLoader pattern\n"
            "- Subscription and real-time data patterns\n"
            "- Pagination strategies (cursor, offset)\n"
            "- Schema evolution and versioning"
        ),
    },
    "grpc-services": {
        "expert_name": "gRPC Services Expert",
        "description": "Protocol Buffers, gRPC service design, streaming, and inter-service communication.",
        "key_concepts": (
            "- Protocol Buffer schema design and evolution\n"
            "- Unary, server-streaming, client-streaming, and bidirectional RPCs\n"
            "- gRPC interceptors and middleware\n"
            "- Load balancing and service discovery\n"
            "- Error handling with gRPC status codes"
        ),
    },
    "message-broker": {
        "expert_name": "Message Broker Expert",
        "description": "Event-driven architecture, message queues, pub/sub patterns, and data streaming.",
        "key_concepts": (
            "- Publish/subscribe vs point-to-point messaging\n"
            "- Message ordering and delivery guarantees\n"
            "- Consumer group management and offset handling\n"
            "- Dead-letter queues and error handling\n"
            "- Schema registry and message evolution"
        ),
    },
    "search-engine": {
        "expert_name": "Search Engine Expert",
        "description": "Full-text search, indexing strategies, relevance tuning, and search infrastructure.",
        "key_concepts": (
            "- Index design and mapping configuration\n"
            "- Query DSL and relevance scoring\n"
            "- Analyzers, tokenizers, and filters\n"
            "- Faceted search and aggregations\n"
            "- Index lifecycle management and reindexing"
        ),
    },
    "object-storage": {
        "expert_name": "Object Storage Expert",
        "description": "Blob storage, presigned URLs, multipart uploads, and storage lifecycle.",
        "key_concepts": (
            "- Presigned URL generation and expiry\n"
            "- Multipart upload for large files\n"
            "- Storage lifecycle policies and tiering\n"
            "- Cross-region replication\n"
            "- Access control and bucket policies"
        ),
    },
    "caching": {
        "expert_name": "Caching Expert",
        "description": "Cache strategies, invalidation patterns, distributed caching, and TTL management.",
        "key_concepts": (
            "- Cache-aside, write-through, and write-behind patterns\n"
            "- Cache invalidation strategies\n"
            "- Distributed cache consistency\n"
            "- TTL management and eviction policies\n"
            "- Cache stampede prevention"
        ),
    },
    "email-notifications": {
        "expert_name": "Email & Notifications Expert",
        "description": "Transactional email, notification systems, templates, and deliverability.",
        "key_concepts": (
            "- Transactional vs marketing email patterns\n"
            "- Email template engines and rendering\n"
            "- Deliverability, SPF, DKIM, and DMARC\n"
            "- Notification routing and preferences\n"
            "- Rate limiting and throttling"
        ),
    },
    "real-time": {
        "expert_name": "Real-Time Communication Expert",
        "description": "WebSockets, server-sent events, real-time data sync, and connection management.",
        "key_concepts": (
            "- WebSocket connection lifecycle management\n"
            "- Server-sent events for one-way streaming\n"
            "- Heartbeat and reconnection strategies\n"
            "- Room/channel-based messaging\n"
            "- Scaling WebSocket connections"
        ),
    },
    "scheduling": {
        "expert_name": "Scheduling Expert",
        "description": "Cron jobs, periodic tasks, distributed scheduling, and time-based workflows.",
        "key_concepts": (
            "- Cron expression patterns and scheduling\n"
            "- Distributed locking for scheduled tasks\n"
            "- Missed execution handling and catch-up\n"
            "- Time zone handling in scheduling\n"
            "- Job state persistence and recovery"
        ),
    },
    "feature-flags": {
        "expert_name": "Feature Flags Expert",
        "description": "Feature toggles, progressive rollouts, A/B testing, and release management.",
        "key_concepts": (
            "- Feature flag lifecycle management\n"
            "- Progressive rollout and canary strategies\n"
            "- A/B testing and experiment design\n"
            "- Flag evaluation performance\n"
            "- Technical debt from stale flags"
        ),
    },
    "ml-ops": {
        "expert_name": "MLOps Expert",
        "description": "ML model lifecycle, training pipelines, model serving, and experiment tracking.",
        "key_concepts": (
            "- Model versioning and registry\n"
            "- Training pipeline orchestration\n"
            "- Model serving and inference optimization\n"
            "- Experiment tracking and reproducibility\n"
            "- Data drift detection and monitoring"
        ),
    },
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ExpertSuggestion:
    """A suggested expert generated from codebase analysis."""

    domain: str
    expert_name: str
    description: str
    keywords: list[str] = field(default_factory=list)
    confidence: float = 0.5
    rationale: str = ""
    detected_libraries: list[str] = field(default_factory=list)


@dataclass
class AutoGenerateResult:
    """Result of auto-generating expert configurations."""

    suggestions: list[ExpertSuggestion] = field(default_factory=list)
    generated: list[dict[str, Any]] = field(default_factory=list)
    scaffolded: list[str] = field(default_factory=list)
    skipped_builtin: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------


def analyze_expert_gaps(
    libraries: list[str],
    frameworks: list[str],
    domains: list[str],
    project_root: Path | None = None,
) -> list[ExpertSuggestion]:
    """Identify domains lacking expert coverage from detected tech stack.

    Args:
        libraries: Detected library names (from profiler).
        frameworks: Detected framework names (from profiler).
        domains: Detected domain tags (from profiler).
        project_root: Project root for structural pattern detection.

    Returns:
        List of expert suggestions for uncovered domains.
    """
    # Collect all detected items for matching
    all_detected = {lib.lower().replace("_", "-") for lib in libraries + frameworks}

    # Get all covered domains (builtin + business)
    builtin_domains = ExpertRegistry.TECHNICAL_DOMAINS
    business_domains = ExpertRegistry.get_business_domains()
    covered_domains = builtin_domains | business_domains

    # Map detected libraries to suggested domains
    domain_libs: dict[str, list[str]] = {}
    skipped_builtin: set[str] = set()

    for lib in all_detected:
        target_domain = _FRAMEWORK_DOMAIN_MAP.get(lib)
        if target_domain is None:
            continue
        if target_domain == _BUILTIN_DOMAIN:
            skipped_builtin.add(lib)
            continue
        if target_domain in covered_domains:
            continue
        domain_libs.setdefault(target_domain, []).append(lib)

    # Check structural patterns
    if project_root is not None:
        for domain, patterns in _STRUCTURAL_PATTERNS.items():
            if domain in covered_domains:
                continue
            found = False
            for ext in patterns.get("file_extensions", []):
                if list(project_root.rglob(f"*{ext}"))[:1]:
                    found = True
                    break
            if not found:
                for dir_pat in patterns.get("dir_patterns", []):
                    if (project_root / dir_pat.rstrip("/")).is_dir():
                        found = True
                        break
            if found:
                domain_libs.setdefault(domain, []).append("structural-pattern")

    # Build suggestions
    suggestions: list[ExpertSuggestion] = []
    for domain, libs in sorted(domain_libs.items()):
        meta = _DOMAIN_METADATA.get(domain, {})
        expert_name = meta.get("expert_name", f"{domain.replace('-', ' ').title()} Expert")
        description = meta.get("description", f"Expert for {domain} domain.")

        # Build keywords from detected libs + domain terms
        keywords = list(dict.fromkeys(libs))  # dedupe, preserve order
        domain_words = domain.replace("-", " ").split()
        for word in domain_words:
            if word not in keywords:
                keywords.append(word)

        confidence = min(1.0, len(libs) * 0.3 + 0.2)
        rationale = f"Detected {', '.join(libs)} in project dependencies"

        suggestions.append(
            ExpertSuggestion(
                domain=domain,
                expert_name=expert_name,
                description=description,
                keywords=keywords,
                confidence=confidence,
                rationale=rationale,
                detected_libraries=libs,
            )
        )

    # Sort by confidence descending
    suggestions.sort(key=lambda s: s.confidence, reverse=True)

    logger.info(
        "expert_gap_analysis.complete",
        suggestions=len(suggestions),
        skipped_builtin=len(skipped_builtin),
    )

    return suggestions


# ---------------------------------------------------------------------------
# Config generation
# ---------------------------------------------------------------------------


def generate_expert_configs(
    suggestions: list[ExpertSuggestion],
    max_experts: int = 5,
) -> list[BusinessExpertEntry]:
    """Generate BusinessExpertEntry configs from suggestions.

    Args:
        suggestions: Expert suggestions from gap analysis.
        max_experts: Maximum number of experts to generate.

    Returns:
        List of valid BusinessExpertEntry configs.
    """
    # Check how many business experts already exist to respect the 20 limit
    existing_count = len(ExpertRegistry.get_business_experts())
    available_slots = max(0, BusinessExpertsConfig._MAX_EXPERTS - existing_count)
    limit = min(max_experts, available_slots)

    if limit <= 0:
        logger.info("expert_config_gen.at_limit", existing=existing_count)
        return []

    configs: list[BusinessExpertEntry] = []
    for suggestion in suggestions[:limit]:
        expert_id = f"expert-{suggestion.domain}"
        configs.append(
            BusinessExpertEntry(
                expert_id=expert_id,
                expert_name=suggestion.expert_name,
                primary_domain=suggestion.domain,
                description=suggestion.description,
                keywords=suggestion.keywords[:50],  # respect max keywords
                rag_enabled=True,
            )
        )

    logger.info(
        "expert_config_gen.complete",
        generated=len(configs),
        limit=limit,
    )

    return configs


# ---------------------------------------------------------------------------
# Knowledge scaffolding with enriched content
# ---------------------------------------------------------------------------


def scaffold_expert_with_knowledge(
    project_root: Path,
    entry: BusinessExpertEntry,
    detected_libraries: list[str] | None = None,
) -> Path:
    """Scaffold knowledge directory with enriched starter content.

    Creates the knowledge directory using the standard scaffold, then adds
    a best-practices.md with domain-specific content if available.

    Args:
        project_root: Project root directory.
        entry: Business expert entry to scaffold.
        detected_libraries: Libraries that triggered this expert suggestion.

    Returns:
        Path to the knowledge directory.
    """
    config = ExpertConfig(
        expert_id=entry.expert_id,
        expert_name=entry.expert_name,
        primary_domain=entry.primary_domain,
        description=entry.description,
        keywords=entry.keywords,
        rag_enabled=entry.rag_enabled,
        knowledge_dir=entry.knowledge_dir,
        is_builtin=False,
    )

    # Use the standard scaffolding (creates README.md + overview.md)
    knowledge_path = scaffold_knowledge_directory(project_root, config)

    # Add enriched best-practices.md with domain-specific content
    best_practices_path = knowledge_path / "best-practices.md"
    if not best_practices_path.exists():
        content = _generate_best_practices(
            entry.expert_name,
            entry.primary_domain,
            entry.description,
            detected_libraries or [],
        )
        best_practices_path.write_text(content, encoding="utf-8")
        logger.info(
            "knowledge_best_practices_created",
            domain=entry.primary_domain,
            path=str(best_practices_path),
        )

    return knowledge_path


def _generate_best_practices(
    expert_name: str,
    domain: str,
    description: str,
    libraries: list[str],
) -> str:
    """Generate best-practices.md with domain-specific content."""
    meta = _DOMAIN_METADATA.get(domain, {})
    key_concepts = meta.get("key_concepts", "- Follow established patterns and conventions")
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")

    libs_section = ""
    if libraries:
        clean_libs = [lib for lib in libraries if lib != "structural-pattern"]
        if clean_libs:
            libs_section = (
                "\n## Detected Technologies\n\n"
                + "\n".join(f"- **{lib}**" for lib in clean_libs)
                + "\n"
            )

    return f"""---
title: {expert_name} - Best Practices
tags: [{domain}, best-practices]
updated: {today}
---

# {expert_name} - Best Practices

{description}

## Key Concepts

{key_concepts}
{libs_section}
## General Guidelines

1. **Start simple** - implement the basic pattern first, optimize later.
2. **Handle failures gracefully** - design for partial failures and retries.
3. **Monitor and observe** - add logging and metrics from the start.
4. **Document decisions** - record why specific patterns were chosen.
5. **Test edge cases** - focus on failure modes, not just happy paths.

## Project Context

This knowledge base was auto-generated for the **{expert_name}** based on
detected usage of {domain} technologies in this project. Add project-specific
knowledge to improve consultation accuracy.
"""


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def auto_generate_experts(
    project_root: Path,
    libraries: list[str],
    frameworks: list[str],
    domains: list[str],
    max_experts: int = 5,
    dry_run: bool = True,
    include_knowledge: bool = True,
) -> AutoGenerateResult:
    """Orchestrate expert auto-generation from codebase analysis.

    Args:
        project_root: Project root directory.
        libraries: Detected library names.
        frameworks: Detected framework names.
        domains: Detected domain tags.
        max_experts: Maximum experts to generate.
        dry_run: If True, only return suggestions without writing files.
        include_knowledge: If True, scaffold knowledge directories.

    Returns:
        AutoGenerateResult with suggestions, generated configs, and scaffolded paths.
    """
    result = AutoGenerateResult()

    # Step 1: Gap analysis
    suggestions = analyze_expert_gaps(
        libraries=libraries,
        frameworks=frameworks,
        domains=domains,
        project_root=project_root,
    )
    result.suggestions = suggestions

    # Track skipped domains
    builtin_domains = ExpertRegistry.TECHNICAL_DOMAINS
    business_domains = ExpertRegistry.get_business_domains()
    result.skipped_builtin = sorted(builtin_domains)
    result.skipped_existing = sorted(business_domains)

    if not suggestions:
        logger.info("auto_generate.no_suggestions")
        return result

    if dry_run:
        logger.info("auto_generate.dry_run", suggestions=len(suggestions))
        return result

    # Step 2: Generate configs
    configs = generate_expert_configs(suggestions, max_experts=max_experts)
    if not configs:
        return result

    # Step 3: Write to experts.yaml (merge with existing)
    _merge_into_experts_yaml(project_root, configs)

    # Build suggestion lookup for library info
    suggestion_map = {s.domain: s for s in suggestions}

    for config in configs:
        result.generated.append({
            "expert_id": config.expert_id,
            "expert_name": config.expert_name,
            "primary_domain": config.primary_domain,
            "description": config.description,
            "keywords": config.keywords,
        })

        # Step 4: Scaffold knowledge directories
        if include_knowledge:
            suggestion = suggestion_map.get(config.primary_domain)
            detected_libs = suggestion.detected_libraries if suggestion else None
            knowledge_path = scaffold_expert_with_knowledge(
                project_root, config, detected_libs,
            )
            result.scaffolded.append(str(knowledge_path))

    logger.info(
        "auto_generate.complete",
        generated=len(result.generated),
        scaffolded=len(result.scaffolded),
    )

    return result


def _merge_into_experts_yaml(
    project_root: Path,
    new_entries: list[BusinessExpertEntry],
) -> None:
    """Merge new expert entries into experts.yaml, preserving existing entries."""
    import yaml

    yaml_path = project_root / ".tapps-mcp" / "experts.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    existing_data: dict[str, Any] = {"experts": []}
    if yaml_path.exists():
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            existing_data = raw
            if "experts" not in existing_data:
                existing_data["experts"] = []

    existing_ids = {
        e["expert_id"]
        for e in existing_data["experts"]
        if isinstance(e, dict) and "expert_id" in e
    }

    for entry in new_entries:
        if entry.expert_id in existing_ids:
            continue
        existing_data["experts"].append(
            entry.model_dump(exclude_defaults=True),
        )

    yaml_path.write_text(
        yaml.safe_dump(existing_data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    logger.info(
        "experts_yaml.merged",
        new_count=len(new_entries),
        total_count=len(existing_data["experts"]),
        path=str(yaml_path),
    )
