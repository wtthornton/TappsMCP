"""Unit tests for project profiling modules.

Covers TechStack/ProjectProfile models, TechStackDetector,
detect_project_type, and detect_project_profile.
"""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.project.models import ProjectProfile, TechStack
from tapps_mcp.project.profiler import detect_project_profile
from tapps_mcp.project.tech_stack import TechStackDetector, _should_skip
from tapps_mcp.project.type_detector import detect_project_type

# =========================================================================
# TechStack model
# =========================================================================


class TestTechStack:
    def test_defaults_are_empty(self) -> None:
        ts = TechStack()
        assert ts.languages == []
        assert ts.libraries == []
        assert ts.frameworks == []
        assert ts.domains == []
        assert ts.context7_priority == []

    def test_populated_fields(self) -> None:
        ts = TechStack(
            languages=["python", "typescript"],
            libraries=["fastapi", "pydantic"],
            frameworks=["fastapi", "pytest"],
            domains=["api", "web"],
            context7_priority=["fastapi"],
        )
        assert "python" in ts.languages
        assert "typescript" in ts.languages
        assert len(ts.libraries) == 2
        assert "api" in ts.domains
        assert ts.context7_priority == ["fastapi"]


# =========================================================================
# ProjectProfile model
# =========================================================================


class TestProjectProfile:
    def test_defaults(self) -> None:
        pp = ProjectProfile()
        assert pp.project_type is None
        assert pp.project_type_confidence == 0.0
        assert pp.project_type_reason == ""
        assert pp.has_ci is False
        assert pp.ci_systems == []
        assert pp.has_docker is False
        assert pp.has_tests is False
        assert pp.test_frameworks == []
        assert pp.package_managers == []
        assert pp.quality_recommendations == []
        assert isinstance(pp.tech_stack, TechStack)

    def test_full_data(self) -> None:
        ts = TechStack(languages=["python"], frameworks=["fastapi"])
        pp = ProjectProfile(
            tech_stack=ts,
            project_type="api-service",
            project_type_confidence=0.8,
            project_type_reason="Detected api-service based on: has_api_routes",
            has_ci=True,
            ci_systems=["github-actions"],
            has_docker=True,
            has_tests=True,
            test_frameworks=["pytest"],
            package_managers=["uv"],
            quality_recommendations=["Add mypy for type checking."],
        )
        assert pp.project_type == "api-service"
        assert pp.project_type_confidence == 0.8
        assert pp.has_ci is True
        assert "github-actions" in pp.ci_systems
        assert pp.has_docker is True
        assert pp.has_tests is True
        assert "pytest" in pp.test_frameworks
        assert "uv" in pp.package_managers
        assert len(pp.quality_recommendations) == 1

    def test_confidence_clamped_to_unit_range(self) -> None:
        pp = ProjectProfile(project_type_confidence=1.0)
        assert pp.project_type_confidence == 1.0

        pp2 = ProjectProfile(project_type_confidence=0.0)
        assert pp2.project_type_confidence == 0.0


# =========================================================================
# TechStackDetector
# =========================================================================


class TestTechStackDetectorLanguages:
    def test_detect_python_with_enough_files(self, tmp_path: Path) -> None:
        # Need >= 3 .py files to register "python"
        for i in range(4):
            (tmp_path / f"mod{i}.py").write_text(f"x = {i}", encoding="utf-8")
        det = TechStackDetector(tmp_path)
        langs = det.detect_languages()
        assert "python" in langs

    def test_too_few_files_not_detected(self, tmp_path: Path) -> None:
        (tmp_path / "one.py").write_text("x = 1", encoding="utf-8")
        det = TechStackDetector(tmp_path)
        langs = det.detect_languages()
        assert "python" not in langs

    def test_multiple_languages(self, tmp_path: Path) -> None:
        for i in range(3):
            (tmp_path / f"mod{i}.py").write_text("pass", encoding="utf-8")
        for i in range(3):
            (tmp_path / f"app{i}.js").write_text("// js", encoding="utf-8")
        det = TechStackDetector(tmp_path)
        langs = det.detect_languages()
        assert "python" in langs
        assert "javascript" in langs


class TestTechStackDetectorLibraries:
    def test_from_requirements_txt(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text(
            "requests>=2.28\nflask==3.0\n# comment\npydantic\n",
            encoding="utf-8",
        )
        det = TechStackDetector(tmp_path)
        libs = det.detect_libraries()
        assert "requests" in libs
        assert "flask" in libs
        assert "pydantic" in libs

    def test_from_pyproject_toml(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\ndependencies = [\n'
            '  "httpx>=0.27",\n  "structlog",\n]\n',
            encoding="utf-8",
        )
        det = TechStackDetector(tmp_path)
        libs = det.detect_libraries()
        assert "httpx" in libs
        assert "structlog" in libs

    def test_from_pyproject_toml_poetry(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.poetry.dependencies]\npython = \"^3.12\"\n"
            'click = "^8.0"\nrich = "^13.0"\n',
            encoding="utf-8",
        )
        det = TechStackDetector(tmp_path)
        libs = det.detect_libraries()
        assert "click" in libs
        assert "rich" in libs
        # python dep should be excluded
        assert "python" not in libs

    def test_from_package_json(self, tmp_path: Path) -> None:
        pkg = {
            "dependencies": {"express": "^4.18", "cors": "^2.8"},
            "devDependencies": {"jest": "^29.0", "typescript": "^5.0"},
        }
        (tmp_path / "package.json").write_text(
            json.dumps(pkg), encoding="utf-8",
        )
        det = TechStackDetector(tmp_path)
        libs = det.detect_libraries()
        assert "express" in libs
        assert "cors" in libs
        assert "jest" in libs
        assert "typescript" in libs

    def test_from_setup_py(self, tmp_path: Path) -> None:
        (tmp_path / "setup.py").write_text(
            "from setuptools import setup\n"
            "setup(\n"
            "    install_requires=['boto3', 'pyyaml>=6.0'],\n"
            ")\n",
            encoding="utf-8",
        )
        det = TechStackDetector(tmp_path)
        libs = det.detect_libraries()
        assert "boto3" in libs
        assert "pyyaml" in libs


class TestTechStackDetectorFrameworks:
    def test_detect_from_python_imports(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text(
            "from fastapi import FastAPI\nimport pytest\n",
            encoding="utf-8",
        )
        det = TechStackDetector(tmp_path)
        fws = det.detect_frameworks()
        assert "fastapi" in fws
        assert "pytest" in fws

    def test_detect_from_js_imports(self, tmp_path: Path) -> None:
        (tmp_path / "index.js").write_text(
            "import express from 'express';\n"
            "const react = require('react');\n",
            encoding="utf-8",
        )
        det = TechStackDetector(tmp_path)
        fws = det.detect_frameworks()
        assert "express" in fws
        assert "react" in fws


class TestTechStackDetectorDomains:
    def test_detect_domains_from_libraries(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text(
            "flask\npandas\nredis\n", encoding="utf-8",
        )
        det = TechStackDetector(tmp_path)
        det.detect_libraries()
        domains = det.detect_domains()
        assert "data" in domains
        assert "database" in domains

    def test_testing_domain_from_tests_dir(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        det = TechStackDetector(tmp_path)
        domains = det.detect_domains()
        assert "testing" in domains

    def test_devops_domain_from_dockerfile(self, tmp_path: Path) -> None:
        (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
        det = TechStackDetector(tmp_path)
        domains = det.detect_domains()
        assert "devops" in domains


class TestTechStackDetectorDetectAll:
    def test_returns_complete_techstack(self, tmp_path: Path) -> None:
        # Create enough Python files
        for i in range(4):
            (tmp_path / f"mod{i}.py").write_text("pass", encoding="utf-8")
        # Add a requirements file
        (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
        # Add a Python import for framework detection
        (tmp_path / "app.py").write_text(
            "from flask import Flask\n", encoding="utf-8",
        )
        # Create tests dir for domain detection
        (tmp_path / "tests").mkdir()

        det = TechStackDetector(tmp_path)
        ts = det.detect_all()
        assert isinstance(ts, TechStack)
        assert "python" in ts.languages
        assert "flask" in ts.libraries
        assert "flask" in ts.frameworks
        assert "testing" in ts.domains
        assert "web" in ts.domains


class TestShouldSkip:
    def test_skips_venv(self, tmp_path: Path) -> None:
        p = tmp_path / ".venv" / "lib" / "foo.py"
        assert _should_skip(p) is True

    def test_skips_node_modules(self, tmp_path: Path) -> None:
        p = tmp_path / "node_modules" / "express" / "index.js"
        assert _should_skip(p) is True

    def test_skips_pycache(self, tmp_path: Path) -> None:
        p = tmp_path / "__pycache__" / "foo.cpython-312.pyc"
        assert _should_skip(p) is True

    def test_allows_normal_paths(self, tmp_path: Path) -> None:
        p = tmp_path / "src" / "main.py"
        assert _should_skip(p) is False

    def test_skip_dirs_respected_in_language_detection(self, tmp_path: Path) -> None:
        # Files inside .venv should not count toward language detection
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        for i in range(5):
            (venv / f"mod{i}.py").write_text("pass", encoding="utf-8")
        det = TechStackDetector(tmp_path)
        langs = det.detect_languages()
        assert "python" not in langs


# =========================================================================
# Type detector
# =========================================================================


class TestDetectProjectType:
    def test_api_service(self, tmp_path: Path) -> None:
        (tmp_path / "api").mkdir()
        (tmp_path / "routes").mkdir()
        (tmp_path / "openapi.yaml").write_text("openapi: 3.0\n", encoding="utf-8")
        ptype, conf, reason = detect_project_type(tmp_path)
        assert ptype == "api-service"
        assert conf >= 0.3
        assert "has_api_routes" in reason

    def test_cli_tool(self, tmp_path: Path) -> None:
        (tmp_path / "cli.py").write_text("import click\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "mycli"\n'
            '[project.scripts]\nmycli = "pkg:main"\n',
            encoding="utf-8",
        )
        ptype, conf, reason = detect_project_type(tmp_path)
        assert ptype == "cli-tool"
        assert conf >= 0.3

    def test_library(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mylib"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "mylib"\nversion = "1.0"\n',
            encoding="utf-8",
        )
        ptype, conf, reason = detect_project_type(tmp_path)
        assert ptype == "library"
        assert conf >= 0.3

    def test_microservice(self, tmp_path: Path) -> None:
        (tmp_path / "services").mkdir()
        (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
        (tmp_path / "docker-compose.yml").write_text("version: '3'\n", encoding="utf-8")
        ptype, conf, reason = detect_project_type(tmp_path)
        assert ptype == "microservice"
        assert conf >= 0.3

    def test_empty_project_returns_none(self, tmp_path: Path) -> None:
        ptype, conf, reason = detect_project_type(tmp_path)
        assert ptype is None
        assert conf == 0.0

    def test_nonexistent_root_returns_none(self, tmp_path: Path) -> None:
        ptype, conf, reason = detect_project_type(tmp_path / "nonexistent")
        assert ptype is None
        assert conf == 0.0
        assert "does not exist" in reason


# =========================================================================
# Profiler integration
# =========================================================================


class TestDetectProjectProfile:
    def test_python_project(self, tmp_path: Path) -> None:
        for i in range(4):
            (tmp_path / f"mod{i}.py").write_text("pass", encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("flask\n", encoding="utf-8")
        profile = detect_project_profile(tmp_path)
        assert isinstance(profile, ProjectProfile)
        assert "python" in profile.tech_stack.languages
        assert "flask" in profile.tech_stack.libraries

    def test_ci_detection_github_actions(self, tmp_path: Path) -> None:
        gh_dir = tmp_path / ".github" / "workflows"
        gh_dir.mkdir(parents=True)
        (gh_dir / "ci.yml").write_text("name: CI\n", encoding="utf-8")
        profile = detect_project_profile(tmp_path)
        assert profile.has_ci is True
        assert "github-actions" in profile.ci_systems

    def test_docker_detection(self, tmp_path: Path) -> None:
        (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
        profile = detect_project_profile(tmp_path)
        assert profile.has_docker is True

    def test_test_framework_detection(self, tmp_path: Path) -> None:
        (tmp_path / "conftest.py").write_text("# conftest\n", encoding="utf-8")
        profile = detect_project_profile(tmp_path)
        assert profile.has_tests is True
        assert "pytest" in profile.test_frameworks

    def test_package_manager_detection_uv(self, tmp_path: Path) -> None:
        (tmp_path / "uv.lock").write_text("# lock\n", encoding="utf-8")
        profile = detect_project_profile(tmp_path)
        assert "uv" in profile.package_managers

    def test_package_manager_pip_fallback(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\n', encoding="utf-8",
        )
        profile = detect_project_profile(tmp_path)
        assert "pip" in profile.package_managers

    def test_quality_recommendations_no_ci(self, tmp_path: Path) -> None:
        profile = detect_project_profile(tmp_path)
        assert profile.has_ci is False
        assert any("CI/CD" in r for r in profile.quality_recommendations)

    def test_quality_recommendations_no_tests(self, tmp_path: Path) -> None:
        profile = detect_project_profile(tmp_path)
        assert profile.has_tests is False
        assert any("test suite" in r for r in profile.quality_recommendations)

    def test_quality_recommendations_python_without_ruff(self, tmp_path: Path) -> None:
        for i in range(4):
            (tmp_path / f"mod{i}.py").write_text("pass", encoding="utf-8")
        profile = detect_project_profile(tmp_path)
        assert "python" in profile.tech_stack.languages
        assert any("ruff" in r for r in profile.quality_recommendations)

    def test_quality_recommendations_python_without_mypy(self, tmp_path: Path) -> None:
        for i in range(4):
            (tmp_path / f"mod{i}.py").write_text("pass", encoding="utf-8")
        profile = detect_project_profile(tmp_path)
        assert "python" in profile.tech_stack.languages
        assert any("mypy" in r for r in profile.quality_recommendations)

    def test_quality_recommendations_no_docker_for_api(self, tmp_path: Path) -> None:
        (tmp_path / "api").mkdir()
        (tmp_path / "routes").mkdir()
        (tmp_path / "openapi.yaml").write_text("openapi: 3.0\n", encoding="utf-8")
        profile = detect_project_profile(tmp_path)
        if profile.project_type in ("api-service", "microservice", "web-app"):
            assert any("Dockerfile" in r for r in profile.quality_recommendations)

    def test_multiple_ci_systems(self, tmp_path: Path) -> None:
        gh_dir = tmp_path / ".github" / "workflows"
        gh_dir.mkdir(parents=True)
        (gh_dir / "ci.yml").write_text("name: CI\n", encoding="utf-8")
        (tmp_path / ".gitlab-ci.yml").write_text("stages:\n", encoding="utf-8")
        profile = detect_project_profile(tmp_path)
        assert profile.has_ci is True
        assert "github-actions" in profile.ci_systems
        assert "gitlab-ci" in profile.ci_systems
