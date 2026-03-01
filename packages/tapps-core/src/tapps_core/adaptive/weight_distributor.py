"""Expert weight distribution utility.

Implements the 51% primary / 49% distributed formula for expert voting
weights across domains.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import ClassVar

import structlog

from tapps_core.adaptive.models import ExpertWeightMatrix

logger = structlog.get_logger(__name__)

# Primary expert weight floor.
_PRIMARY_WEIGHT = Decimal("0.51")
_OTHER_POOL = Decimal("0.49")


class WeightDistributor:
    """Static utility for computing expert weight distributions."""

    PRIMARY_WEIGHT: ClassVar[float] = 0.51
    OTHER_WEIGHT: ClassVar[float] = 0.49

    @staticmethod
    def calculate_weights(
        domains: list[str],
        expert_primary_map: dict[str, str],
    ) -> ExpertWeightMatrix:
        """Build an :class:`ExpertWeightMatrix` from a domain-to-primary mapping.

        Args:
            domains: All domains in the matrix.
            expert_primary_map: Mapping of ``domain -> primary_expert_id``.

        Returns:
            A validated :class:`ExpertWeightMatrix`.

        Raises:
            ValueError: If validation fails (missing domains, duplicate primaries).
        """
        # Validate.
        for d in domains:
            if d not in expert_primary_map:
                msg = f"Domain '{d}' has no primary expert assigned"
                raise ValueError(msg)

        experts = sorted({expert_primary_map[d] for d in domains})
        n_experts = len(experts)

        weights: dict[str, dict[str, float]] = {eid: {} for eid in experts}

        for domain in domains:
            primary = expert_primary_map[domain]

            if n_experts == 1:
                weights[primary][domain] = 1.0
                continue

            # Primary gets 51%, rest share 49%.
            others = [e for e in experts if e != primary]
            other_count = len(others)

            if other_count == 0:
                weights[primary][domain] = 1.0
                continue

            per_other = _OTHER_POOL / Decimal(other_count)
            per_other_rounded = float(per_other.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))

            weights[primary][domain] = float(_PRIMARY_WEIGHT)
            for eid in others:
                weights[eid][domain] = per_other_rounded

            # Adjust primary to make column sum exactly 1.0.
            col_sum = sum(weights[eid][domain] for eid in experts)
            diff = 1.0 - col_sum
            weights[primary][domain] = round(weights[primary][domain] + diff, 4)

        return ExpertWeightMatrix(
            weights=weights,
            domains=domains,
            experts=experts,
        )

    @staticmethod
    def recalculate_on_domain_add(
        current_matrix: ExpertWeightMatrix,
        new_domain: str,
        new_expert_id: str,
    ) -> ExpertWeightMatrix:
        """Return a new matrix with *new_domain* added under *new_expert_id*."""
        updated_domains = [*current_matrix.domains, new_domain]

        # Build primary map from existing matrix + new entry.
        primary_map: dict[str, str] = {}
        for domain in current_matrix.domains:
            primary = current_matrix.get_primary_expert(domain)
            if primary:
                primary_map[domain] = primary
        primary_map[new_domain] = new_expert_id

        return WeightDistributor.calculate_weights(updated_domains, primary_map)

    @staticmethod
    def format_matrix(matrix: ExpertWeightMatrix) -> str:
        """Return a human-readable table representation of *matrix*."""
        if not matrix.domains or not matrix.experts:
            return "(empty matrix)"

        # Column widths.
        col_w = max(len(d) for d in matrix.domains)
        id_w = max(len(e) for e in matrix.experts)
        col_w = max(col_w, 8)
        id_w = max(id_w, 10)

        header = f"{'Expert':<{id_w}}"
        for d in matrix.domains:
            header += f"  {d:>{col_w}}"
        lines = [header, "-" * len(header)]

        for eid in matrix.experts:
            row = f"{eid:<{id_w}}"
            for d in matrix.domains:
                w = matrix.get_expert_weight(eid, d)
                row += f"  {w:>{col_w}.4f}"
            lines.append(row)

        return "\n".join(lines)
