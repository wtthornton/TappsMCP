"""File-based implementations of the adaptive tracking protocols.

Provides JSONL-backed :class:`FileOutcomeTracker` and
:class:`FilePerformanceTracker` that satisfy the protocol interfaces
defined in :mod:`tapps_core.adaptive.protocols`.

Also provides :class:`DomainWeightStore` for persisting learned domain
routing weights (Epic 57).
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import structlog

from tapps_core.adaptive.models import (
    CodeOutcome,
    DomainWeightEntry,
    DomainWeightsSnapshot,
    ExpertPerformance,
    _utc_now_iso,
)

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

# Quality threshold for first-pass success determination.
_QUALITY_THRESHOLD = 70.0

# Weakness detection thresholds.
_LOW_CONFIDENCE_THRESHOLD = 0.6
_LOW_SUCCESS_THRESHOLD = 0.5


class FileOutcomeTracker:
    """JSONL file-backed outcome tracker.

    Each :class:`CodeOutcome` is appended as a single JSON line to
    ``{project_root}/.tapps-mcp/learning/outcomes.jsonl``.
    """

    def __init__(self, project_root: Path) -> None:
        self._store_dir = project_root / ".tapps-mcp" / "learning"
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._store_dir / "outcomes.jsonl"

    # -- Protocol methods ---------------------------------------------------

    def save_outcome(self, outcome: CodeOutcome) -> None:
        """Append *outcome* as a JSONL record."""
        line = json.dumps(outcome.model_dump(), ensure_ascii=False)
        try:
            with self._file.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            logger.warning("outcome_save_failed", file=str(self._file), exc_info=True)

    def load_outcomes(
        self,
        limit: int | None = None,
        workflow_id: str | None = None,
    ) -> list[CodeOutcome]:
        """Load outcomes from disk, optionally filtered by *workflow_id*."""
        if not self._file.exists():
            return []

        outcomes: list[CodeOutcome] = []
        try:
            text = self._file.read_text(encoding="utf-8")
        except OSError:
            logger.warning("outcome_load_failed", file=str(self._file), exc_info=True)
            return []

        for line in text.strip().splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                outcome = CodeOutcome.model_validate(data)
                if workflow_id is not None and outcome.workflow_id != workflow_id:
                    continue
                outcomes.append(outcome)
            except (json.JSONDecodeError, ValueError):
                logger.debug("outcome_parse_failed", line=line[:120])

        if limit is not None:
            outcomes = outcomes[-limit:]
        return outcomes

    def get_statistics(self) -> dict[str, Any]:
        """Return aggregate statistics over stored outcomes."""
        outcomes = self.load_outcomes()
        if not outcomes:
            return {
                "total_outcomes": 0,
                "first_pass_success_rate": 0.0,
                "avg_iterations": 0.0,
                "expert_usage": {},
            }

        first_pass_count = sum(1 for o in outcomes if o.first_pass_success)
        total_iterations = sum(o.iterations for o in outcomes)
        expert_usage: dict[str, int] = {}
        for o in outcomes:
            for eid in o.expert_consultations:
                expert_usage[eid] = expert_usage.get(eid, 0) + 1

        return {
            "total_outcomes": len(outcomes),
            "first_pass_success_rate": first_pass_count / len(outcomes),
            "avg_iterations": total_iterations / len(outcomes),
            "expert_usage": expert_usage,
        }


class FilePerformanceTracker:
    """JSONL file-backed expert performance tracker.

    Consultation records are appended to
    ``{project_root}/.tapps-mcp/learning/expert_performance.jsonl``.
    """

    def __init__(self, project_root: Path) -> None:
        self._store_dir = project_root / ".tapps-mcp" / "learning"
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._store_dir / "expert_performance.jsonl"

    # -- Protocol methods ---------------------------------------------------

    def track_consultation(
        self,
        expert_id: str,
        domain: str,
        confidence: float,
        query: str | None = None,
    ) -> None:
        """Append a consultation record."""
        record = {
            "expert_id": expert_id,
            "domain": domain,
            "confidence": confidence,
            "query": query or "",
            "timestamp": _utc_now_iso(),
        }
        line = json.dumps(record, ensure_ascii=False)
        try:
            with self._file.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            logger.warning("consultation_save_failed", file=str(self._file), exc_info=True)

    def calculate_performance(
        self,
        expert_id: str,
        days: int = 30,
    ) -> ExpertPerformance | None:
        """Calculate aggregated performance for *expert_id* within *days*."""
        records = self._load_consultations(expert_id, days)
        if not records:
            return None

        confidences = [r["confidence"] for r in records]
        domains = list({r["domain"] for r in records})
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        weaknesses = self._identify_weaknesses(avg_conf)

        return ExpertPerformance(
            expert_id=expert_id,
            consultations=len(records),
            avg_confidence=round(avg_conf, 4),
            first_pass_success_rate=0.0,  # requires outcome data from Epic 7
            code_quality_improvement=0.0,  # requires outcome data from Epic 7
            domain_coverage=domains,
            weaknesses=weaknesses,
        )

    def get_all_performance(
        self,
        days: int = 30,
    ) -> dict[str, ExpertPerformance]:
        """Calculate performance for every tracked expert."""
        all_ids = self._get_all_expert_ids(days)
        results: dict[str, ExpertPerformance] = {}
        for eid in all_ids:
            perf = self.calculate_performance(eid, days)
            if perf is not None:
                results[eid] = perf
        return results

    # -- Private helpers ----------------------------------------------------

    def _load_consultations(
        self,
        expert_id: str | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Load consultation records, filtered by expert and time window."""
        if not self._file.exists():
            return []

        try:
            text = self._file.read_text(encoding="utf-8")
        except OSError:
            return []

        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        return [
            data
            for line in text.strip().splitlines()
            if line.strip()
            and (data := self._parse_consultation_line(line)) is not None
            and self._passes_consultation_filter(data, expert_id, cutoff)
        ]

    @staticmethod
    def _parse_consultation_line(line: str) -> dict[str, Any] | None:
        """Parse a JSONL line into a consultation record, or None if invalid."""
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _passes_consultation_filter(
        data: dict[str, Any],
        expert_id: str | None,
        cutoff: datetime,
    ) -> bool:
        """Return True if record passes time and expert filters."""
        ts_str = data.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            if ts < cutoff:
                return False
        except (ValueError, TypeError):
            pass  # keep records without valid timestamps

        return expert_id is None or data.get("expert_id") == expert_id

    def _get_all_expert_ids(self, days: int = 30) -> set[str]:
        """Return all unique expert IDs within the time window."""
        records = self._load_consultations(expert_id=None, days=days)
        return {r["expert_id"] for r in records if "expert_id" in r}

    @staticmethod
    def _identify_weaknesses(avg_confidence: float) -> list[str]:
        """Identify weakness indicators from aggregate metrics."""
        weaknesses: list[str] = []
        if avg_confidence < _LOW_CONFIDENCE_THRESHOLD:
            weaknesses.append("low_confidence")
        return weaknesses


def save_json_atomic(data: dict[str, Any] | list[Any], target: Path) -> None:
    """Write *data* to *target* atomically via a temporary file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        Path(tmp_path).replace(target)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_path).unlink()
        raise


def _save_yaml_atomic(data: dict[str, Any], target: Path) -> None:
    """Write *data* to *target* as YAML atomically via a temporary file."""
    try:
        import yaml
    except ImportError:
        logger.warning("yaml_not_available", msg="Falling back to JSON format")
        save_json_atomic(data, target.with_suffix(".json"))
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, default_flow_style=False, allow_unicode=True)
        Path(tmp_path).replace(target)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_path).unlink()
        raise


# ---------------------------------------------------------------------------
# Domain weight persistence (Epic 57)
# ---------------------------------------------------------------------------

DomainType = Literal["technical", "business"]

# Default weight for domains without feedback history.
_DEFAULT_DOMAIN_WEIGHT = 1.0

# Minimum weight to prevent domains from being completely ignored.
_MIN_DOMAIN_WEIGHT = 0.1

# Maximum weight to prevent single domain from dominating.
_MAX_DOMAIN_WEIGHT = 3.0


class DomainWeightStore:
    """YAML file-backed domain routing weight store.

    Stores learned domain routing weights separately for technical (built-in)
    and business (project-specific) domains. Weights are persisted to
    ``{project_root}/.tapps-mcp/adaptive/domain_weights.yaml``.

    Usage::

        store = DomainWeightStore(project_root)

        # Save or update a weight
        store.save_weight("security", 1.2, samples=45, domain_type="technical")

        # Load all weights
        snapshot = store.load_weights()

        # Get a specific weight
        entry = store.get_weight("security", domain_type="technical")

        # Update from feedback
        store.update_from_feedback("security", helpful=True, domain_type="technical")
    """

    def __init__(self, project_root: Path) -> None:
        """Initialize the store with a project root directory.

        Args:
            project_root: Root directory of the project. Weights are stored
                in ``.tapps-mcp/adaptive/domain_weights.yaml`` within this dir.
        """
        self._store_dir = project_root / ".tapps-mcp" / "adaptive"
        self._file = self._store_dir / "domain_weights.yaml"
        self._json_fallback = self._store_dir / "domain_weights.json"

    # -- Public API ---------------------------------------------------------

    def save_weight(
        self,
        domain: str,
        weight: float,
        *,
        samples: int = 0,
        positive_count: int = 0,
        negative_count: int = 0,
        domain_type: DomainType = "technical",
    ) -> None:
        """Save or update a domain weight entry.

        Args:
            domain: Domain identifier (e.g., "security", "acme-billing").
            weight: Learned routing weight (clamped to [0.1, 3.0]).
            samples: Total number of feedback samples.
            positive_count: Number of positive feedback samples.
            negative_count: Number of negative feedback samples.
            domain_type: Whether this is a "technical" or "business" domain.
        """
        snapshot = self.load_weights()
        entry = DomainWeightEntry(
            domain=domain,
            weight=max(_MIN_DOMAIN_WEIGHT, min(_MAX_DOMAIN_WEIGHT, weight)),
            samples=samples,
            positive_count=positive_count,
            negative_count=negative_count,
            last_updated=_utc_now_iso(),
        )

        if domain_type == "technical":
            snapshot.technical[domain] = entry
        else:
            snapshot.business[domain] = entry

        snapshot.timestamp = _utc_now_iso()
        self._persist(snapshot)

    def load_weights(self) -> DomainWeightsSnapshot:
        """Load all domain weights from disk.

        Returns an empty snapshot if the file doesn't exist (graceful degradation).

        Returns:
            A :class:`DomainWeightsSnapshot` with technical and business weights.
        """
        # Try YAML first, then JSON fallback
        if self._file.exists():
            return self._load_yaml()
        if self._json_fallback.exists():
            return self._load_json_fallback()

        # No existing file - return empty snapshot
        return DomainWeightsSnapshot()

    def get_weight(
        self,
        domain: str,
        *,
        domain_type: DomainType = "technical",
    ) -> DomainWeightEntry | None:
        """Get the weight entry for a specific domain.

        Args:
            domain: Domain identifier to look up.
            domain_type: Whether to look in "technical" or "business" weights.

        Returns:
            The :class:`DomainWeightEntry` if found, else ``None``.
        """
        snapshot = self.load_weights()
        weights = snapshot.technical if domain_type == "technical" else snapshot.business
        return weights.get(domain)

    def get_weight_value(
        self,
        domain: str,
        *,
        domain_type: DomainType = "technical",
    ) -> float:
        """Get the numeric weight for a domain, defaulting to 1.0 if not found.

        Args:
            domain: Domain identifier to look up.
            domain_type: Whether to look in "technical" or "business" weights.

        Returns:
            The weight value, or 1.0 if the domain has no stored weight.
        """
        entry = self.get_weight(domain, domain_type=domain_type)
        return entry.weight if entry else _DEFAULT_DOMAIN_WEIGHT

    def update_from_feedback(
        self,
        domain: str,
        *,
        helpful: bool,
        domain_type: DomainType = "technical",
        learning_rate: float = 0.1,
    ) -> DomainWeightEntry:
        """Update a domain's weight based on feedback.

        Positive feedback increases weight; negative decreases it.
        Uses exponential smoothing with the given learning rate.

        Args:
            domain: Domain identifier to update.
            helpful: Whether the feedback was positive (True) or negative (False).
            domain_type: Whether this is a "technical" or "business" domain.
            learning_rate: How much to adjust the weight (0.0-1.0).

        Returns:
            The updated :class:`DomainWeightEntry`.
        """
        snapshot = self.load_weights()
        weights = snapshot.technical if domain_type == "technical" else snapshot.business

        # Get existing entry or create new one
        entry = weights.get(domain)
        if entry is None:
            entry = DomainWeightEntry(domain=domain)

        # Update counts
        new_samples = entry.samples + 1
        new_positive = entry.positive_count + (1 if helpful else 0)
        new_negative = entry.negative_count + (0 if helpful else 1)

        # Calculate new weight using exponential smoothing
        adjustment = learning_rate if helpful else -learning_rate
        new_weight = entry.weight * (1.0 + adjustment)
        new_weight = max(_MIN_DOMAIN_WEIGHT, min(_MAX_DOMAIN_WEIGHT, new_weight))

        # Save updated entry
        self.save_weight(
            domain,
            new_weight,
            samples=new_samples,
            positive_count=new_positive,
            negative_count=new_negative,
            domain_type=domain_type,
        )

        # Return the updated entry
        return DomainWeightEntry(
            domain=domain,
            weight=new_weight,
            samples=new_samples,
            positive_count=new_positive,
            negative_count=new_negative,
            last_updated=_utc_now_iso(),
        )

    def load_technical_weights(self) -> dict[str, DomainWeightEntry]:
        """Load only technical domain weights.

        Returns:
            Dictionary mapping domain names to weight entries.
        """
        return dict(self.load_weights().technical)

    def load_business_weights(self) -> dict[str, DomainWeightEntry]:
        """Load only business domain weights.

        Returns:
            Dictionary mapping domain names to weight entries.
        """
        return dict(self.load_weights().business)

    def delete_weight(
        self,
        domain: str,
        *,
        domain_type: DomainType = "technical",
    ) -> bool:
        """Remove a domain's weight entry.

        Args:
            domain: Domain identifier to remove.
            domain_type: Whether to remove from "technical" or "business" weights.

        Returns:
            True if the entry was removed, False if it didn't exist.
        """
        snapshot = self.load_weights()
        weights = snapshot.technical if domain_type == "technical" else snapshot.business

        if domain not in weights:
            return False

        del weights[domain]
        snapshot.timestamp = _utc_now_iso()
        self._persist(snapshot)
        return True

    def clear_weights(self, *, domain_type: DomainType | None = None) -> None:
        """Clear stored weights.

        Args:
            domain_type: If specified, clear only that type. If None, clear all.
        """
        snapshot = self.load_weights()

        if domain_type is None:
            snapshot.technical = {}
            snapshot.business = {}
        elif domain_type == "technical":
            snapshot.technical = {}
        else:
            snapshot.business = {}

        snapshot.timestamp = _utc_now_iso()
        self._persist(snapshot)

    def get_statistics(self) -> dict[str, Any]:
        """Return aggregate statistics over stored weights.

        Returns:
            Dictionary with counts, averages, and top domains by weight.
        """
        snapshot = self.load_weights()

        tech_entries = list(snapshot.technical.values())
        biz_entries = list(snapshot.business.values())
        all_entries = tech_entries + biz_entries

        if not all_entries:
            return {
                "total_domains": 0,
                "technical_count": 0,
                "business_count": 0,
                "total_samples": 0,
                "avg_weight": _DEFAULT_DOMAIN_WEIGHT,
                "top_technical": [],
                "top_business": [],
            }

        total_samples = sum(e.samples for e in all_entries)
        avg_weight = sum(e.weight for e in all_entries) / len(all_entries)

        # Top 5 by weight in each category
        top_tech = sorted(tech_entries, key=lambda e: e.weight, reverse=True)[:5]
        top_biz = sorted(biz_entries, key=lambda e: e.weight, reverse=True)[:5]

        return {
            "total_domains": len(all_entries),
            "technical_count": len(tech_entries),
            "business_count": len(biz_entries),
            "total_samples": total_samples,
            "avg_weight": round(avg_weight, 4),
            "top_technical": [{"domain": e.domain, "weight": e.weight} for e in top_tech],
            "top_business": [{"domain": e.domain, "weight": e.weight} for e in top_biz],
        }

    # -- Private helpers ----------------------------------------------------

    def _persist(self, snapshot: DomainWeightsSnapshot) -> None:
        """Persist snapshot to disk (YAML preferred, JSON fallback)."""
        data = snapshot.model_dump(mode="json")
        # Convert DomainWeightEntry dicts for cleaner YAML
        for section in ("technical", "business"):
            if section in data:
                data[section] = {
                    k: {
                        "weight": v["weight"],
                        "samples": v["samples"],
                        "positive_count": v["positive_count"],
                        "negative_count": v["negative_count"],
                        "last_updated": v["last_updated"],
                    }
                    for k, v in data[section].items()
                }
        try:
            _save_yaml_atomic(data, self._file)
        except OSError:
            logger.warning("domain_weights_save_failed", file=str(self._file), exc_info=True)

    def _load_yaml(self) -> DomainWeightsSnapshot:
        """Load weights from YAML file."""
        try:
            import yaml

            text = self._file.read_text(encoding="utf-8")
            data = yaml.safe_load(text) or {}
        except ImportError:
            logger.warning("yaml_not_available", msg="Cannot load YAML weights")
            return DomainWeightsSnapshot()
        except (OSError, yaml.YAMLError) as e:
            logger.warning("domain_weights_load_failed", file=str(self._file), error=str(e))
            return DomainWeightsSnapshot()

        return self._parse_snapshot(data)

    def _load_json_fallback(self) -> DomainWeightsSnapshot:
        """Load weights from JSON fallback file."""
        try:
            text = self._json_fallback.read_text(encoding="utf-8")
            data = json.loads(text)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                "domain_weights_load_failed", file=str(self._json_fallback), error=str(e)
            )
            return DomainWeightsSnapshot()

        return self._parse_snapshot(data)

    def _parse_snapshot(self, data: dict[str, Any]) -> DomainWeightsSnapshot:
        """Parse raw dict into a DomainWeightsSnapshot with migration support."""
        # Handle schema migrations
        version = data.get("version", 1)
        if version < 1:
            logger.warning("domain_weights_unknown_version", version=version)

        # Parse technical weights
        technical: dict[str, DomainWeightEntry] = {}
        for domain, entry_data in data.get("technical", {}).items():
            if isinstance(entry_data, dict):
                technical[domain] = DomainWeightEntry(domain=domain, **entry_data)
            else:
                # Legacy: just a weight value
                technical[domain] = DomainWeightEntry(domain=domain, weight=float(entry_data))

        # Parse business weights
        business: dict[str, DomainWeightEntry] = {}
        for domain, entry_data in data.get("business", {}).items():
            if isinstance(entry_data, dict):
                business[domain] = DomainWeightEntry(domain=domain, **entry_data)
            else:
                business[domain] = DomainWeightEntry(domain=domain, weight=float(entry_data))

        return DomainWeightsSnapshot(
            technical=technical,
            business=business,
            timestamp=data.get("timestamp", _utc_now_iso()),
            version=version,
        )
