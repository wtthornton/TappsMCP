"""Tests for document judge presets and bootstrap helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import yaml

from tapps_mcp.pipeline.document_judges import (
    DOCUMENT_BUILDER_PROFILE,
    discover_document_judge_preset,
    is_document_consumer,
    is_document_layout_path,
    merge_document_judges_into_yaml,
    merge_document_memory_profile,
    path_matches_narrative_glob,
    summarise_configured_judges,
)


class TestDocumentConsumerDetection:
    def test_bare_reports_dir_is_not_consumer(self, tmp_path: Path) -> None:
        (tmp_path / "reports").mkdir()
        assert is_document_consumer(tmp_path) is False

    def test_brands_and_templates_mark_consumer(self, tmp_path: Path) -> None:
        (tmp_path / "brands").mkdir()
        (tmp_path / "templates").mkdir()
        assert is_document_consumer(tmp_path) is True

    def test_non_consumer_without_markers(self, tmp_path: Path) -> None:
        assert is_document_consumer(tmp_path) is False


class TestJudgePresetDiscovery:
    def test_discovers_build_script_grep_judge(self, tmp_path: Path) -> None:
        (tmp_path / "brands").mkdir()
        (tmp_path / "templates").mkdir()
        build = tmp_path / "scripts" / "build-pdfs.mjs"
        build.parent.mkdir()
        build.write_text('import { exec } from "node:child_process";\nexec("node build --audit");\n')
        judges = discover_document_judge_preset(tmp_path)
        assert any(j["type"] == "grep" and "--audit" in j["expect"] for j in judges)
        assert all(j.get("blocking") is True for j in judges)

    def test_skips_node_modules_build_scripts(self, tmp_path: Path) -> None:
        (tmp_path / "brands").mkdir()
        (tmp_path / "templates").mkdir()
        junk = tmp_path / "node_modules" / "pkg" / "build-pdfs.mjs"
        junk.parent.mkdir(parents=True)
        junk.write_text("// --audit\n")
        real = tmp_path / "scripts" / "build-pdfs.mjs"
        real.parent.mkdir()
        real.write_text("// --audit\n")
        judges = discover_document_judge_preset(tmp_path)
        targets = [j.get("target", "") for j in judges if j["type"] == "grep"]
        assert any("scripts/build-pdfs.mjs" in t or str(real) in t for t in targets)
        assert not any("node_modules" in t for t in targets)

    def test_discovers_shell_audit_when_pdf_and_report_studio(self, tmp_path: Path) -> None:
        (tmp_path / "brands").mkdir()
        (tmp_path / "templates").mkdir()
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["nlt-report-studio>=0.1.3"]\n',
            encoding="utf-8",
        )
        pdf = tmp_path / "apps" / "docs" / "public" / "downloads" / "vol-06-sample.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"%PDF-1.4")

        judges = discover_document_judge_preset(tmp_path)
        shell = [j for j in judges if j["type"] == "shell"]
        assert len(shell) == 1
        assert "audit --profile reference" in shell[0]["target"]
        assert "vol-06-sample.pdf" in shell[0]["target"]
        assert shell[0]["when_changed"] == ["reports/**", "src/**", "brands/**", "templates/**"]

    def test_skips_shell_audit_without_reference_pdf(self, tmp_path: Path) -> None:
        (tmp_path / "brands").mkdir()
        (tmp_path / "templates").mkdir()
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["nlt-report-studio>=0.1.3"]\n',
            encoding="utf-8",
        )
        judges = discover_document_judge_preset(tmp_path)
        assert not any(j["type"] == "shell" for j in judges)


class TestMergeDocumentJudges:
    def test_merges_when_empty(self, tmp_path: Path) -> None:
        (tmp_path / "brands").mkdir()
        (tmp_path / "templates").mkdir()
        build = tmp_path / "build-pdfs.mjs"
        build.write_text("// --audit\n")
        result = merge_document_judges_into_yaml(tmp_path)
        assert result["merged"] is True
        config = yaml.safe_load((tmp_path / ".tapps-mcp.yaml").read_text())
        assert len(config["validate_changed"]["judges"]) >= 1

    def test_preserves_existing_judges(self, tmp_path: Path) -> None:
        (tmp_path / "brands").mkdir()
        (tmp_path / "templates").mkdir()
        (tmp_path / ".tapps-mcp.yaml").write_text(
            yaml.safe_dump({"validate_changed": {"judges": [{"type": "exists", "target": "x"}]}})
        )
        result = merge_document_judges_into_yaml(tmp_path)
        assert result["merged"] is False
        config = yaml.safe_load((tmp_path / ".tapps-mcp.yaml").read_text())
        assert config["validate_changed"]["judges"][0]["target"] == "x"


class TestMemoryProfile:
    def test_does_not_write_document_builder_profile(self, tmp_path: Path) -> None:
        (tmp_path / "brands").mkdir()
        (tmp_path / "templates").mkdir()
        result = merge_document_memory_profile(tmp_path)
        assert result["merged"] is False
        assert not (tmp_path / ".tapps-mcp.yaml").is_file()
        assert result["profile"] is None
        assert "leaving memory.profile unset" in " ".join(result["messages"])

    def test_preserves_existing_profile(self, tmp_path: Path) -> None:
        (tmp_path / "brands").mkdir()
        (tmp_path / "templates").mkdir()
        (tmp_path / ".tapps-mcp.yaml").write_text(
            yaml.safe_dump({"memory": {"profile": "repo-brain"}})
        )
        result = merge_document_memory_profile(tmp_path)
        assert result["merged"] is False
        config = yaml.safe_load((tmp_path / ".tapps-mcp.yaml").read_text())
        assert config["memory"]["profile"] == "repo-brain"


class TestSummariseConfiguredJudges:
    def test_empty(self) -> None:
        assert summarise_configured_judges([])["configured"] is False

    def test_counts_blocking(self) -> None:
        summary = summarise_configured_judges(
            [{"blocking": True}, {"blocking": False}]
        )
        assert summary == {"configured": True, "count": 2, "blocking": 1, "advisory": 1}


class TestPathHelpers:
    def test_layout_path_under_reports(self, tmp_path: Path) -> None:
        path = tmp_path / "reports" / "annual" / "page.tsx"
        path.parent.mkdir(parents=True)
        path.touch()
        assert is_document_layout_path(path, tmp_path) is True

    def test_narrative_glob_match(self, tmp_path: Path) -> None:
        path = tmp_path / "reports" / "foo.py"
        path.parent.mkdir(parents=True)
        path.touch()
        assert path_matches_narrative_glob(path, tmp_path, ["reports/**"]) is True

    def test_report_studio_installed_via_check(self, tmp_path: Path) -> None:
        with patch(
            "tapps_mcp.pipeline.document_judges.check_report_studio",
            return_value={"installed": True},
        ):
            assert is_document_consumer(tmp_path) is True


class TestDoctorReportStudioJudges:
    def test_installed_with_judges(self, tmp_path: Path, monkeypatch) -> None:
        from tapps_core.config.settings import TappsMCPSettings, ValidateChangedSettings
        from tapps_mcp.distribution.doctor import check_report_studio

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\ndependencies = ["nlt-report-studio>=1.0"]\n',
            encoding="utf-8",
        )
        (tmp_path / "reports").mkdir()

        settings = TappsMCPSettings(
            project_root=tmp_path,
            validate_changed=ValidateChangedSettings(
                judges=[{"type": "shell", "target": "true", "blocking": True}]
            ),
        )
        monkeypatch.setattr(
            "tapps_core.config.settings.load_settings",
            lambda **_: settings,
        )
        result = check_report_studio(tmp_path)
        assert result.ok is True
        assert "judges configured" in result.message

    def test_installed_without_judges(self, tmp_path: Path, monkeypatch) -> None:
        from tapps_core.config.settings import TappsMCPSettings, ValidateChangedSettings
        from tapps_mcp.distribution.doctor import check_report_studio

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\ndependencies = ["nlt-report-studio>=1.0"]\n',
            encoding="utf-8",
        )
        (tmp_path / "reports").mkdir()

        settings = TappsMCPSettings(
            project_root=tmp_path,
            validate_changed=ValidateChangedSettings(judges=[]),
        )
        monkeypatch.setattr(
            "tapps_core.config.settings.load_settings",
            lambda **_: settings,
        )
        result = check_report_studio(tmp_path)
        assert result.ok is True
        assert "judges missing" in result.message
