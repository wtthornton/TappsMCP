"""Query expansion with synonym matching for improved domain detection.

Maps common variants, abbreviations, and related terms to their canonical
keyword forms used in ``DOMAIN_KEYWORDS``.  This improves recall when users
phrase questions differently from the keywords defined in the detector.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Synonym dictionary: variant -> canonical form
# ---------------------------------------------------------------------------
# Each key is a variant (abbreviation, informal term, alternative spelling)
# that maps to the canonical keyword found in DOMAIN_KEYWORDS.  Only lowercase.

SYNONYMS: dict[str, str] = {
    # Security
    "vuln": "vulnerability",
    "vulns": "vulnerability",
    "vulnerabilities": "vulnerability",
    "auth": "authentication",
    "authn": "authentication",
    "authz": "authorization",
    "passwd": "credential",
    "password": "credential",
    "inject": "sql injection",
    "sqli": "sql injection",
    "cross-site scripting": "xss",
    "cross site scripting": "xss",
    "pen test": "penetration",
    "pentest": "penetration",
    # Performance
    "perf": "performance",
    "slowness": "slow",
    "lag": "latency",
    "response time": "latency",
    "concurrent": "concurrency",
    "threading": "thread",
    "multiprocessing": "parallel",
    "mem": "memory",
    # Testing
    "unittest": "unit test",
    "unittests": "unit test",
    "spec": "test",
    "specs": "test",
    "e2e test": "e2e",
    "end-to-end": "e2e",
    "end to end": "e2e",
    "mocking": "mock",
    "faking": "stub",
    "test driven": "tdd",
    "behavior driven": "bdd",
    # Code quality
    "linter": "lint",
    "type checking": "type check",
    "typechecking": "type check",
    "tech debt": "technical debt",
    "code review": "code quality",
    "refactoring": "refactor",
    # Architecture
    "microservices": "microservice",
    "di": "dependency injection",
    "ddd": "domain driven",
    "event-driven": "event driven",
    "event sourcing": "event driven",
    # DevOps / Workflow
    "cicd": "ci",
    "ci/cd": "ci",
    "continuous integration": "ci",
    "continuous delivery": "cd",
    "continuous deployment": "cd",
    "deploying": "deployment",
    "branching": "branch",
    "merging": "merge",
    "pull request": "pr",
    # Cloud / Infrastructure
    "infra": "infrastructure",
    "iac": "infrastructure as code",
    "k8s": "kubernetes",
    "kube": "kubernetes",
    "containers": "container",
    "containerize": "container",
    "containerization": "containerization",
    "fargate": "serverless",
    "cloud function": "serverless",
    # Database
    "db": "database",
    "postgres": "postgres",
    "postgresql": "postgres",
    "mysql": "mysql",
    "mongo": "mongodb",
    "mariadb": "mysql",
    "sqlite": "database",
    "dynamo": "nosql",
    "dynamodb": "nosql",
    "cassandra": "nosql",
    # API
    "restful": "rest",
    "rest api": "rest",
    "gql": "graphql",
    "ws": "websocket",
    "websockets": "websocket",
    # Observability
    "logs": "logging",
    "traces": "tracing",
    "apm": "monitoring",
    "telemetry": "opentelemetry",
    "otel": "opentelemetry",
    # AI / ML
    "artificial intelligence": "ai",
    "deep learning": "machine learning",
    "dl": "machine learning",
    "nlp": "llm",
    "natural language": "llm",
    "chatbot": "agent",
    "chat bot": "agent",
    "retrieval augmented": "rag",
    "embeddings": "embedding",
    "finetuning": "fine-tune",
    "fine tuning": "fine-tune",
    # Docs
    "doc": "documentation",
    "documenting": "documentation",
    # Privacy
    "pii": "pii",
    "personal data": "pii",
    "anonymization": "anonymize",
    "pseudonymization": "pseudonymize",
    "data breach": "breach notification",
}


def expand_query(question: str) -> str:
    """Expand a question by appending canonical synonyms for matched variants.

    The original question text is preserved.  For each synonym variant found
    in the question (via word-boundary matching), the canonical form is
    appended once at the end.  This enriches the text for downstream keyword
    matching without altering the user's original phrasing.

    Args:
        question: The raw user question.

    Returns:
        The question with canonical synonyms appended (space-separated).
    """
    question_lower = question.lower()
    additions: list[str] = []

    for variant, canonical in SYNONYMS.items():
        pattern = r"\b" + re.escape(variant) + r"\b"
        if re.search(pattern, question_lower):
            # Only add the canonical form if it is not already in the question.
            canonical_pattern = r"\b" + re.escape(canonical) + r"\b"
            if not re.search(canonical_pattern, question_lower):
                if canonical not in additions:
                    additions.append(canonical)

    if not additions:
        return question

    return question + " " + " ".join(additions)


def expand_keywords(keywords: list[str]) -> list[str]:
    """Expand a list of keywords by adding canonical forms for any synonyms.

    Each keyword is checked against the synonym dictionary.  If it matches a
    variant, the canonical form is appended to the result (the original
    keyword is always preserved).

    Args:
        keywords: List of keyword strings.

    Returns:
        Expanded list with canonical forms appended (no duplicates).
    """
    seen: set[str] = set()
    result: list[str] = []

    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower not in seen:
            seen.add(kw_lower)
            result.append(kw)

        canonical = SYNONYMS.get(kw_lower)
        if canonical and canonical.lower() not in seen:
            seen.add(canonical.lower())
            result.append(canonical)

    return result
