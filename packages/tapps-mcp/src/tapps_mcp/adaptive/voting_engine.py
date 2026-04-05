"""Backward-compatible re-export.

Also wires ``_build_default_matrix`` so that patches against this
module propagate to the core implementation.
"""

from __future__ import annotations

from typing import Any

import tapps_core.adaptive.voting_engine as _core_voting
from tapps_core.adaptive.voting_engine import AdaptiveVotingEngine as AdaptiveVotingEngine
from tapps_core.adaptive.weight_distributor import WeightDistributor as WeightDistributor


def _build_default_matrix() -> Any:
    """Build a default weight matrix from :class:`ExpertRegistry`.

    This wrapper lives in tapps_mcp so that patches against
    ``tapps_mcp.adaptive.voting_engine.WeightDistributor`` work correctly.
    """
    from tapps_core.adaptive.models import ExpertWeightMatrix
    from tapps_core.experts.registry import ExpertRegistry

    experts = ExpertRegistry.get_all_experts()
    if not experts:
        return ExpertWeightMatrix()

    domains = [e.primary_domain for e in experts]
    primary_map = {e.primary_domain: e.expert_id for e in experts}

    return WeightDistributor.calculate_weights(domains, primary_map)


# Monkey-patch the core module so that AdaptiveVotingEngine.adjust_voting_weights
# (which calls _build_default_matrix at module level in tapps_core) uses our
# version. This allows tests patching tapps_mcp.adaptive.voting_engine._build_default_matrix
# to also affect the core.  We redirect via a lambda that calls the function
# from *this* module's globals, so mock.patch on this module works correctly.
_core_voting._build_default_matrix = lambda: globals()["_build_default_matrix"]()
