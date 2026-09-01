"""Naming-site and slot-validation tests for handoffs (TAP-6870).

``handoff_path`` is the single site that names a handoff file, and
``handoff_memory_key`` the single site that names its brain row. Everything
here pins one of three properties: the no-slot path is byte-identical to the
pre-change constant, a slot lands under ``handoffs/``, and an invalid slot is
refused by *both* defences before any path is written.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.tools.handoff_schema import (
    SESSION_HANDOFF_MEMORY_KEY,
    InvalidHandoffSlotError,
    handoff_memory_key,
    handoff_path,
)

# The literal this module replaced. Written out rather than imported so the
# test still fails if the naming site silently changes what it returns.
_PRE_CHANGE_RELATIVE = Path(".tapps-mcp") / "session-handoff.md"


class TestDefaultPathUnchanged:
    def test_no_slot_returns_pre_change_path(self, tmp_path: Path) -> None:
        assert handoff_path(tmp_path) == tmp_path / _PRE_CHANGE_RELATIVE

    def test_no_slot_string_is_byte_identical(self, tmp_path: Path) -> None:
        assert str(handoff_path(tmp_path)) == str(tmp_path / ".tapps-mcp" / "session-handoff.md")

    def test_slot_none_is_the_default(self, tmp_path: Path) -> None:
        assert handoff_path(tmp_path, None) == handoff_path(tmp_path)

    def test_no_slot_brain_key_unchanged(self) -> None:
        assert handoff_memory_key() == "session-handoff"
        assert handoff_memory_key() == SESSION_HANDOFF_MEMORY_KEY


class TestSlottedPath:
    def test_slot_lands_under_handoffs_dir(self, tmp_path: Path) -> None:
        assert handoff_path(tmp_path, "ceg-hub") == (
            tmp_path / ".tapps-mcp" / "handoffs" / "ceg-hub.md"
        )

    def test_slot_brain_key_is_namespaced(self) -> None:
        assert handoff_memory_key("ceg-hub") == "session-handoff:ceg-hub"

    @pytest.mark.parametrize("slot", ["a", "0", "handoff-slots", "a" * 48])
    def test_allowlist_accepts_legal_slots(self, tmp_path: Path, slot: str) -> None:
        assert handoff_path(tmp_path, slot).name == f"{slot}.md"


class TestSlotValidationRejects:
    # The four cases the spec names, plus the shapes the regex exists to stop.
    @pytest.mark.parametrize(
        "slot",
        [
            "../escape",
            "a/b",
            "",
            "a" * 64,
            "..",
            ".hidden",
            "Upper",
            "-leading-dash",
            "has space",
            "trailing.md",
        ],
    )
    def test_invalid_slot_raises(self, tmp_path: Path, slot: str) -> None:
        with pytest.raises(InvalidHandoffSlotError):
            handoff_path(tmp_path, slot)

    def test_error_carries_a_structured_envelope(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidHandoffSlotError) as exc:
            handoff_path(tmp_path, "../escape")
        envelope = exc.value.envelope
        assert envelope["ok"] is False
        assert envelope["code"] == "invalid_handoff_slot"
        assert envelope["gate"] == "handoff_slot_validation"
        assert envelope["hint"]
        assert envelope["extra"]["slot"] == "../escape"

    def test_invalid_slot_never_touches_the_filesystem(self, tmp_path: Path) -> None:
        before = sorted(p.name for p in tmp_path.iterdir())
        for slot in ("../escape", "a/b", "", "a" * 64):
            with pytest.raises(InvalidHandoffSlotError):
                handoff_path(tmp_path, slot)
        assert sorted(p.name for p in tmp_path.iterdir()) == before

    def test_memory_key_rejects_the_same_slots(self) -> None:
        for slot in ("../escape", "a/b", "", "a" * 64):
            with pytest.raises(InvalidHandoffSlotError):
                handoff_memory_key(slot)


class TestContainmentIsIndependentOfTheRegex:
    """The post-join check must still hold when the allowlist is bypassed."""

    def test_symlinked_handoffs_dir_pointing_outside_is_rejected(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        (root / ".tapps-mcp").mkdir(parents=True)
        outside = tmp_path / "outside"
        outside.mkdir()
        (root / ".tapps-mcp" / "handoffs").symlink_to(outside)

        # "legit" passes the allowlist regex; only the containment check sees
        # that the directory it would land in resolves outside the project.
        with pytest.raises(InvalidHandoffSlotError) as exc:
            handoff_path(root, "legit")
        assert exc.value.envelope["extra"]["reason"] == "escapes_project_root"

    def test_symlinked_handoffs_dir_inside_the_project_is_allowed(self, tmp_path: Path) -> None:
        # Negative control: the check rejects *escape*, not symlinks as such.
        root = tmp_path / "proj"
        (root / ".tapps-mcp").mkdir(parents=True)
        inside = root / "elsewhere"
        inside.mkdir()
        (root / ".tapps-mcp" / "handoffs").symlink_to(inside)
        assert handoff_path(root, "legit").name == "legit.md"

    def test_containment_catches_traversal_when_the_regex_is_loosened(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Simulate a future maintainer widening the allowlist: the second
        # defence must still refuse a slot that walks out of handoffs/.
        import re

        from tapps_mcp.tools import handoff_schema

        monkeypatch.setattr(handoff_schema, "_SLOT_RE", re.compile(r"^.*$"))
        with pytest.raises(InvalidHandoffSlotError) as exc:
            handoff_path(tmp_path, "../escape")
        assert exc.value.envelope["extra"]["reason"] == "escapes_slot_dir"


class TestNoRestatedConstantSurvives:
    """VAL-7: the other sites resolve a handoff path via the naming site."""

    def test_fleet_audit_reports_the_naming_site_path(self, tmp_path: Path) -> None:
        from datetime import UTC, datetime

        from tapps_mcp.tools import fleet_audit

        (tmp_path / ".tapps-mcp.yaml").write_text("", encoding="utf-8")
        report = fleet_audit.audit_project_root(
            tmp_path,
            since=datetime(2000, 1, 1, tzinfo=UTC),
            include_brain=False,
        )
        expected = handoff_path(tmp_path).relative_to(tmp_path)
        assert report["handoff"]["path"] == str(expected)

    def test_fleet_audit_holds_no_private_path_constant(self) -> None:
        from tapps_mcp.tools import fleet_audit

        assert not hasattr(fleet_audit, "_HANDOFF_PATH")

    def test_dashboard_constant_has_not_diverged(self, tmp_path: Path) -> None:
        # tapps-core cannot import tapps-mcp (dependency runs the other way),
        # so dashboard.py keeps its own constant and this check fails loudly
        # if the two ever disagree.
        from tapps_core.metrics import dashboard

        assert handoff_path(tmp_path).relative_to(tmp_path) == dashboard._HANDOFF_RELATIVE
