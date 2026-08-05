"""Integration tests for the pre-push brain version floor check (TAP-1923).

Covers three scenarios from the acceptance criteria:
  1. Floor parse — the hook correctly extracts the tapps-brain floor from TOML.
  2. Reject    — floors below the hook's floor cause a non-zero exit.
  3. Bypass    — TAPPS_SKIP_PREPUSH=1 bypasses the floor check.

The hook requires git-ref stdin and remote args to reach the floor-check
section, so the tests use a thin wrapper script that replays only the
brain-floor block. The wrapper is generated from the actual pre-push hook
source to stay in sync as the hook evolves.

The operational floor is **read from the hook** rather than duplicated here.
Hardcoding it drifted three times (3.18.0 → 3.24.0 → 3.28.0) because the floor
moves in the hook and pyproject while this file was left behind, so the suite
asserted a floor the project had already abandoned. The only constant that
stays pinned is the policy minimum from ADR-0033, which the hook must never
drop below.
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
_FLOOR_SECTION_START = "# --- tapps-brain version floor check"
_FLOOR_SECTION_END = "# --- Smoke gate ---"

# The minimum the hook's floor is allowed to be, per ADR-0033 (supersedes
# ADR-0013's 3.24.0). Raising the operational floor is fine; dropping below
# this is the regression the gate exists to catch.
_ADR_MINIMUM_FLOOR = "3.28.0"


def _parse_hook_floor() -> str:
    """Read ``_REQUIRED_BRAIN_FLOOR`` out of the pre-push hook source."""
    hook_text = _HOOK_PATH.read_text(encoding="utf-8")
    match = re.search(r'_REQUIRED_BRAIN_FLOOR="(\d+\.\d+\.\d+)"', hook_text)
    if match is None:  # pragma: no cover — hook restructured
        raise RuntimeError(
            "_REQUIRED_BRAIN_FLOOR not found in .githooks/pre-push — "
            "update _parse_hook_floor() in this test."
        )
    return match.group(1)


_REQUIRED_FLOOR = _parse_hook_floor()


def _as_tuple(version: str) -> tuple[int, ...]:
    """Convert an ``X.Y.Z`` version string to a comparable int tuple."""
    return tuple(int(part) for part in version.split("."))


def _offset_version(version: str, *, minor: int = 0, patch: int = 0) -> str:
    """Return ``version`` shifted by the given minor/patch deltas.

    Fixtures are derived from the live floor so they keep testing "just below"
    and "just above" no matter where the floor moves.
    """
    major_v, minor_v, patch_v = _as_tuple(version)
    shifted = (major_v, minor_v + minor, patch_v + patch)
    if any(part < 0 for part in shifted):  # pragma: no cover — floor too low
        raise ValueError(f"Cannot offset {version} by minor={minor}, patch={patch}")
    return "{}.{}.{}".format(*shifted)


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
    """TAP-1923: pre-push gate enforces the tapps-brain version floor."""

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
        assert _as_tuple(actual_floor) >= _as_tuple(_REQUIRED_FLOOR), (
            f"tapps-brain floor {actual_floor} < required {_REQUIRED_FLOOR}; "
            "bump the floor in packages/tapps-core/pyproject.toml"
        )

    def test_hook_contains_floor_section(self) -> None:
        """The pre-push hook source contains the brain-floor check block."""
        hook_text = _HOOK_PATH.read_text(encoding="utf-8")
        assert _FLOOR_SECTION_START in hook_text, (
            "Brain-floor section missing from .githooks/pre-push"
        )

    def test_hook_floor_not_below_adr_minimum(self) -> None:
        """The hook's floor never regresses below the ADR-0033 minimum."""
        assert _as_tuple(_REQUIRED_FLOOR) >= _as_tuple(_ADR_MINIMUM_FLOOR), (
            f"pre-push floor {_REQUIRED_FLOOR} is below the ADR-0033 minimum "
            f"{_ADR_MINIMUM_FLOOR}; supersede the ADR before lowering it"
        )

    # -- Reject (floor < minimum) -------------------------------------------

    def test_rejects_floor_below_minimum(self, tmp_path: Path) -> None:
        """Hook exits 1 with an actionable message when the floor is too low."""
        bad_floor = _offset_version(_REQUIRED_FLOOR, minor=-1)
        toml = _make_toml(tmp_path, bad_floor)
        result = _run_wrapper(_make_wrapper(toml))
        assert result.returncode != 0, f"Expected non-zero exit for floor {bad_floor}"
        assert bad_floor in result.stderr, "Error message should name the bad floor"
        assert _REQUIRED_FLOOR in result.stderr, "Error message should name the required floor"

    def test_rejects_very_old_floor(self, tmp_path: Path) -> None:
        """A major version below the floor is rejected cleanly."""
        major = _as_tuple(_REQUIRED_FLOOR)[0]
        toml = _make_toml(tmp_path, f"{major - 1}.0.0")
        result = _run_wrapper(_make_wrapper(toml))
        assert result.returncode != 0
        assert "BRAIN FLOOR REGRESSION" in result.stderr

    def test_rejects_floor_just_below(self, tmp_path: Path) -> None:
        """The highest version below the floor is still rejected."""
        toml = _make_toml(tmp_path, _offset_version(_REQUIRED_FLOOR, minor=-1, patch=9))
        result = _run_wrapper(_make_wrapper(toml))
        assert result.returncode != 0

    # -- Accept (floor >= minimum) ------------------------------------------

    def test_accepts_exact_minimum_floor(self, tmp_path: Path) -> None:
        """Exactly the required floor passes the floor check."""
        toml = _make_toml(tmp_path, _REQUIRED_FLOOR)
        result = _run_wrapper(_make_wrapper(toml))
        assert result.returncode == 0, f"Unexpected failure: {result.stderr}"

    def test_accepts_newer_floor(self, tmp_path: Path) -> None:
        """A floor two minors above the requirement passes."""
        toml = _make_toml(tmp_path, _offset_version(_REQUIRED_FLOOR, minor=2))
        result = _run_wrapper(_make_wrapper(toml))
        assert result.returncode == 0

    def test_accepts_minor_bump(self, tmp_path: Path) -> None:
        """One minor above the requirement passes the floor check."""
        toml = _make_toml(tmp_path, _offset_version(_REQUIRED_FLOOR, minor=1))
        result = _run_wrapper(_make_wrapper(toml))
        assert result.returncode == 0

    # -- Bypass (TAPPS_SKIP_PREPUSH) -----------------------------------------

    def test_bypass_skips_floor_check(self, tmp_path: Path) -> None:
        """TAPPS_SKIP_PREPUSH=1 skips the floor check even for a low floor."""
        toml = _make_toml(tmp_path, _offset_version(_REQUIRED_FLOOR, minor=-1))
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
