"""check_karpathy_guidelines must honour the two declared opt-out mechanisms.

Split out of ``test_karpathy_guidelines.py`` rather than appended to it: that
file is already past its own maintainability ceiling (line-count driven), so
adding tests there would regress an already-legacy-debt file instead of
covering new behaviour cleanly.

``upgrade`` honours two independent ways to decline the Karpathy block
(``.tapps-mcp.yaml`` -> ``include_karpathy_guidelines: false``, and the
``karpathy`` ``upgrade_skip_files`` token) via ``refresh_karpathy_blocks``,
but ``check_karpathy_guidelines`` read neither — it FAILed a project for a
state upgrade deliberately produced.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor import check_karpathy_guidelines


def test_doctor_check_passes_when_yaml_opts_out_and_block_absent(
    tmp_path: Path,
) -> None:
    """Negative control 1/2: ``include_karpathy_guidelines: false`` must not FAIL
    a project that never installed the block. Must fail on unfixed code, which
    hard-FAILs "missing in preferred home" regardless of the opt-out."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / ".tapps-mcp.yaml").write_text(
        "include_karpathy_guidelines: false\n", encoding="utf-8"
    )

    result = check_karpathy_guidelines(tmp_path)
    assert result.ok, result.message
    assert "skipped" in result.message.lower()
    assert "include_karpathy_guidelines" in result.message


def test_doctor_check_passes_when_skip_token_opts_out_and_block_absent(
    tmp_path: Path,
) -> None:
    """Negative control 2/2: the ``karpathy`` ``upgrade_skip_files`` token must
    not FAIL a project that never installed the block. Distinct mechanism from
    the yaml flag above — one passing does not cover the other."""
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (tmp_path / ".tapps-mcp.yaml").write_text(
        "upgrade_skip_files:\n  - karpathy\n", encoding="utf-8"
    )

    result = check_karpathy_guidelines(tmp_path)
    assert result.ok, result.message
    assert "skipped" in result.message.lower()
    assert "upgrade_skip_files" in result.message


def test_doctor_check_still_fails_when_not_opted_out_and_block_missing(
    tmp_path: Path,
) -> None:
    """Coverage control: no opt-out declared, block missing -> still FAILs.

    This fixture never sets ``include_karpathy_guidelines`` or
    ``upgrade_skip_files``, so the opt-out branch must not apply.
    """
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")

    result = check_karpathy_guidelines(tmp_path)
    assert not result.ok
    assert "missing in preferred home" in result.message


def test_doctor_check_still_reports_stale_block_when_opted_out(
    tmp_path: Path,
) -> None:
    """Coverage control: opting out is not a licence to ignore a block that is
    actually present and stale. This fixture never creates a "block absent"
    state — the preferred home carries a real, out-of-date block — so the
    opt-out skip path must not swallow it."""
    (tmp_path / "AGENTS.md").write_text(
        "# AGENTS\n\n"
        "<!-- BEGIN: karpathy-guidelines deadbee "
        "(MIT, forrestchang/andrej-karpathy-skills) -->\n"
        "old body\n"
        "<!-- END: karpathy-guidelines -->\n",
        encoding="utf-8",
    )
    (tmp_path / ".tapps-mcp.yaml").write_text(
        "include_karpathy_guidelines: false\n", encoding="utf-8"
    )

    result = check_karpathy_guidelines(tmp_path)
    assert not result.ok
    assert "deadbee" in result.message
