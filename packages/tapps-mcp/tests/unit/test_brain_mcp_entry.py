"""TAP-1888: bridge-only brain MCP entry doctor check + upgrade strip."""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.distribution.doctor import (
    check_brain_mcp_entry,
    strip_brain_mcp_entries,
)
from tapps_mcp.pipeline.upgrade import upgrade_pipeline


class TestCheckBrainMcpEntry:
    def test_clean_mcp_json_passes(self, tmp_path: Path) -> None:
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {"command": "uv", "args": ["run", "tapps-mcp", "serve"]}
                    }
                }
            ),
            encoding="utf-8",
        )
        result = check_brain_mcp_entry(tmp_path)
        assert result.ok is True

    def test_tapps_brain_entry_fails(self, tmp_path: Path) -> None:
        (tmp_path / ".cursor" / "mcp.json").parent.mkdir(parents=True)
        (tmp_path / ".cursor" / "mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]},
                        "tapps-brain": {"command": "tapps-brain", "args": ["serve"]},
                    }
                }
            ),
            encoding="utf-8",
        )
        result = check_brain_mcp_entry(tmp_path)
        assert result.ok is False
        assert ".cursor/mcp.json" in result.message
        assert "docs/adr/0001" in (result.detail or "")


class TestStripBrainMcpEntries:
    def test_strip_removes_brain_preserves_tapps_mcp(self, tmp_path: Path) -> None:
        mcp_path = tmp_path / ".mcp.json"
        mcp_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]},
                        "tapps-brain": {"url": "http://localhost:8080/mcp"},
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        out = strip_brain_mcp_entries(tmp_path, dry_run=False)
        assert ".mcp.json" in out["stripped"]
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
        assert "tapps-brain" not in data["mcpServers"]
        assert "tapps-mcp" in data["mcpServers"]
        assert check_brain_mcp_entry(tmp_path).ok is True

    def test_upgrade_pipeline_strips_brain_entry(self, tmp_path: Path) -> None:
        (tmp_path / ".tapps-mcp.yaml").write_text("llm_engagement_level: low\n", encoding="utf-8")
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]},
                        "tapps-brain-mcp": {"command": "tapps-brain-mcp", "args": ["serve"]},
                    }
                }
            ),
            encoding="utf-8",
        )

        result = upgrade_pipeline(tmp_path, dry_run=True, platform="")
        strip_result = result["components"]["brain_mcp_strip"]
        assert strip_result["dry_run"] is True
        assert any(".mcp.json" in entry for entry in strip_result["stripped"])
