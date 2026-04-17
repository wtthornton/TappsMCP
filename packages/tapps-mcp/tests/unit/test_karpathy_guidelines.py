"""Tests for the vendored Karpathy guidelines block: loader + install/refresh + doctor."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.distribution.doctor import check_karpathy_guidelines
from tapps_mcp.pipeline import karpathy_block
from tapps_mcp.prompts.prompt_loader import (
    KARPATHY_GUIDELINES_MARKER_BEGIN,
    KARPATHY_GUIDELINES_MARKER_END,
    KARPATHY_GUIDELINES_SOURCE_SHA,
    load_karpathy_guidelines,
)

# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def test_load_karpathy_guidelines_has_pinned_sha() -> None:
    assert len(KARPATHY_GUIDELINES_SOURCE_SHA) == 40
    assert all(c in "0123456789abcdef" for c in KARPATHY_GUIDELINES_SOURCE_SHA)


def test_load_karpathy_guidelines_wraps_in_markers() -> None:
    block = load_karpathy_guidelines()
    assert block.startswith(KARPATHY_GUIDELINES_MARKER_BEGIN)
    assert block.endswith(KARPATHY_GUIDELINES_MARKER_END)
    # Both markers present exactly once each
    assert block.count(KARPATHY_GUIDELINES_MARKER_BEGIN) == 1
    assert block.count(KARPATHY_GUIDELINES_MARKER_END) == 1


def test_load_karpathy_guidelines_contains_all_four_principles() -> None:
    block = load_karpathy_guidelines()
    assert "Think Before Coding" in block
    assert "Simplicity First" in block
    assert "Surgical Changes" in block
    assert "Goal-Driven Execution" in block


def test_load_karpathy_guidelines_preserves_attribution() -> None:
    block = load_karpathy_guidelines()
    assert "forrestchang/andrej-karpathy-skills" in block
    assert KARPATHY_GUIDELINES_SOURCE_SHA in block


# ---------------------------------------------------------------------------
# install_or_refresh
# ---------------------------------------------------------------------------


def test_install_skips_when_file_missing(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    action = karpathy_block.install_or_refresh(target)
    assert action == "skipped_file_missing"
    assert not target.exists()


def test_install_adds_block_when_absent(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("# AGENTS\n\nproject-specific content.\n", encoding="utf-8")

    action = karpathy_block.install_or_refresh(target)
    assert action == "added"

    content = target.read_text(encoding="utf-8")
    assert "project-specific content." in content  # user content preserved
    assert KARPATHY_GUIDELINES_MARKER_BEGIN in content
    assert KARPATHY_GUIDELINES_MARKER_END in content


def test_install_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("# AGENTS\n", encoding="utf-8")

    first = karpathy_block.install_or_refresh(target)
    after_first = target.read_text(encoding="utf-8")

    second = karpathy_block.install_or_refresh(target)
    after_second = target.read_text(encoding="utf-8")

    assert first == "added"
    assert second == "unchanged"
    assert after_first == after_second
    # Markers still present exactly once
    assert after_second.count(KARPATHY_GUIDELINES_MARKER_BEGIN) == 1
    assert after_second.count(KARPATHY_GUIDELINES_MARKER_END) == 1


def test_install_refreshes_stale_block(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    stale_block = (
        "<!-- BEGIN: karpathy-guidelines 0000000 "
        "(MIT, forrestchang/andrej-karpathy-skills) -->\n"
        "## Karpathy Behavioral Guidelines\n\n"
        "Stale content from an older vendor.\n"
        "<!-- END: karpathy-guidelines -->"
    )
    target.write_text(
        f"# AGENTS\n\nkept preamble.\n\n{stale_block}\n\ntrailing user content.\n",
        encoding="utf-8",
    )

    action = karpathy_block.install_or_refresh(target)
    assert action == "refreshed"

    content = target.read_text(encoding="utf-8")
    # Refreshed: old SHA prefix gone, new SHA present
    assert "0000000" not in content
    assert KARPATHY_GUIDELINES_SOURCE_SHA[:7] in content
    # Surrounding user content preserved
    assert "kept preamble." in content
    assert "trailing user content." in content
    # Still exactly one block
    assert content.count(KARPATHY_GUIDELINES_MARKER_END) == 1


def test_install_dry_run_does_not_write(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    original = "# AGENTS\n\ncontent.\n"
    target.write_text(original, encoding="utf-8")

    action = karpathy_block.install_or_refresh(target, dry_run=True)
    assert action == "added"
    assert target.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# check (doctor)
# ---------------------------------------------------------------------------


def test_check_reports_file_absent(tmp_path: Path) -> None:
    report = karpathy_block.check(tmp_path / "AGENTS.md")
    assert report["state"] == "file_absent"
    assert report["current_sha"] is None
    assert report["expected_sha"] == KARPATHY_GUIDELINES_SOURCE_SHA


def test_check_reports_missing(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("# AGENTS\nno block here.\n", encoding="utf-8")

    report = karpathy_block.check(target)
    assert report["state"] == "missing"
    assert report["current_sha"] is None


def test_check_reports_ok_after_install(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    target.write_text("# AGENTS\n", encoding="utf-8")
    karpathy_block.install_or_refresh(target)

    report = karpathy_block.check(target)
    assert report["state"] == "ok"
    assert report["current_sha"] == KARPATHY_GUIDELINES_SOURCE_SHA[:7]


def test_check_reports_stale_when_sha_mismatch(tmp_path: Path) -> None:
    target = tmp_path / "AGENTS.md"
    stale = (
        "# AGENTS\n\n"
        "<!-- BEGIN: karpathy-guidelines deadbee "
        "(MIT, forrestchang/andrej-karpathy-skills) -->\n"
        "stale body\n"
        "<!-- END: karpathy-guidelines -->\n"
    )
    target.write_text(stale, encoding="utf-8")

    report = karpathy_block.check(target)
    assert report["state"] == "stale"
    assert report["current_sha"] == "deadbee"


# ---------------------------------------------------------------------------
# doctor.check_karpathy_guidelines integration
# ---------------------------------------------------------------------------


def test_doctor_check_passes_when_block_present(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# AGENTS\n", encoding="utf-8")
    karpathy_block.install_or_refresh(agents)

    result = check_karpathy_guidelines(tmp_path)
    assert result.ok
    assert "Karpathy guidelines" in result.name
    assert KARPATHY_GUIDELINES_SOURCE_SHA[:7] in result.message


def test_doctor_check_fails_when_block_missing(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    result = check_karpathy_guidelines(tmp_path)
    assert not result.ok
    assert "tapps_upgrade" in result.detail


def test_doctor_check_fails_when_block_stale(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text(
        "# AGENTS\n\n"
        "<!-- BEGIN: karpathy-guidelines deadbee "
        "(MIT, forrestchang/andrej-karpathy-skills) -->\n"
        "old body\n"
        "<!-- END: karpathy-guidelines -->\n",
        encoding="utf-8",
    )
    result = check_karpathy_guidelines(tmp_path)
    assert not result.ok
    assert "deadbee" in result.message
    assert "tapps_upgrade" in result.detail


# ---------------------------------------------------------------------------
# init/upgrade wiring
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_init_installs_block_into_new_agents_md(tmp_path: Path) -> None:
    from tapps_mcp.pipeline.init import BootstrapConfig, bootstrap_pipeline

    cfg = BootstrapConfig(
        create_handoff=False,
        create_runlog=False,
        create_agents_md=True,
        create_tech_stack_md=False,
        platform="",
        verify_server=False,
        install_missing_checkers=False,
        warm_cache_from_tech_stack=False,
        warm_expert_rag_from_tech_stack=False,
        include_karpathy=True,
    )
    result = bootstrap_pipeline(tmp_path, config=cfg)

    agents = tmp_path / "AGENTS.md"
    assert agents.exists()
    content = agents.read_text(encoding="utf-8")
    assert KARPATHY_GUIDELINES_MARKER_BEGIN in content
    kp = result["karpathy_guidelines"]
    assert kp["source_sha"] == KARPATHY_GUIDELINES_SOURCE_SHA
    assert kp["files"]["AGENTS.md"] in {"added", "unchanged"}
    # No CLAUDE.md was created (platform=""), so it should be skipped
    assert kp["files"]["CLAUDE.md"] == "skipped_file_missing"


@pytest.mark.slow
def test_init_installs_block_into_both_files_when_claude_md_present(tmp_path: Path) -> None:
    from tapps_mcp.pipeline.init import BootstrapConfig, bootstrap_pipeline

    # Pre-create a user-owned CLAUDE.md to simulate a project that uses Claude Code
    (tmp_path / "CLAUDE.md").write_text(
        "# CLAUDE.md\n\nuser-owned preamble that must survive.\n",
        encoding="utf-8",
    )

    cfg = BootstrapConfig(
        create_handoff=False,
        create_runlog=False,
        create_agents_md=True,
        create_tech_stack_md=False,
        platform="",  # don't run platform bootstrap; we just want the karpathy step
        verify_server=False,
        install_missing_checkers=False,
        warm_cache_from_tech_stack=False,
        warm_expert_rag_from_tech_stack=False,
        include_karpathy=True,
    )
    result = bootstrap_pipeline(tmp_path, config=cfg)

    claude = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "user-owned preamble that must survive." in claude  # user content preserved
    assert KARPATHY_GUIDELINES_MARKER_BEGIN in claude

    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert KARPATHY_GUIDELINES_MARKER_BEGIN in agents

    kp = result["karpathy_guidelines"]
    assert kp["files"]["AGENTS.md"] in {"added", "unchanged"}
    assert kp["files"]["CLAUDE.md"] == "added"


@pytest.mark.slow
def test_init_skips_block_when_include_karpathy_false(tmp_path: Path) -> None:
    from tapps_mcp.pipeline.init import BootstrapConfig, bootstrap_pipeline

    # CLAUDE.md present too — must also be left alone
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")

    cfg = BootstrapConfig(
        create_handoff=False,
        create_runlog=False,
        create_agents_md=True,
        create_tech_stack_md=False,
        platform="",
        verify_server=False,
        install_missing_checkers=False,
        warm_cache_from_tech_stack=False,
        warm_expert_rag_from_tech_stack=False,
        include_karpathy=False,
    )
    result = bootstrap_pipeline(tmp_path, config=cfg)

    assert KARPATHY_GUIDELINES_MARKER_BEGIN not in (tmp_path / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    assert KARPATHY_GUIDELINES_MARKER_BEGIN not in (tmp_path / "CLAUDE.md").read_text(
        encoding="utf-8"
    )
    assert result["karpathy_guidelines"]["action"] == "skipped"


def test_upgrade_refreshes_stale_block_in_both_files(tmp_path: Path) -> None:
    from tapps_mcp.pipeline.upgrade import _refresh_karpathy_blocks

    stale = (
        "<!-- BEGIN: karpathy-guidelines deadbee "
        "(MIT, forrestchang/andrej-karpathy-skills) -->\n"
        "stale\n"
        "<!-- END: karpathy-guidelines -->\n"
    )
    (tmp_path / "AGENTS.md").write_text(f"# AGENTS\n\n{stale}", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(f"# CLAUDE\n\n{stale}", encoding="utf-8")

    result = _refresh_karpathy_blocks(tmp_path, dry_run=False)
    assert result["source_sha"] == KARPATHY_GUIDELINES_SOURCE_SHA
    assert result["files"]["AGENTS.md"] == "refreshed"
    assert result["files"]["CLAUDE.md"] == "refreshed"

    for name in ("AGENTS.md", "CLAUDE.md"):
        content = (tmp_path / name).read_text(encoding="utf-8")
        assert "deadbee" not in content
        assert KARPATHY_GUIDELINES_SOURCE_SHA[:7] in content


def test_upgrade_skips_missing_files(tmp_path: Path) -> None:
    from tapps_mcp.pipeline.upgrade import _refresh_karpathy_blocks

    result = _refresh_karpathy_blocks(tmp_path, dry_run=False)
    assert result["files"]["AGENTS.md"] == "skipped_file_missing"
    assert result["files"]["CLAUDE.md"] == "skipped_file_missing"


# ---------------------------------------------------------------------------
# doctor: dual-file states
# ---------------------------------------------------------------------------


def test_doctor_check_fails_when_both_files_missing(tmp_path: Path) -> None:
    result = check_karpathy_guidelines(tmp_path)
    assert not result.ok
    assert "Neither AGENTS.md nor CLAUDE.md" in result.message
    assert "tapps_init" in result.detail


def test_doctor_check_passes_when_both_files_have_block(tmp_path: Path) -> None:
    for name in ("AGENTS.md", "CLAUDE.md"):
        p = tmp_path / name
        p.write_text(f"# {name}\n", encoding="utf-8")
        karpathy_block.install_or_refresh(p)

    result = check_karpathy_guidelines(tmp_path)
    assert result.ok
    assert "AGENTS.md" in result.message
    assert "CLAUDE.md" in result.message


def test_doctor_check_fails_when_one_file_missing_block(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# AGENTS\n", encoding="utf-8")
    karpathy_block.install_or_refresh(agents)
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")

    result = check_karpathy_guidelines(tmp_path)
    assert not result.ok
    assert "CLAUDE.md" in result.message
    assert "missing" in result.message
    assert "tapps_upgrade" in result.detail


def test_doctor_check_fails_when_one_file_stale(tmp_path: Path) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# AGENTS\n", encoding="utf-8")
    karpathy_block.install_or_refresh(agents)
    (tmp_path / "CLAUDE.md").write_text(
        "# CLAUDE\n\n"
        "<!-- BEGIN: karpathy-guidelines deadbee "
        "(MIT, forrestchang/andrej-karpathy-skills) -->\nold\n"
        "<!-- END: karpathy-guidelines -->\n",
        encoding="utf-8",
    )

    result = check_karpathy_guidelines(tmp_path)
    assert not result.ok
    assert "stale" in result.message
    assert "CLAUDE.md@deadbee" in result.message
