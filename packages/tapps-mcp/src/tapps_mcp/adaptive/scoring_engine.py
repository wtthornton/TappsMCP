"""Backward-compatible re-export."""

from __future__ import annotations

from tapps_core.adaptive.scoring_engine import DEFAULT_LEARNING_RATE as DEFAULT_LEARNING_RATE
from tapps_core.adaptive.scoring_engine import (
    MIN_OUTCOMES_FOR_ADJUSTMENT as MIN_OUTCOMES_FOR_ADJUSTMENT,
)
from tapps_core.adaptive.scoring_engine import AdaptiveScoringEngine as AdaptiveScoringEngine
from tapps_core.adaptive.scoring_engine import _get_default_weights as _get_default_weights
from tapps_core.adaptive.scoring_engine import _pearson_correlation as _pearson_correlation
