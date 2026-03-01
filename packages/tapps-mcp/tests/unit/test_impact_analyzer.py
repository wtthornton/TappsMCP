"""Tests for project.impact_analyzer -- blast-radius detection."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.impact_analyzer import analyze_impact, build_import_graph
from tapps_mcp.project.models import ImpactReport


def _write_file(path: Path, content: str) -> None:
    """Helper: ensure parent dirs exist, then write *content*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestAnalyzeImpactIsolated:
    """Cases where a changed file has no downstream dependents."""

    def test_no_impact_isolated_file(self, tmp_path: Path) -> None:
        """A file with no imports pointing to it has total_affected=0, severity=low."""
        _write_file(tmp_path / "src" / "__init__.py", "")
        _write_file(tmp_path / "src" / "models.py", "x = 1\n")

        report: ImpactReport = analyze_impact(
            file_path=tmp_path / "src" / "models.py",
            project_root=tmp_path,
        )

        assert report.total_affected == 0
        assert report.severity == "low"
        assert report.direct_dependents == []
        assert report.transitive_dependents == []
        assert report.test_files == []

    def test_outside_project_root(self, tmp_path: Path) -> None:
        """File not under project_root returns low severity with a specific message."""
        _write_file(tmp_path / "project" / "app.py", "x = 1\n")

        # The changed file is outside `project/`
        outside = tmp_path / "other" / "stray.py"
        _write_file(outside, "y = 2\n")

        report = analyze_impact(
            file_path=outside,
            project_root=tmp_path / "project",
        )

        assert report.severity == "low"
        assert any("outside" in r.lower() for r in report.recommendations)


class TestDirectDependents:
    """Cases where files directly import the changed file."""

    def test_direct_dependent(self, tmp_path: Path) -> None:
        """File A imports file B. Changing B causes A to appear as a direct dependent."""
        _write_file(tmp_path / "src" / "__init__.py", "")
        _write_file(tmp_path / "src" / "models.py", "x = 1\n")
        _write_file(
            tmp_path / "src" / "service.py",
            "from src.models import x\n",
        )

        report = analyze_impact(
            file_path=tmp_path / "src" / "models.py",
            project_root=tmp_path,
        )

        direct_paths = [d.file_path for d in report.direct_dependents]
        assert str(tmp_path / "src" / "service.py") in direct_paths
        assert report.total_affected >= 1

    def test_test_file_categorized_separately(self, tmp_path: Path) -> None:
        """test_*.py that imports the changed file is in test_files, not direct."""
        _write_file(tmp_path / "src" / "__init__.py", "")
        _write_file(tmp_path / "src" / "models.py", "x = 1\n")
        _write_file(tmp_path / "tests" / "__init__.py", "")
        _write_file(
            tmp_path / "tests" / "test_models.py",
            "from src.models import x\n",
        )

        report = analyze_impact(
            file_path=tmp_path / "src" / "models.py",
            project_root=tmp_path,
        )

        test_paths = [t.file_path for t in report.test_files]
        direct_paths = [d.file_path for d in report.direct_dependents]

        assert str(tmp_path / "tests" / "test_models.py") in test_paths
        assert str(tmp_path / "tests" / "test_models.py") not in direct_paths


class TestTransitiveDependents:
    """Cases with multi-hop import chains."""

    def test_transitive_dependent(self, tmp_path: Path) -> None:
        """C imports B, B imports A. Changing A -> B is direct, C is transitive."""
        _write_file(tmp_path / "pkg" / "__init__.py", "")
        _write_file(tmp_path / "pkg" / "a.py", "val = 42\n")
        _write_file(
            tmp_path / "pkg" / "b.py",
            "from pkg.a import val\n",
        )
        _write_file(
            tmp_path / "pkg" / "c.py",
            "from pkg.b import val\n",
        )

        report = analyze_impact(
            file_path=tmp_path / "pkg" / "a.py",
            project_root=tmp_path,
        )

        direct_paths = [d.file_path for d in report.direct_dependents]
        transitive_paths = [t.file_path for t in report.transitive_dependents]

        assert str(tmp_path / "pkg" / "b.py") in direct_paths
        assert str(tmp_path / "pkg" / "c.py") in transitive_paths
        assert report.total_affected >= 2


class TestSeverity:
    """Severity assessment logic."""

    def test_removed_file_severity(self, tmp_path: Path) -> None:
        """change_type='removed' with dependents -> severity=critical."""
        _write_file(tmp_path / "lib" / "__init__.py", "")
        _write_file(tmp_path / "lib" / "core.py", "x = 1\n")
        _write_file(
            tmp_path / "lib" / "consumer.py",
            "from lib.core import x\n",
        )

        report = analyze_impact(
            file_path=tmp_path / "lib" / "core.py",
            project_root=tmp_path,
            change_type="removed",
        )

        assert report.severity == "critical"
        assert report.change_type == "removed"


class TestModuleMapping:
    """Edge cases in module-name resolution."""

    def test_module_for_file_init(self, tmp_path: Path) -> None:
        """__init__.py maps to the package name, not 'package.__init__'."""
        _write_file(tmp_path / "mypkg" / "__init__.py", "FLAG = True\n")
        _write_file(
            tmp_path / "mypkg" / "sub.py",
            "from mypkg import FLAG\n",
        )

        report = analyze_impact(
            file_path=tmp_path / "mypkg" / "__init__.py",
            project_root=tmp_path,
        )

        # sub.py imports 'mypkg' which is the module name for __init__.py
        direct_paths = [d.file_path for d in report.direct_dependents]
        assert str(tmp_path / "mypkg" / "sub.py") in direct_paths


class TestRecommendations:
    """Recommendation text generation."""

    def test_recommendations_with_tests(self, tmp_path: Path) -> None:
        """When tests are affected, a recommendation mentions re-running them."""
        _write_file(tmp_path / "app" / "__init__.py", "")
        _write_file(tmp_path / "app" / "logic.py", "y = 10\n")
        _write_file(tmp_path / "tests" / "__init__.py", "")
        _write_file(
            tmp_path / "tests" / "test_logic.py",
            "from app.logic import y\n",
        )

        report = analyze_impact(
            file_path=tmp_path / "app" / "logic.py",
            project_root=tmp_path,
        )

        assert report.test_files, "Expected at least one test file"
        recs_lower = " ".join(report.recommendations).lower()
        assert "re-run" in recs_lower or "rerun" in recs_lower


class TestBuildImportGraph:
    """Tests for the public build_import_graph helper."""

    def test_returns_graph(self, tmp_path: Path) -> None:
        """build_import_graph returns a dict mapping modules to importing files."""
        _write_file(tmp_path / "pkg" / "__init__.py", "")
        _write_file(tmp_path / "pkg" / "core.py", "x = 1\n")
        _write_file(
            tmp_path / "pkg" / "consumer.py",
            "from pkg.core import x\n",
        )

        graph = build_import_graph(tmp_path)

        assert isinstance(graph, dict)
        assert "pkg.core" in graph
        assert str(tmp_path / "pkg" / "consumer.py") in graph["pkg.core"]

    def test_graph_reuse_gives_same_results(self, tmp_path: Path) -> None:
        """Passing a prebuilt graph to analyze_impact produces the same results."""
        _write_file(tmp_path / "pkg" / "__init__.py", "")
        _write_file(tmp_path / "pkg" / "core.py", "x = 1\n")
        _write_file(
            tmp_path / "pkg" / "consumer.py",
            "from pkg.core import x\n",
        )

        # Without prebuilt graph
        report_auto = analyze_impact(
            file_path=tmp_path / "pkg" / "core.py",
            project_root=tmp_path,
        )

        # With prebuilt graph
        graph = build_import_graph(tmp_path)
        report_reuse = analyze_impact(
            file_path=tmp_path / "pkg" / "core.py",
            project_root=tmp_path,
            graph=graph,
        )

        assert report_auto.severity == report_reuse.severity
        assert report_auto.total_affected == report_reuse.total_affected
        assert len(report_auto.direct_dependents) == len(report_reuse.direct_dependents)


class TestSkipDirs:
    """Files in ignored directories must be excluded."""

    def test_skip_dirs_respected(self, tmp_path: Path) -> None:
        """Files inside .venv/ are not included as dependents."""
        _write_file(tmp_path / "pkg" / "__init__.py", "")
        _write_file(tmp_path / "pkg" / "core.py", "z = 1\n")

        # This file is inside .venv and should be skipped
        _write_file(
            tmp_path / ".venv" / "lib" / "wrapper.py",
            "from pkg.core import z\n",
        )
        # This file is a normal dependent
        _write_file(
            tmp_path / "pkg" / "consumer.py",
            "from pkg.core import z\n",
        )

        report = analyze_impact(
            file_path=tmp_path / "pkg" / "core.py",
            project_root=tmp_path,
        )

        all_paths = (
            [d.file_path for d in report.direct_dependents]
            + [t.file_path for t in report.transitive_dependents]
            + [t.file_path for t in report.test_files]
        )

        # The .venv file must NOT appear
        for p in all_paths:
            assert ".venv" not in p, f"Unexpected .venv file in results: {p}"

        # The normal consumer SHOULD appear
        assert str(tmp_path / "pkg" / "consumer.py") in all_paths
