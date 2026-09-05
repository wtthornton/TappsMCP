"""TAP-6968 (tapps-mcp half): ``tapps-mcp managed-block-hash`` prints the
emitter's current canonical managed-block hash for a skill.

No CLI or Python entry point existed to hash the emitter's *current* body for
a named skill; the closest existing code
(``distribution.doctor_skills._check_managed_skill_current``) computes the
same underlying value but only as an internal equality check inside doctor,
never as a standalone, scriptable target a fleet sweep could diff against.
"""

from __future__ import annotations

import hashlib
import json
import re

from click.testing import CliRunner

from tapps_mcp.cli import managed_block_hash_cmd
from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS, CURSOR_SKILLS
from tapps_mcp.pipeline.skill_managed_block import (
    extract_block,
    normalize_block_version,
    wrap_with_markers,
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _expected_hash(skill_name: str, host: str) -> str:
    catalogue = CLAUDE_SKILLS if host == "claude" else CURSOR_SKILLS
    block = extract_block(wrap_with_markers(catalogue[skill_name], skill_name))
    assert block is not None
    return hashlib.sha256(normalize_block_version(block).encode("utf-8")).hexdigest()


class TestManagedBlockHashCommand:
    def test_prints_json_line_with_64_hex_hash(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            managed_block_hash_cmd, ["orchestration-prompt", "--host", "claude"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["skill"] == "orchestration-prompt"
        assert data["host"] == "claude"
        assert _HEX64.match(data["hash"])

    def test_hash_matches_independently_computed_value(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            managed_block_hash_cmd, ["orchestration-prompt", "--host", "claude"]
        )
        data = json.loads(result.output)
        assert data["hash"] == _expected_hash("orchestration-prompt", "claude")

    def test_cursor_host_also_resolves(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            managed_block_hash_cmd, ["orchestration-prompt", "--host", "cursor"]
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["hash"] == _expected_hash("orchestration-prompt", "cursor")

    def test_unknown_skill_errors(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            managed_block_hash_cmd, ["not-a-real-skill", "--host", "claude"]
        )
        assert result.exit_code != 0

    def test_default_host_is_claude(self) -> None:
        runner = CliRunner()
        result = runner.invoke(managed_block_hash_cmd, ["orchestration-prompt"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["host"] == "claude"


class TestManagedBlockHashComparativeNegativeControl:
    """Changing the upstream body by even one character must move the hash."""

    def test_one_character_change_changes_the_hash(self, monkeypatch) -> None:
        runner = CliRunner()
        before = json.loads(
            runner.invoke(
                managed_block_hash_cmd, ["orchestration-prompt", "--host", "claude"]
            ).output
        )["hash"]

        original_body = CLAUDE_SKILLS["orchestration-prompt"]
        monkeypatch.setitem(
            CLAUDE_SKILLS, "orchestration-prompt", original_body + " "
        )

        after = json.loads(
            runner.invoke(
                managed_block_hash_cmd, ["orchestration-prompt", "--host", "claude"]
            ).output
        )["hash"]

        assert before != after
