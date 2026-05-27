"""Integration tests for the pre-push brain version floor check (TAP-1923).

Covers three scenarios from the acceptance criteria:
  1. Floor parse — the hook correctly extracts the tapps-brain floor from TOML.
  2. Reject    — floors below 3.18.0 cause the hook to exit non-zero.
  3. Bypass    — TAPPS_SKIP_PREPUSH=1 bypasses the floor check.

The hook requires git-ref stdin and remote args to reach the floor-check
section, so the tests use a thin wrapper script that replays only the
brain-floor block. The wrapper is generated from the actual pre-push hook
source to stay in sync as the hook evolves.
"""
from __future__ import annotations

import re
import subprocess
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HOOK_PATH = Path(__file__).parents[4] / ".githooks" / "pre-push"
_REQUIRED_FLOOR = "3.18.0"
_FLOOR_SECTION_START = "# --- tapps-brain version floor check"
_FLOOR_SECTION_END = "# --- Tier 1: fast gate"


def _extract_floor_section(hook_text: str) -> str:
    """Pull the brain-floor block out of the pre-push hook source.

    Raises RuntimeError if the markers are not found (the hook changed
    without updating this test file).
    """
    start = hook_text.find(_FLOOR_SECTION_START)
    end = hook_text.find(_FLOOR_SECTION_END)
    if start == -1 or end == -1:
        raise RuntimeError(  # pragma: no cover
            "Brain-floor markers not found in .githooks/pre-push — "
            "update _FLOOR_SECTION_START / _FLOOR_SECTION_END in this test."
        )
    return hook_text[start:end]


def _make_wrapper(toml_path: Path, skip_prepush: str = "") -> str:
    """Return a bash script that runs just the floor check against toml_path.

    The wrapper includes a minimal replica of the pre-push bypass block so
    that ``TAPPS_SKIP_PREPUSH`` tests exercise the same early-exit semantics
    as the real hook without needing a git environment.
    """
    hook_text = _HOOK_PATH.read_text(encoding="utf-8")
    floor_block = _extract_floor_section(hook_text)
    # Inject the TOML path and optional bypass flag.
    env_lines = [f'TAPPS_CORE_PYPROJECT="{toml_path}"']
    if skip_prepush:
        env_lines.append(f"TAPPS_SKIP_PREPUSH={skip_prepush!r}")
    env_export = "\n".join(env_lines)
    # Replicate the bypass block that lives before the floor check in the
    # real hook so TAPPS_SKIP_PREPUSH short-circuits correctly.
    bypass_block = textwrap.dedent("""\
        if [[ -n "${TAPPS_SKIP_PREPUSH:-}" ]]; then
          echo "[pre-push] TAPPS_SKIP_PREPUSH set; skipping gate." >&2
          exit 0
        fi
    """)
    return textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -e
        {env_export}
        {bypass_block}
        {floor_block}
        exit 0
    """)


def _run_wrapper(wrapper_script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", wrapper_script],
        capture_output=True,
        text=True,
    )


def _make_toml(tmp_path: Path, floor: str) -> Path:
    """Write a minimal pyproject.toml snippet with the given brain floor."""
    p = tmp_path / "pyproject.toml"
    p.write_text(
        f'dependencies = [\n    "tapps-brain>={floor},<4",\n]\n',
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPrepushBrainFloor:
    """TAP-1923: pre-push gate enforces tapps-brain>={_REQUIRED_FLOOR} floor."""

    # -- Floor parse ---------------------------------------------------------

    def test_actual_pyproject_floor_meets_requirement(self) -> None:
        """The real tapps-core/pyproject.toml pin satisfies the floor."""
        core_toml = (
            Path(__file__).parents[4]
            / "packages"
            / "tapps-core"
            / "pyproject.toml"
        )
        text = core_toml.read_text(encoding="utf-8")
        match = re.search(r'tapps-brain>=([\d]+\.[\d]+\.[\d]+)', text)
        assert match is not None, "tapps-brain floor not found in tapps-core/pyproject.toml"
        actual_floor = match.group(1)
        # Compare using tuple int conversion — safe for X.Y.Z semver.
        actual = tuple(int(x) for x in actual_floor.split("."))
        required = tuple(int(x) for x in _REQUIRED_FLOOR.split("."))
        assert actual >= required, (
            f"tapps-brain floor {actual_floor} < required {_REQUIRED_FLOOR}; "
            "bump the floor in packages/tapps-core/pyproject.toml"
        )

    def test_hook_contains_floor_section(self) -> None:
        """The pre-push hook source contains the brain-floor check block."""
        hook_text = _HOOK_PATH.read_text(encoding="utf-8")
        assert _FLOOR_SECTION_START in hook_text, (
            "Brain-floor section missing from .githooks/pre-push"
        )
        assert _REQUIRED_FLOOR in hook_text, (
            f"Required floor {_REQUIRED_FLOOR} not referenced in pre-push hook"
        )

    # -- Reject (floor < minimum) -------------------------------------------

    def test_rejects_floor_below_minimum(self, tmp_path: Path) -> None:
        """Hook exits 1 and prints an actionable message when floor < 3.18.0."""
        toml = _make_toml(tmp_path, "3.17.0")
        result = _run_wrapper(_make_wrapper(toml))
        assert result.returncode != 0, "Expected non-zero exit for floor 3.17.0"
        assert "3.17.0" in result.stderr, "Error message should name the bad floor"
        assert _REQUIRED_FLOOR in result.stderr, "Error message should name the required floor"

    def test_rejects_floor_at_3_0_0(self, tmp_path: Path) -> None:
        """Even a very old floor (3.0.0) is rejected cleanly."""
        toml = _make_toml(tmp_path, "3.0.0")
        result = _run_wrapper(_make_wrapper(toml))
        assert result.returncode != 0
        assert "BRAIN FLOOR REGRESSION" in result.stderr

    def test_rejects_floor_one_patch_below(self, tmp_path: Path) -> None:
        """3.17.9 — one patch below required — is still rejected."""
        toml = _make_toml(tmp_path, "3.17.9")
        result = _run_wrapper(_make_wrapper(toml))
        assert result.returncode != 0

    # -- Accept (floor >= minimum) ------------------------------------------

    def test_accepts_exact_minimum_floor(self, tmp_path: Path) -> None:
        """Exactly 3.18.0 passes the floor check."""
        toml = _make_toml(tmp_path, "3.18.0")
        result = _run_wrapper(_make_wrapper(toml))
        assert result.returncode == 0, f"Unexpected failure: {result.stderr}"

    def test_accepts_newer_floor(self, tmp_path: Path) -> None:
        """A newer floor (e.g. 3.20.0) passes the floor check."""
        toml = _make_toml(tmp_path, "3.20.0")
        result = _run_wrapper(_make_wrapper(toml))
        assert result.returncode == 0

    def test_accepts_minor_bump(self, tmp_path: Path) -> None:
        """3.19.0 (one minor above) passes the floor check."""
        toml = _make_toml(tmp_path, "3.19.0")
        result = _run_wrapper(_make_wrapper(toml))
        assert result.returncode == 0

    # -- Bypass (TAPPS_SKIP_PREPUSH) -----------------------------------------

    def test_bypass_skips_floor_check(self, tmp_path: Path) -> None:
        """TAPPS_SKIP_PREPUSH=1 skips the floor check even for a low floor."""
        toml = _make_toml(tmp_path, "3.17.0")
        # TAPPS_SKIP_PREPUSH causes the hook to exit 0 before reaching the
        # floor check, so we pass it via env rather than inline the entire
        # hook preamble.  The wrapper re-exports it into the sub-shell.
        result = _run_wrapper(_make_wrapper(toml, skip_prepush="1"))
        # The bypass logic exits 0 with an informational log; the floor check
        # itself is never reached, so no failure even with bad floor.
        assert result.returncode == 0

    # -- Edge cases ----------------------------------------------------------

    def test_missing_toml_is_silently_skipped(self, tmp_path: Path) -> None:
        """If the TOML doesn't exist the check is skipped (not a hard error)."""
        missing = tmp_path / "nonexistent.toml"
        result = _run_wrapper(_make_wrapper(missing))
        assert result.returncode == 0

    def test_toml_without_brain_dep_is_skipped(self, tmp_path: Path) -> None:
        """A TOML that has no tapps-brain line passes without error."""
        p = tmp_path / "pyproject.toml"
        p.write_text('dependencies = [\n    "pydantic>=2.0",\n]\n', encoding="utf-8")
        result = _run_wrapper(_make_wrapper(p))
        assert result.returncode == 0
