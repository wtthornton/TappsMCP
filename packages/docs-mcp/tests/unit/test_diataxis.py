"""Tests for Diataxis classification and validation (Epic 82)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from docs_mcp.analyzers.diataxis import DiataxisClassifier
from docs_mcp.validators.diataxis import DiataxisValidator
from tests.helpers import make_settings


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# DiataxisClassifier tests
# ---------------------------------------------------------------------------


class TestClassifierTutorial:
    def test_getting_started(self) -> None:
        content = "# Getting Started\n\nIn this tutorial, you will learn the basics.\n\n1. First step\n2. Second step\n3. Third step\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "tutorial"

    def test_step_by_step(self) -> None:
        content = "# Step 1: Setup\n\n## Step 2: Configure\n\n## Step 3: Run\n\nFollow along with this exercise.\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "tutorial"

    def test_walkthrough(self) -> None:
        content = "# Walkthrough\n\nLet's build your first app. You will learn how to create a project.\n\n1. Create project\n2. Add code\n3. Test\n4. Deploy\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "tutorial"

    def test_tutorial_filename(self) -> None:
        content = "# Build a Widget\n\nSome content about building.\n"
        cls = DiataxisClassifier()
        result = cls.classify(content, file_path="docs/tutorial-widgets.md")
        assert result.primary_quadrant == "tutorial"


class TestClassifierHowTo:
    def test_how_to_heading(self) -> None:
        content = "# How to Configure Authentication\n\nRun the following command to set up auth.\n\n```bash\nnpm install auth\n```\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "how-to"

    def test_setup_guide(self) -> None:
        content = "# Installation Guide\n\nInstall the package. Configure the settings.\n\n```\npip install mypackage\n```\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "how-to"

    def test_deploy_recipe(self) -> None:
        content = "# Deploy to Production\n\nEnsure that all tests pass. Execute the deploy script.\n\n```\n./deploy.sh\n```\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "how-to"


class TestClassifierReference:
    def test_api_reference(self) -> None:
        content = '# API Reference\n\n## Parameters\n\n| Name | Type | Default | Required |\n|------|------|---------|----------|\n| id | int | - | yes |\n| name | str | "" | no |\n\n## Returns\n\n| Field | Type |\n|-------|------|\n| status | int |\n'
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "reference"

    def test_specification(self) -> None:
        content = "# Specification\n\nType: string\nDefault: null\nRequired: true\n\nArgs:\n  param1: First parameter\n  param2: Second parameter\n\nReturns:\n  The result object\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "reference"

    def test_endpoint_docs(self) -> None:
        content = "# API Endpoints\n\n## GET /users\n\nParameters:\n\n| Param | Type | Default |\n|-------|------|--------|\n| limit | int | 10 |\n| offset | int | 0 |\n\nReturns: List of users\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "reference"


class TestClassifierExplanation:
    def test_architecture(self) -> None:
        content = "# Architecture Overview\n\nThis document explains the background and design decisions behind our system. The motivation was to create a scalable architecture.\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "explanation"

    def test_why_document(self) -> None:
        content = "# Why We Chose This Approach\n\nThe reason for this design is that historically we had issues with the previous approach. This is because the trade-off between speed and safety favored the current solution.\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "explanation"

    def test_design_decision(self) -> None:
        content = "# Design Decision: Event Sourcing\n\nBackground on why we chose event sourcing. The concept allows us to maintain a complete audit trail. Compared to traditional CRUD, this alternative provides better traceability.\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "explanation"


class TestClassifierEdgeCases:
    def test_empty_content(self) -> None:
        cls = DiataxisClassifier()
        result = cls.classify("")
        assert result.primary_quadrant == "explanation"  # default fallback
        assert result.confidence < 0.5

    def test_frontmatter_override(self) -> None:
        content = "---\ntitle: Some Doc\ndiataxis_type: tutorial\n---\n# Regular Content\n\nThis is reference-like content with API parameters.\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert result.primary_quadrant == "tutorial"
        assert result.confidence == 1.0
        assert "frontmatter_override" in result.indicators

    def test_mixed_content(self) -> None:
        content = "# Getting Started Guide\n\nHow to install and configure the system.\n\nStep 1: Install\nStep 2: Configure\n\n```\npip install package\n```\n"
        cls = DiataxisClassifier()
        result = cls.classify(content)
        # Should detect mixed nature
        assert result.primary_quadrant in ("tutorial", "how-to")

    def test_confidence_range(self) -> None:
        content = (
            "# API Reference\n\n## Parameters\n\n| Name | Type |\n|------|------|\n| id | int |\n"
        )
        cls = DiataxisClassifier()
        result = cls.classify(content)
        assert 0.0 <= result.confidence <= 1.0


# ---------------------------------------------------------------------------
# DiataxisValidator tests
# ---------------------------------------------------------------------------


class TestDiataxisValidator:
    def test_empty_project(self, tmp_path: Path) -> None:
        validator = DiataxisValidator()
        result = validator.validate(tmp_path)
        assert result.balance_score == 0.0
        assert result.total_files == 0
        assert len(result.recommendations) > 0

    def test_single_quadrant(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "api1.md", "# API Reference\n\n| Param | Type |\n|---|---|\n| id | int |\n"
        )
        _write(
            tmp_path / "api2.md",
            "# API Endpoints\n\n| Method | Path |\n|---|---|\n| GET | /users |\n",
        )

        validator = DiataxisValidator()
        result = validator.validate(tmp_path)

        assert result.classified_files == 2
        assert result.reference_pct > 0
        assert result.balance_score < 50  # Single quadrant = poor balance

    def test_balanced_project(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "tutorial.md",
            "# Getting Started Tutorial\n\nIn this tutorial, you will learn step by step.\n\n1. First\n2. Second\n3. Third\n",
        )
        _write(
            tmp_path / "howto.md",
            "# How to Configure\n\nInstall and set up the system.\n\n```\npip install pkg\n```\n",
        )
        _write(
            tmp_path / "reference.md",
            '# API Reference\n\n| Param | Type | Default |\n|---|---|---|\n| id | int | 0 |\n| name | str | "" |\n',
        )
        _write(
            tmp_path / "architecture.md",
            "# Architecture Overview\n\nBackground on why we designed the system this way. The motivation was scalability.\n",
        )

        validator = DiataxisValidator()
        result = validator.validate(tmp_path)

        assert result.classified_files == 4
        assert result.balance_score > 30  # All quadrants present

    def test_docs_directory_scanned(self, tmp_path: Path) -> None:
        _write(tmp_path / "docs" / "guide.md", "# How to Use\n\nInstall the package.\n")
        _write(tmp_path / "docs" / "ref.md", "# API Reference\n\nParameters.\n")

        validator = DiataxisValidator()
        result = validator.validate(tmp_path)

        assert result.classified_files == 2

    def test_recommendations_for_missing(self, tmp_path: Path) -> None:
        _write(tmp_path / "ref.md", "# API Reference\n\nSpecification of parameters.\n")

        validator = DiataxisValidator()
        result = validator.validate(tmp_path)

        # Should recommend adding missing quadrants
        rec_text = " ".join(result.recommendations).lower()
        assert "missing" in rec_text


# ---------------------------------------------------------------------------
# MCP tool handler tests
# ---------------------------------------------------------------------------


class TestDocsCheckDiataxisTool:
    async def test_success(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Project\n\nDescription.\n")
        from docs_mcp.server_val_tools import docs_check_diataxis

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_diataxis(project_root=str(tmp_path))

        assert result["success"] is True
        assert "balance_score" in result["data"]
        assert "coverage" in result["data"]
        assert "recommendations" in result["data"]

    async def test_invalid_root(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_diataxis

        bad_path = str(tmp_path / "nonexistent_dir_xyz")
        result = await docs_check_diataxis(project_root=bad_path)
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    async def test_empty_project(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_diataxis

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_diataxis(project_root=str(tmp_path))

        assert result["success"] is True
        assert result["data"]["balance_score"] == 0.0
