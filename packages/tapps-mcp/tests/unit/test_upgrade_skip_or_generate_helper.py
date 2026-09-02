"""Pins the skip-or-generate branch shape collapsed into a helper (TAP-6884).

``_apply_or_skip`` / ``_dry_run_status`` replace the repeated
``if _skipped(...): result[...] = "skipped ..." else: result[...] = generate(...)``
blocks in ``upgrade.py``. Several call sites (e.g. ``autonomy_rule``) have no
per-artifact ``upgrade_pipeline`` test of their own, so this pins the shared
shape directly rather than relying on the call sites that do.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tapps_mcp.pipeline.upgrade import _apply_or_skip, _dry_run_status


class TestApplyOrSkip:
    def test_skip_token_present_sets_marker_without_calling_generate(self) -> None:
        calls: list[Path] = []

        def generate(project_root: Path) -> dict[str, Any]:
            calls.append(project_root)
            return {"action": "created"}

        result: dict[str, Any] = {"components": {}}
        _apply_or_skip(result, "measure_script", {"scripts/measure.py"}, generate, Path("/tmp/x"))

        assert result["components"]["measure_script"] == "skipped (upgrade_skip_files)"
        assert calls == []

    def test_no_skip_token_calls_generate_and_stores_its_result(self) -> None:
        def generate(project_root: Path) -> dict[str, Any]:
            return {"action": "created", "path": str(project_root)}

        result: dict[str, Any] = {"components": {}}
        _apply_or_skip(result, "measure_script", set(), generate, Path("/tmp/x"))

        assert result["components"]["measure_script"] == {
            "action": "created",
            "path": "/tmp/x",
        }


class TestDryRunStatus:
    def test_skip_token_present_returns_skip_marker(self) -> None:
        assert (
            _dry_run_status("gitfacts_script", {"scripts/gitfacts.sh"})
            == "skipped (upgrade_skip_files)"
        )

    def test_no_skip_token_returns_would_regenerate(self) -> None:
        assert _dry_run_status("gitfacts_script", set()) == "would-regenerate"
