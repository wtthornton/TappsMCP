"""TAP-7846: ``deploy-local --help`` text must match actual restart behavior.

The help text used to read "Running MCP servers stay pinned to their release
dir; reload MCP in Cursor to pick up the new build." -- true of the *inode*
mechanism (``blue_green.py:14``, ``setup_launch.py:332``), false as operator
guidance: the code restarts the whole six-server fleet itself whenever any of
it is running (``blue_green._deploy_under_lock``, ``fleet_any_running`` /
``restart_fleet_with_smoke``). An operator following the old text would wait
for a reload that already happened, or not realize a "local" deploy just
restarted the MCP backend shared by every repo and session on the host.
"""

from __future__ import annotations

import inspect

from tapps_mcp import cli_deploy
from tapps_mcp.distribution import blue_green as bg
from tapps_mcp.distribution import setup_launch


def _restart_branch_source() -> str:
    return inspect.getsource(bg._restart_fleet_and_reverify_deferred)


class TestHelpTextMatchesRestartBehavior:
    def test_code_restarts_the_fleet_when_running(self) -> None:
        """Sanity check on the claim the help text must reflect."""
        source = _restart_branch_source()
        assert "fleet_any_running" in source
        assert "restart_fleet_with_smoke" in source

    def test_help_text_states_the_fleet_is_restarted(self) -> None:
        doc = (cli_deploy.deploy_local_cmd.__doc__ or "").lower()
        assert "restart" in doc and "fleet" in doc, (
            "help text must say the fleet is restarted when it is running, "
            "matching blue_green.py's fleet_any_running/restart_fleet_with_smoke branch"
        )

    def test_help_text_does_not_claim_manual_reload_with_no_restart(self) -> None:
        """Negative control: the pre-fix wording -- 'stay pinned ... reload MCP
        in Cursor to pick up the new build' with no mention of an automatic
        restart -- must not appear, since it told operators the opposite of
        what the code does.
        """
        doc = (cli_deploy.deploy_local_cmd.__doc__ or "").lower()
        claims_pinned_reload_only = (
            "stay pinned" in doc
            and "reload mcp in cursor" in doc
            and "restart" not in doc
        )
        assert not claims_pinned_reload_only

    def test_help_text_names_the_shared_blast_radius(self) -> None:
        doc = cli_deploy.deploy_local_cmd.__doc__ or ""
        assert "8760" in doc and "8765" in doc
        assert "every repo" in doc.lower() or "shared" in doc.lower()

    def test_accurate_inode_pinning_text_untouched_blue_green(self) -> None:
        """Positive control: the mechanism description this fix must leave
        alone (it describes already-running processes correctly, unlike the
        operator-facing help text above).
        """
        source_lines = inspect.getsource(bg).splitlines()
        assert any(
            "stay pinned to the release dir they were launched from (inode-held)" in line
            for line in source_lines
        )

    def test_accurate_inode_pinning_text_untouched_setup_launch(self) -> None:
        source_lines = inspect.getsource(setup_launch).splitlines()
        assert any(
            "running servers stay pinned to their release dir; only new launches pick up"
            in line
            for line in source_lines
        )
