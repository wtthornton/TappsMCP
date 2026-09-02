"""TAP-6903: a scaffolded script's shebang must stay on line 1.

``wrap_asset()`` used to emit the policy header before the managed block
unconditionally, pushing a source asset's ``#!`` line to line 3. The
scaffolder still sets the exec bit, but the kernel only honors a shebang on
line 1, so the shipped script could not be executed directly (only via
``bash script.sh``).

Split from ``test_skill_asset_policy.py`` rather than appended to it: that
file's maintainability/complexity scores already sit at the "standard" gate
floor, and appending these tests there pushed its overall score below 70.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tapps_mcp.pipeline.skill_asset_policy import (
    install_or_refresh_asset,
    policy_header,
    strip_asset_scaffolding,
    wrap_asset,
)

SKILL = "orchestration-prompt"
SH_ASSET = "scripts/canary.sh"


class TestShebangStaysOnLine1:
    def test_shebang_stays_on_line_1(self) -> None:
        wrapped = wrap_asset("#!/usr/bin/env bash\necho ok\n", SKILL, SH_ASSET)
        assert wrapped.splitlines()[0] == "#!/usr/bin/env bash"

    def test_no_shebang_keeps_header_first(self) -> None:
        wrapped = wrap_asset("echo ok\n", SKILL, SH_ASSET)
        assert wrapped.splitlines()[0] == policy_header("managed_block", SH_ASSET)

    def test_wrapped_shebang_script_is_directly_executable(self, tmp_path: Path) -> None:
        """Acceptance item 2: write, chmod +x, execute directly."""
        wrapped = wrap_asset("#!/usr/bin/env bash\necho ok\n", SKILL, SH_ASSET)
        target = tmp_path / "canary.sh"
        target.write_text(wrapped, encoding="utf-8")
        target.chmod(target.stat().st_mode | 0o111)

        result = subprocess.run([str(target)], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert result.stdout == "ok\n"


class TestShebangRoundTrip:
    """Acceptance item 3: strip_asset_scaffolding recovers the original."""

    def test_round_trips_a_shebang_body(self) -> None:
        body = "#!/usr/bin/env bash\necho ok\n"
        wrapped = wrap_asset(body, SKILL, SH_ASSET)
        assert strip_asset_scaffolding(wrapped) == body.rstrip("\n")

    def test_round_trips_a_no_shebang_body(self) -> None:
        body = "echo ok\n"
        wrapped = wrap_asset(body, SKILL, SH_ASSET)
        assert strip_asset_scaffolding(wrapped) == body.rstrip("\n")


class TestShebangSurvivesInstallOrRefresh:
    """``write_project_script`` goes through this path — must stay consistent
    with ``wrap_asset`` across create/unchanged/refresh."""

    def test_preserves_shebang_on_create(self, tmp_path: Path) -> None:
        target = tmp_path / "canary.sh"
        install_or_refresh_asset(target, "#!/usr/bin/env bash\necho v1\n", SKILL, SH_ASSET)
        assert target.read_text(encoding="utf-8").splitlines()[0] == "#!/usr/bin/env bash"

    def test_is_unchanged_on_rerun(self, tmp_path: Path) -> None:
        target = tmp_path / "canary.sh"
        install_or_refresh_asset(target, "#!/usr/bin/env bash\necho v1\n", SKILL, SH_ASSET)
        assert (
            install_or_refresh_asset(target, "#!/usr/bin/env bash\necho v1\n", SKILL, SH_ASSET)
            == "unchanged"
        )

    def test_keeps_shebang_on_refresh(self, tmp_path: Path) -> None:
        target = tmp_path / "canary.sh"
        install_or_refresh_asset(target, "#!/usr/bin/env bash\necho v1\n", SKILL, SH_ASSET)
        action = install_or_refresh_asset(
            target, "#!/usr/bin/env bash\necho v2\n", SKILL, SH_ASSET
        )
        text = target.read_text(encoding="utf-8")
        assert action == "refreshed"
        assert text.splitlines()[0] == "#!/usr/bin/env bash"
        assert "echo v2" in text
