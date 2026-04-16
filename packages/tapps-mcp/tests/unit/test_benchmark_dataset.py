"""Tests for benchmark dataset loading (Epic 30, Story 2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.benchmark.dataset import (
    DatasetLoader,
    DatasetLoadError,
    DatasetNotFoundError,
    DependencyMissingError,
    _load_from_parquet,
    _map_to_instance,
)
from tapps_mcp.benchmark.models import BenchmarkConfig, BenchmarkInstance

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_ROW: dict[str, Any] = {
    "instance_id": "test-001",
    "repo": "owner/repo",
    "problem_description": "Fix the bug.",
    "clean_pr_patch": "--- a/f.py\n+++ b/f.py\n",
    "test_commands": ["pytest tests/"],
    "test_file_names": ["tests/test_foo.py"],
    "test_file_contents": {"tests/test_foo.py": "def test(): pass"},
    "docker_image": "python:3.12",
}


def _make_instance(**overrides: Any) -> BenchmarkInstance:
    """Build a BenchmarkInstance with sensible defaults."""
    fields: dict[str, Any] = {**_REQUIRED_ROW, **overrides}
    return BenchmarkInstance(**fields)


def _make_config(**overrides: Any) -> BenchmarkConfig:
    """Build a BenchmarkConfig with sensible defaults."""
    defaults: dict[str, Any] = {
        "dataset_name": "eth-sri/agentbench",
        "subset_size": 0,
        "random_seed": 42,
    }
    defaults.update(overrides)
    return BenchmarkConfig(**defaults)


# ---------------------------------------------------------------------------
# sample_subset
# ---------------------------------------------------------------------------


class TestSampleSubset:
    """Tests for DatasetLoader.sample_subset."""

    def test_deterministic(self) -> None:
        """Same seed produces the same sample."""
        instances = [_make_instance(instance_id=f"i-{i}") for i in range(20)]
        loader = DatasetLoader(_make_config())
        result_a = loader.sample_subset(instances, 5, seed=42)
        result_b = loader.sample_subset(instances, 5, seed=42)
        assert [r.instance_id for r in result_a] == [r.instance_id for r in result_b]

    def test_different_seed_different_result(self) -> None:
        """Different seeds produce different samples."""
        instances = [_make_instance(instance_id=f"i-{i}") for i in range(20)]
        loader = DatasetLoader(_make_config())
        result_a = loader.sample_subset(instances, 5, seed=42)
        result_b = loader.sample_subset(instances, 5, seed=99)
        ids_a = [r.instance_id for r in result_a]
        ids_b = [r.instance_id for r in result_b]
        assert ids_a != ids_b

    def test_returns_all_when_n_exceeds_size(self) -> None:
        """When n >= len(instances), all are returned."""
        instances = [_make_instance(instance_id=f"i-{i}") for i in range(3)]
        loader = DatasetLoader(_make_config())
        result = loader.sample_subset(instances, 10, seed=42)
        assert len(result) == 3
        # Should be a copy, not the same object
        assert result is not instances

    def test_returns_all_when_n_is_zero(self) -> None:
        """When n=0, all instances are returned."""
        instances = [_make_instance(instance_id=f"i-{i}") for i in range(5)]
        loader = DatasetLoader(_make_config())
        result = loader.sample_subset(instances, 0, seed=42)
        assert len(result) == 5


# ---------------------------------------------------------------------------
# filter_by_repo
# ---------------------------------------------------------------------------


class TestFilterByRepo:
    """Tests for DatasetLoader.filter_by_repo."""

    def test_case_insensitive(self) -> None:
        """Filtering is case-insensitive."""
        instances = [
            _make_instance(instance_id="a", repo="Owner/Repo"),
            _make_instance(instance_id="b", repo="other/lib"),
        ]
        loader = DatasetLoader(_make_config())
        result = loader.filter_by_repo(instances, ["owner/repo"])
        assert len(result) == 1
        assert result[0].instance_id == "a"

    def test_no_matches(self) -> None:
        """Returns empty list when no repos match."""
        instances = [
            _make_instance(instance_id="a", repo="owner/repo"),
        ]
        loader = DatasetLoader(_make_config())
        result = loader.filter_by_repo(instances, ["nonexistent/lib"])
        assert result == []


# ---------------------------------------------------------------------------
# _map_to_instance
# ---------------------------------------------------------------------------


class TestMapToInstance:
    """Tests for the _map_to_instance helper."""

    def test_all_fields(self) -> None:
        """Mapping with all fields present."""
        row: dict[str, Any] = {
            "instance_id": "test-001",
            "repo": "owner/repo",
            "problem_description": "Fix the bug.",
            "clean_pr_patch": "--- a/f.py\n+++ b/f.py\n",
            "test_commands": ["pytest tests/"],
            "test_file_names": ["tests/test_foo.py"],
            "test_file_contents": {
                "tests/test_foo.py": "def test(): pass",
            },
            "docker_image": "python:3.12",
            "setup_commands": ["pip install -e ."],
            "key_files": ["src/main.py"],
            "risk_factors": ["flaky tests"],
            "rationale": "Complex refactor.",
        }
        inst = _map_to_instance(row)
        assert inst.instance_id == "test-001"
        assert inst.repo == "owner/repo"
        assert inst.setup_commands == ["pip install -e ."]
        assert inst.risk_factors == ["flaky tests"]
        assert inst.rationale == "Complex refactor."

    def test_missing_optional_fields(self) -> None:
        """Only required fields are needed."""
        inst = _map_to_instance(_REQUIRED_ROW)
        assert inst.instance_id == "test-001"
        assert inst.setup_commands == []
        assert inst.key_files == []
        assert inst.risk_factors is None
        assert inst.rationale is None

    def test_json_string_lists(self) -> None:
        """List fields stored as JSON strings are parsed."""
        row = {
            **_REQUIRED_ROW,
            "test_commands": '["pytest", "mypy src/"]',
            "setup_commands": '["pip install -e ."]',
        }
        inst = _map_to_instance(row)
        assert inst.test_commands == ["pytest", "mypy src/"]
        assert inst.setup_commands == ["pip install -e ."]

    def test_json_string_dict(self) -> None:
        """Dict fields stored as JSON strings are parsed."""
        contents = {"test.py": "def test(): pass"}
        row = {
            **_REQUIRED_ROW,
            "test_file_contents": json.dumps(contents),
        }
        inst = _map_to_instance(row)
        assert inst.test_file_contents == contents

    def test_column_aliases(self) -> None:
        """Alternate column names resolve to canonical names."""
        row: dict[str, Any] = {
            "instance_id": "alias-test",
            "repository": "owner/repo",
            "problem_statement": "Fix it.",
            "gold_patch": "diff content",
            "test_commands": ["pytest"],
            "test_file_names": ["test.py"],
            "test_file_contents": {"test.py": "pass"},
            "image": "python:3.12",
        }
        inst = _map_to_instance(row)
        assert inst.repo == "owner/repo"
        assert inst.problem_description == "Fix it."
        assert inst.clean_pr_patch == "diff content"
        assert inst.docker_image == "python:3.12"

    def test_unknown_fields_ignored(self) -> None:
        """Extra columns not in the model are silently dropped."""
        row = {
            **_REQUIRED_ROW,
            "some_extra_column": "should be ignored",
            "another_unknown": 42,
        }
        inst = _map_to_instance(row)
        assert inst.instance_id == "test-001"

    def test_unparseable_json_list_wraps(self) -> None:
        """Non-JSON string in list field wraps to single item."""
        row = {
            **_REQUIRED_ROW,
            "test_commands": "just a plain string",
        }
        inst = _map_to_instance(row)
        assert inst.test_commands == ["just a plain string"]

    def test_unparseable_json_dict_becomes_empty(self) -> None:
        """Non-JSON string in dict field becomes empty dict."""
        row = {
            **_REQUIRED_ROW,
            "test_file_contents": "not valid json",
        }
        inst = _map_to_instance(row)
        assert inst.test_file_contents == {}


# ---------------------------------------------------------------------------
# _load_from_json / _load_from_jsonl (via DatasetLoader.load)
# ---------------------------------------------------------------------------


class TestLoadJsonFile:
    """Tests for JSON file loading."""

    @pytest.mark.asyncio()
    async def test_load_json_file(self, tmp_path: Path) -> None:
        """Loading from a .json file works."""
        data = [_REQUIRED_ROW]
        json_file = tmp_path / "data.json"
        json_file.write_text(json.dumps(data), encoding="utf-8")
        config = _make_config(dataset_name=str(json_file), subset_size=0)
        loader = DatasetLoader(config)
        instances = await loader.load()
        assert len(instances) == 1
        assert instances[0].instance_id == "test-001"

    @pytest.mark.asyncio()
    async def test_load_jsonl_file(self, tmp_path: Path) -> None:
        """Loading from a .jsonl file works."""
        rows = [{**_REQUIRED_ROW, "instance_id": f"jsonl-{i}"} for i in range(3)]
        jsonl_file = tmp_path / "data.jsonl"
        lines = [json.dumps(r) for r in rows]
        jsonl_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        config = _make_config(dataset_name=str(jsonl_file), subset_size=0)
        loader = DatasetLoader(config)
        instances = await loader.load()
        assert len(instances) == 3
        assert instances[0].instance_id == "jsonl-0"

    @pytest.mark.asyncio()
    async def test_json_not_array_raises(self, tmp_path: Path) -> None:
        """JSON file that is not an array raises DatasetLoadError."""
        json_file = tmp_path / "bad.json"
        json_file.write_text('{"key": "value"}', encoding="utf-8")
        config = _make_config(dataset_name=str(json_file), subset_size=0)
        loader = DatasetLoader(config)
        with pytest.raises(DatasetLoadError, match="Expected JSON array"):
            await loader.load()


# ---------------------------------------------------------------------------
# Parquet dispatch
# ---------------------------------------------------------------------------


class TestLoadParquet:
    """Tests for Parquet file dispatch."""

    @pytest.mark.asyncio()
    async def test_dispatches_to_parquet(self, tmp_path: Path) -> None:
        """A .parquet extension dispatches to parquet loader."""
        pq_file = tmp_path / "data.parquet"
        pq_file.touch()

        config = _make_config(dataset_name=str(pq_file), subset_size=0)
        loader = DatasetLoader(config)

        with patch(
            "tapps_mcp.benchmark.dataset._load_from_parquet",
            return_value=[_REQUIRED_ROW],
        ) as mock_pq:
            instances = await loader.load()
            mock_pq.assert_called_once()
            assert len(instances) == 1

    def test_parquet_file_not_found(self, tmp_path: Path) -> None:
        """DatasetNotFoundError for missing parquet file."""
        missing = tmp_path / "nonexistent.parquet"
        with pytest.raises(DatasetNotFoundError, match="not found"):
            _load_from_parquet(missing)

    def test_parquet_deps_missing(self, tmp_path: Path) -> None:
        """DependencyMissingError when no parquet library."""
        pq_file = tmp_path / "data.parquet"
        pq_file.write_bytes(b"PAR1fake")

        with (
            patch.dict(
                "sys.modules",
                {
                    "pyarrow": None,
                    "pyarrow.parquet": None,
                    "pandas": None,
                },
            ),
            pytest.raises(DependencyMissingError),
        ):
            _load_from_parquet(pq_file)


# ---------------------------------------------------------------------------
# HuggingFace dispatch
# ---------------------------------------------------------------------------


class TestLoadHuggingFace:
    """Tests for HuggingFace loading."""

    @pytest.mark.asyncio()
    async def test_huggingface_not_installed(self) -> None:
        """DependencyMissingError when datasets not importable."""
        config = _make_config(dataset_name="eth-sri/agentbench", subset_size=0)
        loader = DatasetLoader(config)

        with (
            patch.dict(sys.modules, {"datasets": None}),
            pytest.raises(DependencyMissingError),
        ):
            await loader.load()

    @pytest.mark.asyncio()
    async def test_huggingface_not_found(self) -> None:
        """DatasetNotFoundError when fetch fails."""
        mock_datasets = MagicMock()
        mock_datasets.load_dataset.side_effect = Exception("Dataset not found")

        config = _make_config(dataset_name="nonexistent/dataset", subset_size=0)
        loader = DatasetLoader(config)

        with (
            patch.dict(sys.modules, {"datasets": mock_datasets}),
            pytest.raises(DatasetNotFoundError),
        ):
            await loader.load()


# ---------------------------------------------------------------------------
# Load with subset sampling
# ---------------------------------------------------------------------------


class TestLoadWithSubset:
    """Tests for load() with subset sampling."""

    @pytest.mark.asyncio()
    async def test_subset_applied(self, tmp_path: Path) -> None:
        """When subset_size < total, sampling is applied."""
        rows = [{**_REQUIRED_ROW, "instance_id": f"sub-{i}"} for i in range(10)]
        json_file = tmp_path / "data.json"
        json_file.write_text(json.dumps(rows), encoding="utf-8")
        config = _make_config(
            dataset_name=str(json_file),
            subset_size=3,
            random_seed=42,
        )
        loader = DatasetLoader(config)
        instances = await loader.load()
        assert len(instances) == 3

    @pytest.mark.asyncio()
    async def test_subset_not_applied_when_larger(self, tmp_path: Path) -> None:
        """When subset_size >= total, no sampling occurs."""
        rows = [{**_REQUIRED_ROW, "instance_id": f"eq-{i}"} for i in range(3)]
        json_file = tmp_path / "data.json"
        json_file.write_text(json.dumps(rows), encoding="utf-8")
        config = _make_config(
            dataset_name=str(json_file),
            subset_size=5,
            random_seed=42,
        )
        loader = DatasetLoader(config)
        instances = await loader.load()
        assert len(instances) == 3
