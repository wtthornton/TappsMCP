"""Tests for Cursor Marketplace Publishing (Story 12.17).

Verifies that the Cursor plugin marketplace files exist and
contain the required fields.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Locate the plugin directory relative to the repository root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLUGIN_DIR = _REPO_ROOT / "plugin" / "cursor"


class TestMarketplaceJson:
    """Tests for marketplace.json."""

    def test_exists(self):
        assert (_PLUGIN_DIR / "marketplace.json").exists()

    def test_valid_json(self):
        content = (_PLUGIN_DIR / "marketplace.json").read_text()
        data = json.loads(content)
        assert isinstance(data, dict)

    def test_has_required_fields(self):
        data = json.loads((_PLUGIN_DIR / "marketplace.json").read_text())
        required = [
            "name", "displayName", "author", "description",
            "keywords", "license", "version", "repository",
            "homepage", "category",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_name_matches(self):
        data = json.loads((_PLUGIN_DIR / "marketplace.json").read_text())
        assert data["name"] == "tapps-mcp-plugin"

    def test_version_semver(self):
        data = json.loads((_PLUGIN_DIR / "marketplace.json").read_text())
        assert re.match(r"\d+\.\d+\.\d+", data["version"])

    def test_repository_url(self):
        data = json.loads((_PLUGIN_DIR / "marketplace.json").read_text())
        assert data["repository"].startswith("https://github.com/")

    def test_category_non_empty(self):
        data = json.loads((_PLUGIN_DIR / "marketplace.json").read_text())
        assert isinstance(data["category"], str)
        assert len(data["category"]) > 0

    def test_keywords_list(self):
        data = json.loads((_PLUGIN_DIR / "marketplace.json").read_text())
        assert isinstance(data["keywords"], list)
        assert len(data["keywords"]) >= 3


class TestPluginJson:
    """Tests for .cursor-plugin/plugin.json."""

    def test_exists(self):
        assert (_PLUGIN_DIR / ".cursor-plugin" / "plugin.json").exists()

    def test_valid_json(self):
        content = (
            _PLUGIN_DIR / ".cursor-plugin" / "plugin.json"
        ).read_text()
        data = json.loads(content)
        assert isinstance(data, dict)

    def test_has_required_fields(self):
        data = json.loads(
            (_PLUGIN_DIR / ".cursor-plugin" / "plugin.json").read_text()
        )
        required = [
            "name", "displayName", "author", "description",
            "keywords", "license", "version",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"


class TestPluginFiles:
    """Tests for other required plugin files."""

    def test_logo_exists(self):
        assert (_PLUGIN_DIR / "logo.png").exists()

    def test_changelog_exists(self):
        assert (_PLUGIN_DIR / "CHANGELOG.md").exists()

    def test_changelog_non_empty(self):
        content = (_PLUGIN_DIR / "CHANGELOG.md").read_text()
        assert len(content) > 0

    def test_readme_exists(self):
        assert (_PLUGIN_DIR / "README.md").exists()

    def test_readme_has_installation(self):
        content = (_PLUGIN_DIR / "README.md").read_text()
        assert "Installation" in content

    def test_readme_has_deep_link(self):
        content = (_PLUGIN_DIR / "README.md").read_text()
        assert "cursor://install-plugin" in content

    def test_skills_exist(self):
        for skill in ["tapps-score", "tapps-gate", "tapps-validate"]:
            assert (
                _PLUGIN_DIR / "skills" / skill / "SKILL.md"
            ).exists(), f"Missing skill: {skill}"

    def test_mcp_json_exists(self):
        assert (_PLUGIN_DIR / "mcp.json").exists()
