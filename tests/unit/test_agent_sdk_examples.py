"""Tests for Agent SDK Integration examples (Story 12.18).

Verifies that the Python example files have no syntax errors
and contain the expected SDK references.
"""

from __future__ import annotations

import json
import py_compile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES_DIR = _REPO_ROOT / "examples" / "agent-sdk"
_PYTHON_DIR = _EXAMPLES_DIR / "python"
_TS_DIR = _EXAMPLES_DIR / "typescript"


class TestPythonExamplesCompile:
    """Tests that Python examples have no syntax errors."""

    def test_basic_quality_check_compiles(self):
        py_compile.compile(
            str(_PYTHON_DIR / "basic_quality_check.py"),
            doraise=True,
        )

    def test_quality_gate_pipeline_compiles(self):
        py_compile.compile(
            str(_PYTHON_DIR / "quality_gate_pipeline.py"),
            doraise=True,
        )

    def test_subagent_example_compiles(self):
        py_compile.compile(
            str(_PYTHON_DIR / "subagent_example.py"),
            doraise=True,
        )


class TestPythonExamplesContent:
    """Tests that Python examples contain expected SDK references."""

    def test_basic_has_mcp_servers(self):
        content = (_PYTHON_DIR / "basic_quality_check.py").read_text()
        assert "mcp_servers" in content or "McpServerConfig" in content

    def test_basic_has_quick_check(self):
        content = (_PYTHON_DIR / "basic_quality_check.py").read_text()
        assert "tapps_quick_check" in content

    def test_pipeline_has_validate_changed(self):
        content = (_PYTHON_DIR / "quality_gate_pipeline.py").read_text()
        assert "tapps_validate_changed" in content

    def test_pipeline_has_mcp_servers(self):
        content = (_PYTHON_DIR / "quality_gate_pipeline.py").read_text()
        assert "mcp_servers" in content or "McpServerConfig" in content

    def test_subagent_has_agent_definition(self):
        content = (_PYTHON_DIR / "subagent_example.py").read_text()
        assert "AgentDefinition" in content

    def test_subagent_has_tapps_reviewer(self):
        content = (_PYTHON_DIR / "subagent_example.py").read_text()
        assert "tapps-reviewer" in content


class TestReadme:
    """Tests for the examples README."""

    def test_readme_exists(self):
        assert (_EXAMPLES_DIR / "README.md").exists()

    def test_readme_has_prerequisites(self):
        content = (_EXAMPLES_DIR / "README.md").read_text()
        assert "Prerequisites" in content


class TestTypescriptFiles:
    """Tests that TypeScript files exist and have correct content."""

    def test_basic_ts_exists(self):
        assert (_TS_DIR / "basic_quality_check.ts").exists()

    def test_basic_ts_has_mcp_servers(self):
        content = (_TS_DIR / "basic_quality_check.ts").read_text()
        assert "mcpServers" in content

    def test_basic_ts_has_quick_check(self):
        content = (_TS_DIR / "basic_quality_check.ts").read_text()
        assert "tapps_quick_check" in content

    def test_subagent_ts_exists(self):
        assert (_TS_DIR / "subagent_pipeline.ts").exists()

    def test_tsconfig_valid_json(self):
        content = (_TS_DIR / "tsconfig.json").read_text()
        data = json.loads(content)
        assert "compilerOptions" in data

    def test_package_json_valid(self):
        content = (_TS_DIR / "package.json").read_text()
        data = json.loads(content)
        assert "@anthropic-ai/claude-code" in str(data)
