"""Thin adapter wiring adaptive weights into CodeScorer.

Provides caching and a convenience method that returns a
:class:`~tapps_mcp.config.settings.ScoringWeights` instance ready to
be passed to :class:`~tapps_mcp.scoring.scorer.CodeScorer`.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import structlog

from tapps_mcp.adaptive.models import CodeOutcome

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.adaptive.protocols import OutcomeTrackerProtocol
    from tapps_mcp.adaptive.scoring_engine import AdaptiveScoringEngine
    from tapps_mcp.config.settings import ScoringWeights

logger = structlog.get_logger(__name__)


class AdaptiveScorerWrapper:
    """Caching wrapper around :class:`AdaptiveScoringEngine`.

    Produces :class:`ScoringWeights` objects that can be passed directly
    to :class:`CodeScorer.__init__`.
    """

    def __init__(
        self,
        outcome_tracker: OutcomeTrackerProtocol | None = None,
        adaptive_engine: AdaptiveScoringEngine | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self._tracker = outcome_tracker
        self._engine = adaptive_engine
        self._enabled = enabled
        self._cached_weights: dict[str, float] | None = None

    async def get_adaptive_weights(
        self,
        *,
        force_reload: bool = False,
    ) -> dict[str, float] | None:
        """Return adaptive weights, or ``None`` if disabled / unavailable."""
        if not self._enabled or self._engine is None:
            return None

        if self._cached_weights is not None and not force_reload:
            return dict(self._cached_weights)

        try:
            weights = await self._engine.adjust_weights()
            self._cached_weights = weights
            return dict(weights)
        except Exception:
            logger.warning("adaptive_weights_failed", exc_info=True)
            return None

    def get_weights_as_settings(
        self,
        default: ScoringWeights | None = None,
    ) -> ScoringWeights:
        """Convert cached adaptive weights into a :class:`ScoringWeights` instance.

        Falls back to *default* (or ``ScoringWeights()`` if not provided)
        when adaptive weights are not available.
        """
        from tapps_mcp.config.settings import ScoringWeights

        if self._cached_weights is None:
            return default if default is not None else ScoringWeights()

        try:
            return ScoringWeights(**self._cached_weights)  # type: ignore[arg-type]
        except Exception:
            logger.warning("adaptive_weights_conversion_failed", exc_info=True)
            return default if default is not None else ScoringWeights()

    async def track_outcome(
        self,
        workflow_id: str,
        file_path: Path,
        scores: dict[str, float],
        *,
        expert_consultations: list[str] | None = None,
        agent_id: str | None = None,
        prompt_hash: str | None = None,
    ) -> None:
        """Record an outcome via the underlying tracker."""
        if self._tracker is None:
            return

        outcome = CodeOutcome(
            workflow_id=workflow_id,
            file_path=str(file_path),
            initial_scores=scores,
            expert_consultations=expert_consultations or [],
            agent_id=agent_id,
            prompt_hash=prompt_hash,
        )
        self._tracker.save_outcome(outcome)

    @staticmethod
    def hash_prompt(prompt: str) -> str:
        """Return a deterministic 16-char hex hash of *prompt*."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
