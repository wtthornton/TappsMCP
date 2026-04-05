"""Adaptive domain detector for expert routing.

Detects domain suggestions from prompts, code patterns, and consultation
gaps.  Complements the existing :class:`DomainDetector` with adaptive
capabilities based on usage history.

Epic 57: Extends support to business domains with learned weight-based routing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Literal

import structlog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from tapps_core.adaptive.persistence import DomainWeightStore

logger = structlog.get_logger(__name__)


class DomainSuggestion(BaseModel):
    """A suggested domain with confidence and evidence."""

    domain: str = Field(description="Suggested domain name.")
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence.")
    source: str = Field(description="Detection source (prompt, code_pattern, consultation_gap).")
    evidence: list[str] = Field(default_factory=list, description="Supporting evidence.")
    keywords: list[str] = Field(default_factory=list, description="Matched keywords.")
    priority: str = Field(default="normal", description="Priority: low, normal, high, critical.")
    usage_frequency: int = Field(default=0, ge=0, description="Times this domain was detected.")


# Minimum confidence thresholds.
_MIN_PROMPT_CONFIDENCE = 0.5
_MIN_CODE_CONFIDENCE = 0.4
_LOW_CONFIDENCE_THRESHOLD = 0.6
_RECURRING_PATTERN_MIN_COUNT = 3

# Confidence threshold for adaptive routing to activate (Epic 57).
# Below this threshold, the detector falls back to static routing.
_ADAPTIVE_CONFIDENCE_THRESHOLD = 0.4


class AdaptiveDomainDetector:
    """Detects domains from prompts, code, and consultation history.

    This detector supplements the existing static :class:`DomainDetector`
    with adaptive, usage-pattern-based detection.

    Epic 57: Also provides :meth:`detect` which uses learned weights from
    feedback to route questions to the best domain (both technical and
    business domains supported).
    """

    DOMAIN_KEYWORDS: ClassVar[dict[str, list[str]]] = {
        "oauth2": ["oauth", "oauth2", "openid", "oidc", "jwt", "refresh token", "access token"],
        "api-clients": ["api client", "rest client", "http client", "sdk", "api wrapper"],
        "graphql": ["graphql", "gql", "query mutation", "schema stitching", "apollo"],
        "microservices": ["microservice", "service mesh", "grpc", "protobuf", "sidecar"],
        "event-driven": ["event driven", "event sourcing", "cqrs", "message queue", "pub sub"],
        "websocket": ["websocket", "ws://", "wss://", "socket.io", "real-time"],
        "mqtt": ["mqtt", "mosquitto", "paho", "iot protocol", "qos level"],
        "grpc": ["grpc", "protobuf", "protocol buffers", "grpc-web"],
        "serverless": ["serverless", "lambda", "cloud function", "faas"],
        "kubernetes": ["kubernetes", "k8s", "helm", "kustomize", "kubectl"],
        "docker": ["docker", "dockerfile", "container", "docker-compose"],
        "ci-cd": ["ci/cd", "pipeline", "github actions", "jenkins", "gitlab ci"],
        "monitoring": ["monitoring", "prometheus", "grafana", "alerting", "observability"],
        "authentication": ["authentication", "login", "session", "password", "mfa", "2fa"],
        "authorization": ["authorization", "rbac", "permissions", "access control", "acl"],
        "database": ["database", "sql", "nosql", "orm", "migration", "schema"],
        "caching": ["caching", "redis", "memcached", "cache invalidation", "ttl"],
        "search": ["search", "elasticsearch", "full-text", "indexing", "lucene"],
        "queue": ["message queue", "rabbitmq", "kafka", "celery", "task queue"],
        "testing": ["testing", "unit test", "integration test", "e2e", "test coverage"],
    }

    CODE_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "oauth2": [
            r"OAuth2Session",
            r"refresh_token",
            r"authorization_code",
        ],
        "websocket": [
            r"ws://",
            r"wss://",
            r"WebSocket\(",
            r"socketio",
        ],
        "mqtt": [
            r"mqtt\.Client",
            r"paho\.mqtt",
            r"on_message",
        ],
        "database": [
            r"CREATE\s+TABLE",
            r"SELECT\s+.+\s+FROM",
            r"sqlalchemy",
            r"\.execute\(",
        ],
        "docker": [
            r"FROM\s+\w+:\w+",
            r"ENTRYPOINT\s+\[",
            r"docker-compose",
        ],
    }

    def __init__(self, project_root: str | Path | None = None) -> None:
        """Initialize the detector.

        Args:
            project_root: Project root directory. Required for weight-based
                routing via :meth:`detect`. Can be a string or Path.
        """
        if project_root is not None:
            self._project_root: Path | None = Path(project_root)
        else:
            self._project_root = None
        self._weight_store: DomainWeightStore | None = None

    def _get_weight_store(self) -> DomainWeightStore | None:
        """Lazily initialize and return the weight store."""
        if self._weight_store is not None:
            return self._weight_store
        if self._project_root is None:
            return None
        from tapps_core.adaptive.persistence import DomainWeightStore

        self._weight_store = DomainWeightStore(self._project_root)
        return self._weight_store

    # ------------------------------------------------------------------
    # Weight-based routing (Epic 57)
    # ------------------------------------------------------------------

    def detect(
        self,
        question: str,
        *,
        include_business: bool = True,
    ) -> tuple[str, float]:
        """Detect the best domain for a question using learned weights.

        Uses :class:`DomainDetector` for base keyword matching, then applies
        learned weights from :class:`DomainWeightStore` to adjust confidence
        scores. Returns the domain with the highest weighted confidence.

        Args:
            question: The user's question text.
            include_business: If True, include business (project-specific)
                domains in addition to technical (built-in) domains.

        Returns:
            A tuple of (domain, confidence). Returns ("unknown", 0.0) if
            no domain matches above the threshold.

        Note:
            Falls back to static routing if:
            - No project_root was provided (can't load weights)
            - No matching domains found
            - All confidences are below the threshold
        """
        from tapps_core.experts.domain_detector import DomainDetector
        from tapps_core.experts.registry import ExpertRegistry

        # Get base detection results from static detector.
        if include_business:
            results = DomainDetector.detect_from_question_merged(question)
        else:
            results = DomainDetector.detect_from_question(question)

        if not results:
            return ("unknown", 0.0)

        # Get business domains for categorization.
        business_domains = ExpertRegistry.get_business_domains()

        # Apply learned weights to adjust confidence.
        weighted_results: list[tuple[str, float, float]] = []  # (domain, raw_conf, weighted_conf)
        weight_store = self._get_weight_store()

        for mapping in results:
            domain = mapping.domain
            raw_confidence = mapping.confidence

            # Determine if this is a business or technical domain.
            is_business = domain in business_domains
            domain_type: Literal["technical", "business"] = (
                "business" if is_business else "technical"
            )

            # Get learned weight (defaults to 1.0 if not found).
            if weight_store is not None:
                weight = weight_store.get_weight_value(domain, domain_type=domain_type)
            else:
                weight = 1.0

            # Apply weight to confidence (multiplicative).
            weighted_confidence = min(1.0, raw_confidence * weight)
            weighted_results.append((domain, raw_confidence, weighted_confidence))

        # Sort by weighted confidence (descending).
        weighted_results.sort(key=lambda x: x[2], reverse=True)

        # Return the best match if above threshold.
        best_domain, _raw_conf, best_confidence = weighted_results[0]
        if best_confidence >= _ADAPTIVE_CONFIDENCE_THRESHOLD:
            logger.debug(
                "adaptive_domain_detected",
                domain=best_domain,
                confidence=round(best_confidence, 4),
                raw_confidence=round(_raw_conf, 4),
            )
            return (best_domain, round(best_confidence, 4))

        # Fall back to unknown if below threshold.
        logger.debug(
            "adaptive_domain_below_threshold",
            best_domain=best_domain,
            confidence=round(best_confidence, 4),
            threshold=_ADAPTIVE_CONFIDENCE_THRESHOLD,
        )
        return ("unknown", 0.0)

    def detect_with_details(
        self,
        question: str,
        *,
        include_business: bool = True,
    ) -> dict[str, Any]:
        """Detect domain with full details including weight adjustments.

        Like :meth:`detect`, but returns a detailed dictionary with:
        - domain: The selected domain
        - confidence: Final weighted confidence
        - raw_confidence: Original confidence before weighting
        - weight_applied: The learned weight that was applied
        - domain_type: "technical" or "business"
        - all_candidates: List of all considered domains with scores

        Args:
            question: The user's question text.
            include_business: If True, include business domains.

        Returns:
            Dictionary with detection details.
        """
        from tapps_core.experts.domain_detector import DomainDetector
        from tapps_core.experts.registry import ExpertRegistry

        # Get base detection results.
        if include_business:
            results = DomainDetector.detect_from_question_merged(question)
        else:
            results = DomainDetector.detect_from_question(question)

        if not results:
            return {
                "domain": "unknown",
                "confidence": 0.0,
                "raw_confidence": 0.0,
                "weight_applied": 1.0,
                "domain_type": "unknown",
                "all_candidates": [],
            }

        business_domains = ExpertRegistry.get_business_domains()
        weight_store = self._get_weight_store()

        candidates: list[dict[str, Any]] = []
        for mapping in results:
            domain = mapping.domain
            raw_confidence = mapping.confidence
            is_business = domain in business_domains
            domain_type: Literal["technical", "business"] = (
                "business" if is_business else "technical"
            )

            if weight_store is not None:
                weight = weight_store.get_weight_value(domain, domain_type=domain_type)
            else:
                weight = 1.0

            weighted_confidence = min(1.0, raw_confidence * weight)
            candidates.append({
                "domain": domain,
                "confidence": round(weighted_confidence, 4),
                "raw_confidence": round(raw_confidence, 4),
                "weight_applied": round(weight, 4),
                "domain_type": domain_type,
            })

        # Sort by weighted confidence.
        candidates.sort(key=lambda x: x["confidence"], reverse=True)

        best = candidates[0]
        return {
            "domain": best["domain"],
            "confidence": best["confidence"],
            "raw_confidence": best["raw_confidence"],
            "weight_applied": best["weight_applied"],
            "domain_type": best["domain_type"],
            "all_candidates": candidates,
        }

    async def detect_domains(
        self,
        prompt: str | None = None,
        code_context: str | None = None,
        consultation_history: list[dict[str, Any]] | None = None,
    ) -> list[DomainSuggestion]:
        """Detect domains from all available signals.

        Returns suggestions sorted by priority (desc) then confidence (desc).
        """
        suggestions: list[DomainSuggestion] = []

        if prompt:
            suggestions.extend(self._detect_from_prompt(prompt))
        if code_context:
            suggestions.extend(self._detect_from_code_patterns(code_context))
        if consultation_history:
            suggestions.extend(self._detect_from_consultation_gaps(consultation_history))

        # Filter out already-known domains for prompt/code suggestions.
        # Consultation gap suggestions intentionally reference existing domains.
        known = self._get_existing_domains()
        suggestions = [
            s for s in suggestions if s.domain not in known or s.source == "consultation_gap"
        ]

        # Deduplicate by domain (keep highest confidence).
        seen: dict[str, DomainSuggestion] = {}
        for s in suggestions:
            if s.domain not in seen or s.confidence > seen[s.domain].confidence:
                seen[s.domain] = s
        unique = list(seen.values())

        # Sort by priority rank then confidence.
        priority_rank = {"critical": 0, "high": 1, "normal": 2, "low": 3}
        unique.sort(key=lambda s: (priority_rank.get(s.priority, 2), -s.confidence))

        return unique

    def _detect_from_prompt(self, prompt: str) -> list[DomainSuggestion]:
        """Detect domains from keyword matching in the prompt."""
        suggestions: list[DomainSuggestion] = []
        prompt_lower = prompt.lower()

        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            matched: list[str] = []
            for kw in keywords:
                # Use word-boundary matching for short keywords.
                if len(kw) <= 3:
                    if re.search(rf"\b{re.escape(kw)}\b", prompt_lower):
                        matched.append(kw)
                elif kw.lower() in prompt_lower:
                    matched.append(kw)

            if matched:
                conf = min(1.0, _MIN_PROMPT_CONFIDENCE + len(matched) * 0.15)
                suggestions.append(
                    DomainSuggestion(
                        domain=domain,
                        confidence=round(conf, 2),
                        source="prompt",
                        evidence=[f"Keyword match: {kw}" for kw in matched],
                        keywords=matched,
                    )
                )

        return suggestions

    def _detect_from_code_patterns(self, code: str) -> list[DomainSuggestion]:
        """Detect domains from regex patterns in code."""
        suggestions: list[DomainSuggestion] = []

        for domain, patterns in self.CODE_PATTERNS.items():
            matched: list[str] = []
            for pattern in patterns:
                if re.search(pattern, code, re.IGNORECASE):
                    matched.append(pattern)

            if matched:
                conf = min(1.0, _MIN_CODE_CONFIDENCE + len(matched) * 0.2)
                suggestions.append(
                    DomainSuggestion(
                        domain=domain,
                        confidence=round(conf, 2),
                        source="code_pattern",
                        evidence=[f"Pattern match: {p}" for p in matched],
                    )
                )

        return suggestions

    @staticmethod
    def _detect_from_consultation_gaps(
        history: list[dict[str, Any]],
    ) -> list[DomainSuggestion]:
        """Detect domains from low-confidence consultations."""
        suggestions: list[DomainSuggestion] = []
        domain_confs: dict[str, list[float]] = {}

        for entry in history:
            domain = entry.get("domain", "")
            conf = entry.get("confidence", 1.0)
            if domain:
                domain_confs.setdefault(domain, []).append(conf)

        for domain, confs in domain_confs.items():
            avg_conf = sum(confs) / len(confs)
            if avg_conf < _LOW_CONFIDENCE_THRESHOLD:
                suggestions.append(
                    DomainSuggestion(
                        domain=domain,
                        confidence=round(1.0 - avg_conf, 2),
                        source="consultation_gap",
                        evidence=[f"Low avg confidence: {avg_conf:.2f}"],
                        priority="high",
                    )
                )

        return suggestions

    @staticmethod
    def _get_existing_domains() -> set[str]:
        """Return the set of already-registered domains."""
        try:
            from tapps_core.experts.registry import ExpertRegistry

            return {e.primary_domain for e in ExpertRegistry.get_all_experts()}
        except ImportError:
            return set()

    @staticmethod
    async def detect_recurring_patterns(
        detection_history: list[DomainSuggestion],
    ) -> list[DomainSuggestion]:
        """Identify domains that appear frequently in detection history."""
        counts: dict[str, int] = {}
        for s in detection_history:
            counts[s.domain] = counts.get(s.domain, 0) + 1

        recurring: list[DomainSuggestion] = []
        for domain, count in counts.items():
            if count >= _RECURRING_PATTERN_MIN_COUNT:
                recurring.append(
                    DomainSuggestion(
                        domain=domain,
                        confidence=min(1.0, 0.5 + count * 0.1),
                        source="recurring_pattern",
                        evidence=[f"Detected {count} times"],
                        usage_frequency=count,
                        priority="high",
                    )
                )

        return recurring
