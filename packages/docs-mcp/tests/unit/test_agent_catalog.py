"""Tests for agent catalog loader."""

from __future__ import annotations

from pathlib import Path

from docs_mcp.agents.catalog import AgentCatalog, _parse_frontmatter, load_agent_config
from docs_mcp.agents.models import MemoryProfile


class TestParseFrontmatter:
    """Test YAML frontmatter parsing."""

    def test_valid_frontmatter(self) -> None:
        content = """---
name: test-agent
description: A test agent
keywords:
  - test
  - demo
---

# Agent Documentation
"""
        result = _parse_frontmatter(content)
        assert result["name"] == "test-agent"
        assert result["description"] == "A test agent"
        assert result["keywords"] == ["test", "demo"]

    def test_no_frontmatter(self) -> None:
        content = "# Just a regular markdown file\n\nSome content."
        result = _parse_frontmatter(content)
        assert result == {}

    def test_empty_frontmatter(self) -> None:
        content = "---\n---\nContent"
        result = _parse_frontmatter(content)
        assert result == {}

    def test_no_closing_delimiter(self) -> None:
        content = "---\nname: test\nNo closing delimiter"
        result = _parse_frontmatter(content)
        assert result == {}

    def test_invalid_yaml(self) -> None:
        content = "---\n: invalid: yaml: [[\n---\nContent"
        result = _parse_frontmatter(content)
        assert result == {}

    def test_non_dict_yaml(self) -> None:
        content = "---\n- just\n- a\n- list\n---\nContent"
        result = _parse_frontmatter(content)
        assert result == {}

    def test_whitespace_handling(self) -> None:
        content = """
---
name: spaced-agent
description: Has leading whitespace
---

Body text.
"""
        result = _parse_frontmatter(content)
        assert result["name"] == "spaced-agent"


class TestLoadAgentConfig:
    """Test loading AgentConfig from files."""

    def test_valid_agent_file(self, tmp_path: Path) -> None:
        agent_file = tmp_path / "weather-agent.md"
        agent_file.write_text("""---
name: weather
description: Provides weather forecasts
keywords:
  - weather
  - forecast
memory_profile: readonly
---

# Weather Agent

This agent provides weather information.
""")
        config = load_agent_config(agent_file)
        assert config is not None
        assert config.name == "weather"
        assert config.description == "Provides weather forecasts"
        assert config.keywords == ["weather", "forecast"]
        assert config.memory_profile == MemoryProfile.READONLY
        assert config.source_path == agent_file

    def test_missing_name(self, tmp_path: Path) -> None:
        agent_file = tmp_path / "no-name.md"
        agent_file.write_text("""---
description: Agent without a name
---
""")
        config = load_agent_config(agent_file)
        assert config is None

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        agent_file = tmp_path / "plain.md"
        agent_file.write_text("# Just a plain file\n\nNo frontmatter here.")
        config = load_agent_config(agent_file)
        assert config is None

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        config = load_agent_config(tmp_path / "does-not-exist.md")
        assert config is None

    def test_unknown_fields_ignored(self, tmp_path: Path) -> None:
        agent_file = tmp_path / "extra-fields.md"
        agent_file.write_text("""---
name: test
description: Test agent
unknown_field: should be ignored
another_unknown: also ignored
---
""")
        config = load_agent_config(agent_file)
        assert config is not None
        assert config.name == "test"


class TestAgentCatalog:
    """Test AgentCatalog operations."""

    def test_from_directory(self, tmp_path: Path) -> None:
        # Create agent files
        for name in ["alpha", "beta", "gamma"]:
            (tmp_path / f"{name}.md").write_text(f"""---
name: {name}
description: Agent {name}
keywords:
  - {name}
---
""")

        catalog = AgentCatalog.from_directory(tmp_path)
        assert len(catalog) == 3
        assert catalog.get("alpha") is not None
        assert catalog.get("beta") is not None

    def test_from_nonexistent_directory(self, tmp_path: Path) -> None:
        catalog = AgentCatalog.from_directory(tmp_path / "nonexistent")
        assert len(catalog) == 0

    def test_active_agents_excludes_deprecated(self) -> None:
        from docs_mcp.agents.models import AgentConfig

        agents = [
            AgentConfig(name="active", deprecated=False),
            AgentConfig(name="old", deprecated=True),
            AgentConfig(name="also-active", deprecated=False),
        ]
        catalog = AgentCatalog(agents)
        assert len(catalog.agents) == 3
        assert len(catalog.active_agents) == 2
        assert all(a.name != "old" for a in catalog.active_agents)

    def test_get_existing(self) -> None:
        from docs_mcp.agents.models import AgentConfig

        catalog = AgentCatalog([AgentConfig(name="target")])
        assert catalog.get("target") is not None
        assert catalog.get("target")

    def test_get_missing(self) -> None:
        catalog = AgentCatalog([])
        assert catalog.get("nonexistent") is None

    def test_add_agent(self) -> None:
        from docs_mcp.agents.models import AgentConfig

        catalog = AgentCatalog()
        assert len(catalog) == 0
        catalog.add(AgentConfig(name="new-agent"))
        assert len(catalog) == 1
        assert catalog.get("new-agent") is not None

    def test_remove_agent(self) -> None:
        from docs_mcp.agents.models import AgentConfig

        catalog = AgentCatalog([AgentConfig(name="removable")])
        assert len(catalog) == 1
        assert catalog.remove("removable") is True
        assert len(catalog) == 0

    def test_remove_nonexistent(self) -> None:
        catalog = AgentCatalog()
        assert catalog.remove("ghost") is False

    def test_skips_invalid_files(self, tmp_path: Path) -> None:
        # Valid agent
        (tmp_path / "good.md").write_text("---\nname: good\n---\n")
        # Invalid (no frontmatter)
        (tmp_path / "bad.md").write_text("Just text, no frontmatter")
        # Invalid (no name)
        (tmp_path / "nameless.md").write_text("---\ndescription: no name\n---\n")

        catalog = AgentCatalog.from_directory(tmp_path)
        assert len(catalog) == 1
        assert catalog.get("good") is not None
