"""Unit tests for the architectural pattern classifier (STORY-100.1)."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest

from docs_mcp.analyzers.dependency import ImportEdge, ImportGraph
from docs_mcp.analyzers.models import ModuleMap, ModuleNode
from docs_mcp.analyzers.pattern import PatternClassifier


def _make_map(package_names: list[str], *, total_packages: int | None = None) -> ModuleMap:
    tree = [
        ModuleNode(name=name, path=f"src/{name}", is_package=True)
        for name in package_names
    ]
    return ModuleMap(
        project_root="/tmp/x",
        project_name="x",
        module_tree=tree,
        total_packages=total_packages if total_packages is not None else len(package_names),
        total_modules=len(package_names),
    )


def _make_graph(
    externals: dict[str, list[str]] | None = None,
    edges: list[tuple[str, str]] | None = None,
) -> ImportGraph:
    return ImportGraph(
        edges=[ImportEdge(source=s, target=t) for s, t in (edges or [])],
        external_imports=externals or {},
    )


class TestClassifier:
    def test_hexagonal_when_ports_and_adapters_present(self, tmp_path: Path) -> None:
        mm = _make_map(["core", "ports", "adapters", "domain"])
        result = PatternClassifier().classify(tmp_path, module_map=mm)
        assert result.archetype == "hexagonal"
        assert result.confidence >= 0.7
        assert any("ports" in e for e in result.evidence)

    def test_layered_when_canonical_layers_present(self, tmp_path: Path) -> None:
        mm = _make_map(["api", "services", "repositories", "models"])
        result = PatternClassifier().classify(tmp_path, module_map=mm)
        assert result.archetype == "layered"
        assert result.confidence >= 0.7

    def test_event_driven_when_broker_libs_imported(self, tmp_path: Path) -> None:
        mm = _make_map(["app", "handlers"])
        graph = _make_graph(externals={"kafka": ["app"], "celery": ["handlers"]})
        result = PatternClassifier().classify(tmp_path, module_map=mm, import_graph=graph)
        assert result.archetype == "event_driven"
        assert result.confidence >= 0.5

    def test_redis_alone_does_not_trigger_event_driven(self, tmp_path: Path) -> None:
        mm = _make_map(["app"])
        graph = _make_graph(externals={"redis": ["app"]})
        result = PatternClassifier().classify(tmp_path, module_map=mm, import_graph=graph)
        assert result.archetype != "event_driven"

    def test_monolith_for_tiny_projects(self, tmp_path: Path) -> None:
        mm = _make_map(["app"], total_packages=1)
        result = PatternClassifier().classify(tmp_path, module_map=mm)
        assert result.archetype == "monolith"

    def test_unknown_when_no_signal(self, tmp_path: Path) -> None:
        result = PatternClassifier().classify(tmp_path)
        assert result.archetype == "unknown"
        assert result.confidence == 0.0

    def test_pipeline_when_stage_packages_and_acyclic(self, tmp_path: Path) -> None:
        mm = _make_map(["extract", "transform", "load"])
        graph = _make_graph(edges=[("extract", "transform"), ("transform", "load")])
        result = PatternClassifier().classify(tmp_path, module_map=mm, import_graph=graph)
        assert result.archetype == "pipeline"

    def test_alternatives_ranked_when_multiple_signals(self, tmp_path: Path) -> None:
        mm = _make_map(["api", "services", "repositories", "models", "ports", "adapters"])
        result = PatternClassifier().classify(tmp_path, module_map=mm)
        # Hexagonal wins over layered due to higher score.
        assert result.archetype in {"hexagonal", "layered"}
        assert result.alternatives  # non-empty ranking tail

    def test_microservice_when_multiple_pyproject_in_subdirs(self, tmp_path: Path) -> None:
        (tmp_path / "svc_a").mkdir()
        (tmp_path / "svc_a" / "pyproject.toml").write_text("[project]\nname='a'\n")
        (tmp_path / "svc_b").mkdir()
        (tmp_path / "svc_b" / "pyproject.toml").write_text("[project]\nname='b'\n")
        result = PatternClassifier().classify(tmp_path)
        assert result.archetype == "microservice"


@pytest.mark.parametrize(
    "packages,expected",
    [
        (["ports", "adapters", "core"], "hexagonal"),
        (["api", "services", "repositories", "models"], "layered"),
        (["extract", "transform", "load"], "pipeline"),
    ],
)
def test_parametrized_archetypes(
    packages: list[str], expected: str, tmp_path: Path
) -> None:
    mm = _make_map(packages)
    graph = _make_graph(edges=list(pairwise(packages)))
    result = PatternClassifier().classify(tmp_path, module_map=mm, import_graph=graph)
    assert result.archetype == expected
