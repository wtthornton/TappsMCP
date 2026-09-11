"""TAP-7156 VAL-01: the ``migrated`` branch must never emit a second shebang.

``install_or_refresh_asset``'s ``migrated`` branch used to splice a legacy
no-marker file's raw body in unwrapped below the managed block. Since that
body could itself start with its own ``#!`` line, the emitted file ended up
with two shebangs (only line 1 is honored by the kernel, so the second is
dead — or worse, for ``.js``, a duplicate top-level declaration is a real
``SyntaxError``, not merely a harmless comment).

The defect fires ONLY on the legacy no-marker -> marker migration transition,
never on a plain repeat upgrade of an already-marker-carrying file (the
``span is not None`` refresh branch replaces only the managed block and does
not re-append). So every fixture here seeds a pre-existing, marker-less
executable script *before* the first ``install_or_refresh_asset`` call --
that is the only path that drives the ``migrated`` branch at all.
"""

from __future__ import annotations

import re
from pathlib import Path

from tapps_mcp.pipeline.skill_asset_policy import install_or_refresh_asset, write_project_script

SKILL = "orchestration-prompt"
SH_ASSET = "scripts/canary.sh"


def _shebang_count(text: str) -> int:
    return len(re.findall(r"^#!", text, flags=re.MULTILINE))


class TestMigratedBranchNeverDuplicatesShebang:
    def test_legacy_shebang_script_migrates_to_exactly_one_shebang(self, tmp_path: Path) -> None:
        """VAL-01 proof: seeded pre-marker executable -> exactly 1 shebang."""
        target = tmp_path / "canary.sh"
        target.write_text("#!/usr/bin/env bash\nold_local_var=1\necho legacy\n", encoding="utf-8")

        action = install_or_refresh_asset(target, "#!/usr/bin/env bash\necho v2\n", SKILL, SH_ASSET)

        text = target.read_text(encoding="utf-8")
        assert action == "migrated"
        assert _shebang_count(text) == 1, text
        assert text.splitlines()[0] == "#!/usr/bin/env bash"
        # the legacy body must still be recoverable -- commented, not deleted.
        assert "old_local_var=1" in text
        assert "echo legacy" in text

    def test_write_project_script_migration_also_yields_one_shebang(self, tmp_path: Path) -> None:
        """Same fixture through the project-root entrypoint upgrade actually uses."""
        target = tmp_path / SH_ASSET
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/usr/bin/env bash\nleftover_config=1\n", encoding="utf-8")

        action = write_project_script(tmp_path, SH_ASSET, "#!/usr/bin/env bash\necho v2\n", SKILL)

        text = target.read_text(encoding="utf-8")
        assert action == "migrated"
        assert _shebang_count(text) == 1, text
        assert "leftover_config=1" in text

    def test_already_marker_carrying_file_stays_at_one_shebang(self, tmp_path: Path) -> None:
        """Positive control: a single-upgrade emitted file already yields 1."""
        target = tmp_path / "canary.sh"
        install_or_refresh_asset(target, "#!/usr/bin/env bash\necho v1\n", SKILL, SH_ASSET)
        assert _shebang_count(target.read_text(encoding="utf-8")) == 1

        action = install_or_refresh_asset(target, "#!/usr/bin/env bash\necho v2\n", SKILL, SH_ASSET)
        text = target.read_text(encoding="utf-8")
        assert action == "refreshed"
        assert _shebang_count(text) == 1, text

    def test_migrated_js_body_does_not_reintroduce_a_duplicate_declaration(
        self, tmp_path: Path
    ) -> None:
        """.js: a raw-appended prior body could raise SyntaxError on redeclare."""
        target = tmp_path / "canary.js"
        target.write_text("const shared = 1;\nconsole.log(shared);\n", encoding="utf-8")

        action = install_or_refresh_asset(
            target, "const shared = 2;\nconsole.log(shared);\n", SKILL, "workflows/canary.js"
        )

        text = target.read_text(encoding="utf-8")
        assert action == "migrated"
        # the legacy declaration must be commented out, not live code below
        # the fresh one -- otherwise this is `const shared` declared twice.
        assert "// const shared = 1;" in text
        assert text.count("const shared = 1;") == 1
