"""Tests for usage gap SessionStart hints (TAP-3578)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from tapps_mcp.tools.usage import (
    compute_gaps,
    format_session_start_gap_hint,
    format_stop_gap_followup,
)


class TestLookupDocsUnderused:
    def _write_edit_loops(
        self,
        metrics_dir: Path,
        *,
        rel_path: str,
        loops: int,
        lookup_docs_called: bool = False,
    ) -> None:
        now = int(time.time())
        rows = []
        for i in range(loops):
            rows.append(
                {
                    "ts": now - i,
                    "files_edited": [rel_path],
                    "gate_skipped_files": [],
                    "lookup_docs_called": lookup_docs_called,
                    "checklist_called": True,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                }
            )
        (metrics_dir / "loop-metrics.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n",
            encoding="utf-8",
        )

    def test_suppressed_for_workspace_only_edits(self, tmp_path: Path) -> None:
        """Internal monorepo edits should not trigger ratio-only lookup nagging."""
        pkg = tmp_path / "packages" / "tapps-mcp" / "src" / "tapps_mcp"
        pkg.mkdir(parents=True)
        mod = pkg / "upgrade.py"
        mod.write_text(
            "from tapps_mcp.pipeline.platform_hooks import cleanup_legacy_hook_sidecars\n"
            "import re\n",
            encoding="utf-8",
        )
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "tapps-mcp"\n\n[tool.uv.workspace]\nmembers = ["packages/*"]\n',
            encoding="utf-8",
        )
        (tmp_path / "packages" / "tapps-mcp" / "pyproject.toml").write_text(
            '[project]\nname = "tapps-mcp"\n',
            encoding="utf-8",
        )
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        rel = str(mod.relative_to(tmp_path))
        self._write_edit_loops(metrics_dir, rel_path=rel, loops=4)
        report = compute_gaps(
            tmp_path,
            called_tools={"tapps_session_start", "tapps_validate_changed", "tapps_checklist"},
        )
        assert "lookup_docs_underused" not in report["gaps"]

    def test_fires_when_uncached_external_libs_and_low_ratio(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        mod = src_dir / "api.py"
        mod.write_text("import fastapi\n", encoding="utf-8")
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        rel = str(mod.relative_to(tmp_path))
        self._write_edit_loops(metrics_dir, rel_path=rel, loops=4)
        report = compute_gaps(
            tmp_path,
            called_tools={"tapps_session_start", "tapps_validate_changed", "tapps_checklist"},
        )
        assert "lookup_docs_underused" in report["gaps"]


class TestLibraryUsesWithoutLookupDocs:
    def test_lists_uncached_libraries_from_edited_files(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "packages" / "app" / "src" / "app"
        src_dir.mkdir(parents=True)
        mod = src_dir / "service.py"
        mod.write_text(
            "import fastapi\nfrom pydantic import BaseModel\n",
            encoding="utf-8",
        )
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        rel = str(mod.relative_to(tmp_path))
        (metrics_dir / "loop-metrics.jsonl").write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": [rel],
                    "gate_skipped_files": [],
                    "lookup_docs_called": False,
                    "checklist_called": True,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        report = compute_gaps(
            tmp_path,
            called_tools={"tapps_session_start", "tapps_validate_changed", "tapps_checklist"},
        )
        assert "library_uses_without_lookup_docs" in report["gaps"]
        assert "fastapi" in report["libraries_without_lookup"]
        assert "pydantic" in report["libraries_without_lookup"]
        assert any("fastapi" in rec for rec in report["recommendations"])

    def test_suppresses_gap_for_test_only_pytest_edits(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_foo.py"
        test_file.write_text(
            "import pytest\nfrom unittest.mock import AsyncMock\n",
            encoding="utf-8",
        )
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        rel = str(test_file.relative_to(tmp_path))
        (metrics_dir / "loop-metrics.jsonl").write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": [rel],
                    "gate_skipped_files": [],
                    "lookup_docs_called": False,
                    "checklist_called": True,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        report = compute_gaps(
            tmp_path,
            called_tools={"tapps_session_start", "tapps_validate_changed", "tapps_checklist"},
        )
        assert "library_uses_without_lookup_docs" not in report["gaps"]

    def test_stop_followup_names_libraries(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        mod = src_dir / "api.py"
        mod.write_text("import httpx\n", encoding="utf-8")
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        rel = str(mod.relative_to(tmp_path))
        (metrics_dir / "loop-metrics.jsonl").write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": [rel],
                    "gate_skipped_files": [],
                    "lookup_docs_called": False,
                    "checklist_called": True,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        followup = format_stop_gap_followup(
            tmp_path,
            called_tools={"tapps_validate_changed", "tapps_checklist"},
            mode="warn",
        )
        assert followup is not None
        assert "httpx" in followup
        assert "library_uses_without_lookup_docs" in followup

    def test_suppressed_when_import_cached_under_pypi_name(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        mod = src_dir / "config_loader.py"
        mod.write_text("import yaml\n", encoding="utf-8")
        cache_dir = tmp_path / ".tapps-mcp-cache" / "pyyaml"
        cache_dir.mkdir(parents=True)
        (cache_dir / "overview.md").write_text("# PyYAML\n", encoding="utf-8")
        (cache_dir / "overview.meta.json").write_text(
            json.dumps({"library": "pyyaml", "topic": "overview", "cached_at": int(time.time())}),
            encoding="utf-8",
        )
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        rel = str(mod.relative_to(tmp_path))
        (metrics_dir / "loop-metrics.jsonl").write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": [rel],
                    "gate_skipped_files": [],
                    "lookup_docs_called": False,
                    "checklist_called": True,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        report = compute_gaps(
            tmp_path,
            called_tools={"tapps_session_start", "tapps_validate_changed", "tapps_checklist"},
        )
        assert "library_uses_without_lookup_docs" not in report["gaps"]

    def test_cli_lookup_event_clears_gap_for_session_start(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        mod = src_dir / "api.py"
        mod.write_text("import httpx\n", encoding="utf-8")
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        rel = str(mod.relative_to(tmp_path))
        (metrics_dir / "loop-metrics.jsonl").write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": [rel],
                    "gate_skipped_files": [],
                    "lookup_docs_called": False,
                    "checklist_called": True,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        from tapps_mcp.tools.lookup_telemetry import record_lookup_event

        record_lookup_event(
            tmp_path,
            library="httpx",
            topic="client",
            source="cli",
        )
        report = compute_gaps(tmp_path, called_tools=set())
        assert "library_uses_without_lookup_docs" not in report["gaps"]


class TestComprehensionToolsUnderused:
    def _write_cross_module_edit(self, tmp_path: Path, tools_used: list[str]) -> None:
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (metrics_dir / "loop-metrics.jsonl").write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": [
                        str(tmp_path / "src/mod_a/x.py"),
                        str(tmp_path / "src/mod_a/y.py"),
                        str(tmp_path / "src/mod_b/z.py"),
                    ],
                    "gate_skipped_files": [],
                    "lookup_docs_called": True,
                    "checklist_called": True,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist", *tools_used],
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def test_fires_on_cross_module_edits_without_comprehension(self, tmp_path: Path) -> None:
        self._write_cross_module_edit(tmp_path, tools_used=[])
        report = compute_gaps(tmp_path, called_tools=set())
        assert "comprehension_tools_underused" in report["gaps"]

    def test_suppressed_when_impact_analysis_used(self, tmp_path: Path) -> None:
        self._write_cross_module_edit(tmp_path, tools_used=["tapps_impact_analysis"])
        report = compute_gaps(tmp_path, called_tools=set())
        assert "comprehension_tools_underused" not in report["gaps"]

    def test_suppressed_when_call_graph_in_called_set(self, tmp_path: Path) -> None:
        self._write_cross_module_edit(tmp_path, tools_used=[])
        report = compute_gaps(tmp_path, called_tools={"tapps_call_graph"})
        assert "comprehension_tools_underused" not in report["gaps"]

    def test_not_fired_for_single_module_edit(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        (metrics_dir / "loop-metrics.jsonl").write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": [str(tmp_path / "src/mod_a/x.py")],
                    "gate_skipped_files": [],
                    "lookup_docs_called": True,
                    "checklist_called": True,
                    "tools_used": ["tapps_validate_changed"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        report = compute_gaps(tmp_path, called_tools=set())
        assert "comprehension_tools_underused" not in report["gaps"]


class TestComputeGapsScopedEdits:
    def test_tmp_scratch_excluded_from_edits_without_validation(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        loop_metrics = metrics_dir / "loop-metrics.jsonl"
        loop_metrics.write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": ["/tmp/snippet.py", str(tmp_path / "src/a.py")],
                    "gate_skipped_files": ["/tmp/snippet.py"],
                    "lookup_docs_called": False,
                    "checklist_called": False,
                    "tools_used": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        report = compute_gaps(tmp_path, called_tools=set())
        assert "edits_without_validation" in report["gaps"]
        assert "/tmp/snippet.py" not in report["edited_files_recent"]
        assert str(tmp_path / "src/a.py") in report["edited_files_recent"]

    def test_recent_compliant_loops_suppress_recurring_skip_gap(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        now = int(time.time())
        rows = []
        for i in range(4):
            rows.append(
                {
                    "ts": now - i,
                    "files_edited": ["src/a.py"],
                    "gate_skipped_files": ["src/a.py"],
                    "lookup_docs_called": False,
                    "checklist_called": False,
                    "tools_used": [],
                }
            )
        for i in range(6):
            rows.append(
                {
                    "ts": now - 20 - i,
                    "files_edited": ["src/a.py"],
                    "gate_skipped_files": [],
                    "lookup_docs_called": True,
                    "checklist_called": True,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                }
            )
        (metrics_dir / "loop-metrics.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n",
            encoding="utf-8",
        )
        report = compute_gaps(
            tmp_path,
            called_tools={"tapps_session_start", "tapps_validate_changed", "tapps_checklist"},
        )
        assert "recurring_validation_skips" not in report["gaps"]

    def test_legacy_callmcptool_rows_excluded_from_recurring_skip(
        self, tmp_path: Path
    ) -> None:
        """Pre-TAP-4017 Cursor rows should not inflate gate-skip rate (TAP-4017)."""
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        now = int(time.time())
        src = str(tmp_path / "packages" / "mod.py")
        rows = []
        for i in range(8):
            rows.append(
                {
                    "ts": now - i,
                    "files_edited": [src, "/tmp/snippet.py"],
                    "gate_skipped_files": [src, "/tmp/snippet.py"],
                    "lookup_docs_called": False,
                    "checklist_called": False,
                    "tools_used": ["CallMcpTool", "Write", "Shell"],
                    "mcp_calls": 0,
                }
            )
        for i in range(2):
            rows.append(
                {
                    "ts": now - 20 - i,
                    "files_edited": [src],
                    "gate_skipped_files": [],
                    "lookup_docs_called": True,
                    "checklist_called": True,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                    "mcp_calls": 2,
                }
            )
        (metrics_dir / "loop-metrics.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n",
            encoding="utf-8",
        )
        report = compute_gaps(
            tmp_path,
            called_tools={"tapps_session_start", "tapps_validate_changed", "tapps_checklist"},
        )
        assert "recurring_validation_skips" not in report["gaps"]


class TestFormatSessionStartGapHint:
    def test_returns_none_when_clean(self, tmp_path: Path) -> None:
        assert format_session_start_gap_hint(tmp_path) is None

    def test_surfaces_checklist_missing_from_violations(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        violations = metrics_dir / ".completion-gate-violations.jsonl"
        violations.write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "reasons": ["CHECKLIST_MISSING"],
                    "files_edited": ["src/a.py"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        hint = format_session_start_gap_hint(tmp_path)
        assert hint is not None
        assert "tapps_checklist" in hint

    def test_surfaces_loop_metric_gaps(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        loop_metrics = metrics_dir / "loop-metrics.jsonl"
        loop_metrics.write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": ["src/a.py"],
                    "mcp_calls": 1,
                    "gate_skipped_files": ["src/a.py"],
                    "lookup_docs_called": False,
                    "checklist_called": False,
                    "tools_used": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        hint = format_session_start_gap_hint(tmp_path)
        assert hint is not None
        assert "validation" in hint.lower() or "checklist" in hint.lower()
