"""Dataset loader for AGENTBench benchmark instances.

Loads benchmark instances from HuggingFace datasets or local
Parquet/JSON/JSONL files, with support for deterministic sampling,
repository filtering, and column-name aliasing.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, cast

import structlog

from tapps_mcp.benchmark.models import BenchmarkConfig, BenchmarkInstance

logger = structlog.get_logger(__name__)

__all__ = [
    "DatasetLoadError",
    "DatasetLoader",
    "DatasetNotFoundError",
    "DependencyMissingError",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DatasetLoadError(Exception):
    """Raised when a dataset cannot be loaded."""


class DatasetNotFoundError(DatasetLoadError):
    """Raised when the specified dataset does not exist."""


class DependencyMissingError(DatasetLoadError):
    """Raised when a required optional dependency is not installed."""


# ---------------------------------------------------------------------------
# Column aliases  (alternate name -> canonical model field name)
# ---------------------------------------------------------------------------

_COLUMN_ALIASES: dict[str, str] = {
    "id": "instance_id",
    "instance": "instance_id",
    "repository": "repo",
    "repo_name": "repo",
    "problem_statement": "problem_description",
    "problem": "problem_description",
    "patch": "clean_pr_patch",
    "gold_patch": "clean_pr_patch",
    "image": "docker_image",
    "tests": "test_commands",
}

# Fields that may be stored as JSON-encoded strings in datasets.
_LIST_FIELDS: tuple[str, ...] = (
    "test_commands",
    "test_file_names",
    "setup_commands",
    "key_files",
    "risk_factors",
)

_DICT_FIELDS: tuple[str, ...] = ("test_file_contents",)


# ---------------------------------------------------------------------------
# Loader class
# ---------------------------------------------------------------------------


class DatasetLoader:
    """Load benchmark instances from HuggingFace or local files."""

    def __init__(self, config: BenchmarkConfig) -> None:
        self._config = config

    async def load(self) -> list[BenchmarkInstance]:
        """Load benchmark instances based on config.

        Dispatches to the appropriate backend based on the dataset
        name: local file paths are detected by existence and
        extension; everything else is treated as a HuggingFace
        dataset identifier.

        Returns:
            Loaded (and optionally sampled) list of instances.

        Raises:
            DatasetLoadError: On any loading failure.
            DatasetNotFoundError: When the dataset is not found.
            DependencyMissingError: When a required library is absent.
        """
        dataset_name = self._config.dataset_name
        path = Path(dataset_name)

        if path.exists() and path.suffix in (".parquet", ".pq"):
            raw = _load_from_parquet(path)
        elif path.exists() and path.suffix == ".json":
            raw = _load_from_json(path)
        elif path.exists() and path.suffix == ".jsonl":
            raw = _load_from_jsonl(path)
        else:
            raw = _load_from_huggingface(
                dataset_name,
                revision=self._config.dataset_revision,
            )

        instances = [_map_to_instance(row) for row in raw]
        logger.info(
            "dataset_loaded",
            source=dataset_name,
            total_instances=len(instances),
        )

        # Apply subset sampling if configured
        subset = self._config.subset_size
        if subset > 0 and len(instances) > subset:
            instances = self.sample_subset(instances, subset, self._config.random_seed)
        return instances

    def sample_subset(
        self,
        instances: list[BenchmarkInstance],
        n: int,
        seed: int | None = None,
    ) -> list[BenchmarkInstance]:
        """Deterministic random sampling of instances.

        Args:
            instances: Full list of instances.
            n: Number of instances to sample.
            seed: Random seed for reproducibility.

        Returns:
            A sampled subset, or the original list when *n* is
            zero or exceeds the collection size.
        """
        if n <= 0 or n >= len(instances):
            return list(instances)
        rng = random.Random(seed)
        return rng.sample(instances, n)

    def filter_by_repo(
        self,
        instances: list[BenchmarkInstance],
        repo_names: list[str],
    ) -> list[BenchmarkInstance]:
        """Filter instances to specific repositories.

        Comparison is case-insensitive.

        Args:
            instances: Full list of instances.
            repo_names: Repository names to keep.

        Returns:
            Filtered list containing only matching repos.
        """
        lower_names = {name.lower() for name in repo_names}
        return [inst for inst in instances if inst.repo.lower() in lower_names]


# ---------------------------------------------------------------------------
# Backend loaders
# ---------------------------------------------------------------------------


def _load_from_huggingface(
    dataset_name: str,
    revision: str | None = None,
) -> list[dict[str, Any]]:
    """Load dataset from HuggingFace datasets library.

    Args:
        dataset_name: HuggingFace dataset identifier.
        revision: Optional commit hash or tag to pin for reproducibility.
            When None, the latest revision is fetched (caller accepts
            supply-chain risk).

    Raises:
        DependencyMissingError: If ``datasets`` is not installed.
        DatasetNotFoundError: If the dataset cannot be fetched.
    """
    try:
        from datasets import (
            load_dataset,
        )
    except ImportError as exc:
        msg = (
            "HuggingFace 'datasets' library is required "
            "to load from HuggingFace Hub. "
            "Install with: uv add datasets"
        )
        raise DependencyMissingError(msg) from exc

    try:
        ds = load_dataset(  # nosec B615 — revision pinning is caller-controlled
            dataset_name,
            split="test",
            revision=revision,
        )
        return [dict(row) for row in ds]
    except Exception as exc:
        msg = f"Failed to load dataset '{dataset_name}' from HuggingFace: {exc}"
        raise DatasetNotFoundError(msg) from exc


def _load_from_parquet(path: Path) -> list[dict[str, Any]]:
    """Load dataset from a local Parquet file.

    Tries ``pyarrow`` first, then falls back to ``pandas``.

    Raises:
        DatasetNotFoundError: If the file does not exist.
        DependencyMissingError: If neither library is installed.
    """
    if not path.exists():
        msg = f"Parquet file not found: {path}"
        raise DatasetNotFoundError(msg)

    try:
        import pyarrow.parquet as pq

        table = pq.read_table(str(path))
        col_dict: dict[str, list[Any]] = table.to_pydict()
        if not col_dict:
            return []
        n_rows = len(next(iter(col_dict.values())))
        return [{col: vals[i] for col, vals in col_dict.items()} for i in range(n_rows)]
    except ImportError:
        pass

    try:
        import pandas as pd

        df = pd.read_parquet(path)
        return cast("list[dict[str, Any]]", df.to_dict(orient="records"))
    except ImportError as exc:
        msg = (
            "Either 'pyarrow' or 'pandas' is required to "
            "load Parquet files. "
            "Install with: uv add pyarrow  OR  uv add pandas"
        )
        raise DependencyMissingError(msg) from exc


def _load_from_json(path: Path) -> list[dict[str, Any]]:
    """Load dataset from a local JSON file.

    Expects a top-level JSON array of objects.

    Raises:
        DatasetNotFoundError: If the file does not exist.
        DatasetLoadError: If the JSON is not a list.
    """
    if not path.exists():
        msg = f"JSON file not found: {path}"
        raise DatasetNotFoundError(msg)

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    msg = f"Expected JSON array, got {type(data).__name__}"
    raise DatasetLoadError(msg)


def _load_from_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load dataset from JSONL (one JSON object per line).

    Raises:
        DatasetNotFoundError: If the file does not exist.
    """
    if not path.exists():
        msg = f"JSONL file not found: {path}"
        raise DatasetNotFoundError(msg)

    results: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                results.append(json.loads(stripped))
    return results


# ---------------------------------------------------------------------------
# Row mapping
# ---------------------------------------------------------------------------


def _map_to_instance(
    row: dict[str, Any],
) -> BenchmarkInstance:
    """Map a raw dataset row to a ``BenchmarkInstance``.

    Applies column aliases, parses JSON-encoded list/dict fields,
    and filters to known model fields before construction.
    """
    # Apply column aliases so alternate names resolve to canonical.
    mapped: dict[str, Any] = {}
    for key, value in row.items():
        canonical = _COLUMN_ALIASES.get(key, key)
        mapped[canonical] = value

    # Parse list fields that may be stored as JSON strings.
    for list_field in _LIST_FIELDS:
        val = mapped.get(list_field)
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    mapped[list_field] = parsed
                else:
                    mapped[list_field] = [val] if val else []
            except (json.JSONDecodeError, TypeError):
                mapped[list_field] = [val] if val else []

    # Parse dict fields that may be stored as JSON strings.
    for dict_field in _DICT_FIELDS:
        val = mapped.get(dict_field)
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    mapped[dict_field] = parsed
                else:
                    mapped[dict_field] = {}
            except (json.JSONDecodeError, TypeError):
                mapped[dict_field] = {}

    # Filter to only fields known by the model.
    known_fields = set(BenchmarkInstance.model_fields.keys())
    filtered = {k: v for k, v in mapped.items() if k in known_fields}

    return BenchmarkInstance(**filtered)
