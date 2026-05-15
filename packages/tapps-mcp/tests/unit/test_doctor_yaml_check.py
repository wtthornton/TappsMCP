"""TAP-1787: doctor surfaces ``.tapps-mcp.yaml`` parse failures."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor import check_tapps_mcp_yaml, run_doctor_structured


def test_check_passes_when_yaml_absent(tmp_path: Path) -> None:
    result = check_tapps_mcp_yaml(tmp_path)
    assert result.ok
    assert "not present" in result.message


def test_check_passes_when_yaml_valid(tmp_path: Path) -> None:
    (tmp_path / ".tapps-mcp.yaml").write_text(
        "quality_preset: strict\nlinear_enforce_gate: true\n", encoding="utf-8"
    )
    result = check_tapps_mcp_yaml(tmp_path)
    assert result.ok
    assert "parses cleanly" in result.message


def test_check_fails_when_yaml_unparseable(tmp_path: Path) -> None:
    (tmp_path / ".tapps-mcp.yaml").write_text(
        # tab-indented key after a regular indent — yaml.YAMLError
        "memory:\n  safety: enforce\n\t: bad_indent\n",
        encoding="utf-8",
    )
    result = check_tapps_mcp_yaml(tmp_path)
    assert not result.ok, "doctor must flag YAML parse failure"
    assert "fell back to defaults" in result.message
    assert result.detail, "doctor should surface the parse reason in detail"


def test_run_doctor_structured_includes_yaml_check(tmp_path: Path) -> None:
    (tmp_path / ".tapps-mcp.yaml").write_text(
        "memory:\n  safety: enforce\n\t: bad_indent\n",
        encoding="utf-8",
    )
    out = run_doctor_structured(project_root=str(tmp_path), quick=True)
    names = {c["name"] for c in out["checks"]}
    assert ".tapps-mcp.yaml" in names
    yaml_check = next(c for c in out["checks"] if c["name"] == ".tapps-mcp.yaml")
    assert yaml_check["ok"] is False
