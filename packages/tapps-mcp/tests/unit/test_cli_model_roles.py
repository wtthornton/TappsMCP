"""TAP-7795: ``tapps-mcp model-roles`` prints a machine-readable, derived
view of ``MODEL_ROLES`` so a downstream consumer can diff its own routing
table against this repo's actual constant instead of a hand-retyped copy.
"""

from __future__ import annotations

import json

from click.testing import CliRunner

from tapps_mcp.cli import model_roles_cmd
from tapps_mcp.pipeline.platform_skills import MODEL_ROLES

EXPECTED_ROLES = frozenset(
    {
        "driver",
        "lane",
        "verifier-deterministic",
        "verifier-comparative",
        "verifier-semantic",
        "explorer",
        "prose",
    }
)


class TestModelRolesCommand:
    def test_prints_all_seven_roles_as_json(self) -> None:
        runner = CliRunner()
        result = runner.invoke(model_roles_cmd, [])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert set(data) == EXPECTED_ROLES
        for role, entry in data.items():
            assert entry == MODEL_ROLES[role]

    def test_single_role_argument_returns_just_that_entry(self) -> None:
        runner = CliRunner()
        result = runner.invoke(model_roles_cmd, ["driver"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == {"driver": MODEL_ROLES["driver"]}

    def test_unknown_role_exits_nonzero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(model_roles_cmd, ["not-a-real-role"])
        assert result.exit_code != 0
        assert "not-a-real-role" in result.output


class TestModelRolesDerivationControl:
    """Changing the constant must change the CLI output -- proves the
    command derives from MODEL_ROLES rather than printing a stored copy."""

    def test_changing_a_role_value_changes_the_output(self, monkeypatch) -> None:
        runner = CliRunner()
        before = json.loads(runner.invoke(model_roles_cmd, ["driver"]).output)

        monkeypatch.setitem(MODEL_ROLES, "driver", {"model": "claude-opus-5", "effort": "high"})

        after = json.loads(runner.invoke(model_roles_cmd, ["driver"]).output)
        assert before != after
        assert after == {"driver": {"model": "claude-opus-5", "effort": "high"}}
