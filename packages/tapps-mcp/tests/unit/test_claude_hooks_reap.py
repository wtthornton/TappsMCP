"""Tests for the ADR-0005 MCP reap ownership gate in the Claude sessionStart hook.

The reap scans ``ps`` host-globally, so it sees MCP servers belonging to sibling
repos checked out on the same machine. Signalling those takes down another
project's live session. These tests pin the two properties that prevent it:

* a process rooted in another project is never signalled;
* a true orphan is still collected, so ADR-0005 keeps working.

The behavioural tests execute the *generated* bash against real processes. String
assertions cannot catch a gate that parses cleanly but classifies wrongly, which is
precisely the failure mode that kills a sibling repo's server.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

from tapps_mcp.pipeline.platform_hook_templates import CLAUDE_HOOK_SCRIPTS

_HOOK = "tapps-session-start.sh"


def _extract_ownership_gate() -> str:
    """Pull the ownership-gate bash out of the generated sessionStart hook."""
    content = CLAUDE_HOOK_SCRIPTS[_HOOK]
    match = re.search(
        r"^    TAPPS_REAP_ROOT=.*?(?=^    OLD_PIDS=)", content, re.MULTILINE | re.DOTALL
    )
    assert match, "ownership gate not found in generated sessionStart hook"
    gate = match.group(0)
    # Guard the extraction itself: a partial capture leaves the classifier undefined
    # and every case falls through to "not reapable" — a green suite proving nothing.
    assert "_tapps_pid_cwd()" in gate
    assert "_tapps_ppid_orphaned()" in gate
    assert "_tapps_pid_reapable()" in gate
    return gate


class TestReapGateContent:
    """Structural assertions on the generated hook text."""

    def test_reap_is_scoped_to_this_project(self) -> None:
        content = CLAUDE_HOOK_SCRIPTS[_HOOK]
        assert "_tapps_pid_reapable" in content
        assert "TAPPS_REAP_ROOT" in content
        assert "FOREIGN_PIDS" in content

    def test_kill_consumes_filtered_set_not_raw_candidates(self) -> None:
        """The regression: killing the unfiltered candidate list."""
        content = CLAUDE_HOOK_SCRIPTS[_HOOK]
        assert 'echo "$ZOMBIE_PIDS" | xargs kill' not in content
        assert 'echo "$OWNED_PIDS" | xargs kill' in content

    def test_cwd_resolution_is_portable(self) -> None:
        """/proc is Linux-only; macOS needs the lsof path."""
        content = CLAUDE_HOOK_SCRIPTS[_HOOK]
        assert "/proc/$1/cwd" in content
        assert "lsof" in content

    def test_multi_pid_candidate_lines_are_split_before_filtering(self) -> None:
        """The dup awk space-joins pids per profile; ``^[0-9]+$`` rejects such a line.

        Without the split, any profile with more than one duplicate was dropped
        entirely and nothing got reaped.
        """
        content = CLAUDE_HOOK_SCRIPTS[_HOOK]
        assert "tr ' ' '\\n' | sort -u | grep -E '^[0-9]+$'" in content

    def test_orphan_check_recognises_subreaper_adoption(self) -> None:
        """``ppid == 1`` alone is inert on systemd hosts.

        Orphans reparent to a live ``systemd --user``, so a pid-1 test never fires
        and the reap silently collects nothing.
        """
        content = CLAUDE_HOOK_SCRIPTS[_HOOK]
        assert "systemd|init|launchd" in content


@pytest.mark.skipif(sys.platform == "win32", reason="bash reap block is POSIX-only")
class TestReapGateBehaviour:
    """Execute the generated gate against real processes."""

    def _classify(self, tmp_path, spawn: str) -> str:
        """Spawn one process via ``spawn`` and return REAP or LEAVE."""
        (tmp_path / "sibling-repo").mkdir(exist_ok=True)
        script = tmp_path / "classify.sh"
        script.write_text(
            "#!/usr/bin/env bash\n"
            f"cd {tmp_path!s}\n"
            f"{_extract_ownership_gate()}"
            f"{spawn}\n"
            "sleep 0.5\n"
            'if _tapps_pid_reapable "$TARGET"; then echo REAP; else echo LEAVE; fi\n'
            'kill "$TARGET" 2>/dev/null\n'
        )
        # Hermetic: an inherited TAPPS_PROJECT_ROOT would point the gate at the real
        # repo instead of tmp_path and silently invert every verdict.
        env = {k: v for k, v in os.environ.items() if k != "TAPPS_PROJECT_ROOT"}
        result = subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
            cwd=str(tmp_path),
            env=env,
        )
        return result.stdout.strip().splitlines()[-1]

    def test_merge_keeps_both_pids_from_a_multi_pid_line(self, tmp_path) -> None:
        """Run the real merge pipeline with a two-dup line, as the awk emits it."""
        content = CLAUDE_HOOK_SCRIPTS[_HOOK]
        match = re.search(
            r"^    ZOMBIE_PIDS=\$\(\{.*?\|\| true\)$", content, re.MULTILINE | re.DOTALL
        )
        assert match, "merge block not found in generated sessionStart hook"
        script = tmp_path / "merge.sh"
        script.write_text(
            "#!/usr/bin/env bash\n"
            'OLD_PIDS=""\nVENV_PIDS=""\nNLT_STALE_PIDS=""\n'
            'NLT_DUP_PIDS="111 222"\n'
            f"{match.group(0)}\n"
            'echo "$ZOMBIE_PIDS"\n'
        )
        result = subprocess.run(
            ["bash", str(script)], capture_output=True, text=True, timeout=30, check=True
        )
        assert result.stdout.split() == ["111", "222"]

    def test_generated_hook_is_valid_bash(self, tmp_path) -> None:
        script = tmp_path / "gate.sh"
        script.write_text("#!/usr/bin/env bash\n" + CLAUDE_HOOK_SCRIPTS[_HOOK])
        subprocess.run(["bash", "-n", str(script)], check=True, timeout=30)

    def test_process_rooted_in_this_project_is_reaped(self, tmp_path) -> None:
        assert self._classify(tmp_path, "sleep 30 & TARGET=$!") == "REAP"

    def test_process_rooted_in_sibling_repo_is_left_alone(self, tmp_path) -> None:
        """The regression under test: never signal another project's live server."""
        spawn = f"( cd {tmp_path!s}/sibling-repo && exec sleep 30 ) & TARGET=$!"
        assert self._classify(tmp_path, spawn) == "LEAVE"

    def test_true_orphan_is_reaped(self, tmp_path) -> None:
        """Rooted outside the project, so only the orphan branch can yield REAP."""
        pidfile = tmp_path / "orphan.pid"
        sibling = tmp_path / "sibling-repo"
        # The intermediate subshell exits immediately, reparenting the sleep away.
        spawn = (
            f"( cd {sibling!s} && {{ sleep 30 & echo $! > {pidfile!s}; }} )\n"
            "sleep 0.3\n"
            f"TARGET=$(cat {pidfile!s})"
        )
        assert self._classify(tmp_path, spawn) == "REAP"
