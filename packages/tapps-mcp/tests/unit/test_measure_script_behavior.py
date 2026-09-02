"""Functional behavior tests for the scaffolded ``scripts/measure.py`` (TAP-6884).

Runs the file exactly as scaffolded by ``generate_measure_script`` (managed-block
header + markers included, not the bare staged source) via subprocess, with an
explicit interpreter — ``python3 scripts/measure.py ...`` — because the
managed-block header/marker lines land ahead of the body's own ``#!`` shebang
(see the module docstring on :mod:`tapps_mcp.pipeline.platform_project_scripts`
for why direct ``./scripts/measure.py`` execution is a known, out-of-scope
limitation of the shipped asset class).

Covers evidence-bar items 1-3:

1. Exits non-zero and prints no results when ``--expect`` is not present among
   the found records (the known-positive assertion fails).
2. Prints files matched / records found / distinct groups on every successful
   run — the denominator, always.
3. A wrong ``--key`` never returns bare empty output — it names the specific
   file it checked and explains what to verify next. (A discovered pre-existing
   defect in the staged "proven" source — the "the key DOES exist at: <path>"
   sub-branch is unreachable dead code, proven in the PR body — is NOT patched
   here; see the module docstring. This test asserts the actual, reachable
   behavior only.)

Every item is asserted failing (refusal path) *and* passing (success path), per
the lane's evidence bar.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tapps_mcp.pipeline.platform_project_scripts import MEASURE_PY_REL_PATH
from tapps_mcp.pipeline.platform_project_scripts import (
    generate_measure_script as _generate_measure_script,
)


def _scaffold(tmp_path: Path) -> Path:
    """Install the scaffolded measure.py under tmp_path and return its path."""
    _generate_measure_script(tmp_path)
    return tmp_path / MEASURE_PY_REL_PATH


def _run(script: Path, repo: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), "--repo", str(repo), *extra_args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _plant_manifest(repo: Path, rel: str, payload: dict) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")


class TestEvidenceItem1ExpectIsMandatoryAndValidated:
    """``--expect`` names a known-positive value; when it's absent from the
    data actually found, the probe refuses to report a (possibly wrong) result."""

    def test_expect_value_absent_from_data_fails_and_prints_no_results(
        self, tmp_path: Path
    ) -> None:
        script = _scaffold(tmp_path)
        repo = tmp_path / "target-repo"
        _plant_manifest(
            repo,
            "data/manifest.json",
            {"curation": {"auto_qa": {"metrics": {"clipped_fraction": 0.5}}}},
        )

        result = _run(
            script, repo, "--files", "data/*.json", "--key", "clipped_fraction", "--expect", "0.999"
        )

        assert result.returncode != 0, result.stdout
        assert "PROBE INVALID" in result.stdout
        assert "expected value" in result.stdout
        assert "distinct groups" not in result.stdout, (
            "no results section should print when the known-positive assertion fails:\n"
            f"{result.stdout}"
        )

    def test_expect_value_present_succeeds(self, tmp_path: Path) -> None:
        script = _scaffold(tmp_path)
        repo = tmp_path / "target-repo"
        _plant_manifest(
            repo,
            "data/manifest.json",
            {"curation": {"auto_qa": {"metrics": {"clipped_fraction": 0.982345}}}},
        )

        result = _run(
            script,
            repo,
            "--files",
            "data/*.json",
            "--key",
            "clipped_fraction",
            "--expect",
            "0.982345",
        )

        assert result.returncode == 0, result.stdout
        assert "assertion       : PASSED" in result.stdout


class TestEvidenceItem2DenominatorAlwaysPrinted:
    """files matched / records found / distinct groups on every successful run."""

    def test_successful_run_prints_full_denominator(self, tmp_path: Path) -> None:
        script = _scaffold(tmp_path)
        repo = tmp_path / "target-repo"
        _plant_manifest(
            repo,
            "merch-lines/line-a/manifest.json",
            {"metrics": {"gate_state": "failed"}},
        )
        _plant_manifest(
            repo,
            "merch-lines/line-b/manifest.json",
            {"metrics": {"gate_state": "passed"}},
        )

        result = _run(
            script,
            repo,
            "--files",
            "merch-lines/**/manifest.json",
            "--key",
            "gate_state",
            "--expect",
            "failed",
        )

        assert result.returncode == 0, result.stdout
        assert "files matched   : 2" in result.stdout
        assert "records found   : 2" in result.stdout
        assert "distinct groups : 2" in result.stdout


class TestEvidenceItem3WrongKeyNamesWhatItChecked:
    def test_wrong_key_names_the_first_matched_file_it_checked(self, tmp_path: Path) -> None:
        script = _scaffold(tmp_path)
        repo = tmp_path / "target-repo"
        _plant_manifest(
            repo,
            "data/manifest.json",
            {"curation": {"auto_qa": {"metrics": {"clipped_fraction": 0.982345}}}},
        )

        result = _run(
            script,
            repo,
            "--files",
            "data/*.json",
            "--key",
            "clip_fraction_typo",
            "--expect",
            "0.982345",
        )

        assert result.returncode != 0, result.stdout
        assert "PROBE FAILED: key 'clip_fraction_typo' not found in any matched file." in (
            result.stdout
        )
        # Never a bare empty result: it names the specific file it checked.
        assert "Not present in data/manifest.json either." in result.stdout
        assert "records found   : 0" in result.stdout

    def test_correct_key_on_the_same_data_succeeds(self, tmp_path: Path) -> None:
        script = _scaffold(tmp_path)
        repo = tmp_path / "target-repo"
        _plant_manifest(
            repo,
            "data/manifest.json",
            {"curation": {"auto_qa": {"metrics": {"clipped_fraction": 0.982345}}}},
        )

        result = _run(
            script,
            repo,
            "--files",
            "data/*.json",
            "--key",
            "clipped_fraction",
            "--expect",
            "0.982345",
        )

        assert result.returncode == 0, result.stdout
        assert "records found   : 1" in result.stdout
