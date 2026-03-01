"""Backward-compatible re-export — delegates to tapps_core.adaptive."""

from __future__ import annotations

from tapps_core.adaptive import AdaptiveWeightsSnapshot as AdaptiveWeightsSnapshot
from tapps_core.adaptive import CodeOutcome as CodeOutcome
from tapps_core.adaptive import ExpertPerformance as ExpertPerformance
from tapps_core.adaptive import ExpertWeightMatrix as ExpertWeightMatrix
from tapps_core.adaptive import ExpertWeightsSnapshot as ExpertWeightsSnapshot
from tapps_core.adaptive import FileOutcomeTracker as FileOutcomeTracker
from tapps_core.adaptive import FilePerformanceTracker as FilePerformanceTracker
from tapps_core.adaptive import save_json_atomic as save_json_atomic
from tapps_core.adaptive import OutcomeTrackerProtocol as OutcomeTrackerProtocol
from tapps_core.adaptive import PerformanceTrackerProtocol as PerformanceTrackerProtocol
from tapps_core.adaptive import AdaptiveScoringEngine as AdaptiveScoringEngine
from tapps_core.adaptive import AdaptiveScorerWrapper as AdaptiveScorerWrapper
from tapps_core.adaptive import AdaptiveVotingEngine as AdaptiveVotingEngine
from tapps_core.adaptive import WeightDistributor as WeightDistributor
