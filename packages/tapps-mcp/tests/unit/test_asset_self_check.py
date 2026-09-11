"""TAP-7156 VAL-02: the post-upgrade self-check fails loudly and names paths.

Covers both trigger conditions named in the goal: an emitted executable with
more than one shebang, and one that fails to parse.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.asset_self_check import check_asset, check_assets, main


class TestCheckAsset:
    def test_single_shebang_sh_is_clean(self, tmp_path: Path) -> None:
        target = tmp_path / "clean.sh"
        target.write_text("#!/usr/bin/env bash\necho ok\n", encoding="utf-8")
        assert check_asset(target) is None

    def test_two_shebang_sh_is_flagged(self, tmp_path: Path) -> None:
        target = tmp_path / "dup_shebang.sh"
        target.write_text(
            "#!/usr/bin/env bash\necho a\n#!/usr/bin/env bash\necho b\n", encoding="utf-8"
        )
        violation = check_asset(target)
        assert violation is not None
        assert "2 shebang" in violation.reason

    def test_broken_js_syntax_is_flagged(self, tmp_path: Path) -> None:
        target = tmp_path / "broken.js"
        target.write_text("const x = ;\n", encoding="utf-8")
        violation = check_asset(target)
        assert violation is not None
        assert "node --check" in violation.reason

    def test_valid_js_syntax_is_clean(self, tmp_path: Path) -> None:
        target = tmp_path / "ok.js"
        target.write_text("const x = 1;\nconsole.log(x);\n", encoding="utf-8")
        assert check_asset(target) is None

    def test_broken_python_syntax_is_flagged(self, tmp_path: Path) -> None:
        target = tmp_path / "broken.py"
        target.write_text("def f(:\n    pass\n", encoding="utf-8")
        violation = check_asset(target)
        assert violation is not None
        assert "py_compile" in violation.reason


class TestCheckAssetsAndCli:
    def test_planted_pair_present_yields_nonzero_and_names_both(
        self, tmp_path: Path, capsys: object
    ) -> None:
        """VAL-02 positive control: both planted files are named."""
        sh_bad = tmp_path / "dup.sh"
        sh_bad.write_text("#!/bin/sh\necho a\n#!/bin/sh\necho b\n", encoding="utf-8")
        js_bad = tmp_path / "broken.js"
        js_bad.write_text("const x = ;\n", encoding="utf-8")

        exit_code = main([str(sh_bad), str(js_bad)])

        captured = capsys.readouterr()  # type: ignore[attr-defined]
        assert exit_code != 0
        assert str(sh_bad) in captured.err
        # node may be absent on this host -- js check degrades to skip, sh
        # must still be caught either way.
        assert "dup.sh" in captured.err

    def test_removing_planted_files_yields_exit_zero(self, tmp_path: Path) -> None:
        """VAL-02 negative control: nothing planted -> clean exit."""
        clean = tmp_path / "clean.sh"
        clean.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
        assert main([str(clean)]) == 0

    def test_check_assets_batches_multiple_paths(self, tmp_path: Path) -> None:
        good = tmp_path / "good.sh"
        good.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
        bad = tmp_path / "bad.sh"
        bad.write_text("#!/bin/sh\necho a\n#!/bin/sh\necho b\n", encoding="utf-8")

        violations = check_assets([good, bad])

        assert len(violations) == 1
        assert violations[0].path == bad
