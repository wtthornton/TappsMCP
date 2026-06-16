"""Tests for the audit coverage manifest helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from tapps_mcp.tools.audit_manifest import (
    _BRAIN_KEY_SLUG_RE,
    CoverageEntry,
    FindingCounts,
    _serialize_coverage,
    campaign_key,
    close_coverage,
    coverage_key,
    fix_campaign_key,
    is_fresh,
    load_campaign_spec,
    now_iso,
    read_coverage_for,
    rel_path_from_coverage_key,
    save_campaign_spec,
    write_coverage,
)


class FakeBridge:
    """In-memory stand-in for BrainBridge used in tests."""

    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        self.save_calls: list[dict[str, Any]] = []

    async def save(self, **kwargs: Any) -> dict[str, Any]:
        self.save_calls.append(dict(kwargs))
        self.store[kwargs["key"]] = {"value": kwargs["value"], **kwargs}
        return self.store[kwargs["key"]]

    async def get(self, key: str) -> dict[str, Any] | None:
        return self.store.get(key)


@pytest.fixture
def fake_bridge(monkeypatch: pytest.MonkeyPatch) -> FakeBridge:
    bridge = FakeBridge()
    monkeypatch.setattr(
        "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
        lambda: bridge,
    )
    return bridge


class TestKeys:
    def test_coverage_key(self) -> None:
        assert coverage_key("src/foo.py") == "audit.coverage.src--foo_dpy"

    def test_coverage_key_nested_scout_path(self) -> None:
        rel = "src/nlt_ideas_scout/api/app.py"
        key = coverage_key(rel)
        assert key == "audit.coverage.src--nlt_ideas_scout--api--app_dpy"
        assert _BRAIN_KEY_SLUG_RE.match(key)

    def test_coverage_key_round_trip(self) -> None:
        paths = [
            "src/foo.py",
            "src/nlt_ideas_scout/api/app.py",
            "src/a.b/c.py",
            "src/foo_bar/baz.py",
        ]
        for rel in paths:
            assert rel_path_from_coverage_key(coverage_key(rel)) == rel.lower()

    def test_campaign_key(self) -> None:
        assert campaign_key("audit-2026-05-17") == "audit.campaign.audit-2026-05-17"
        assert _BRAIN_KEY_SLUG_RE.match(campaign_key("audit-2026-05-17"))

    def test_fix_campaign_key(self) -> None:
        key = fix_campaign_key("audit-2026-05-17")
        assert key == "fix.campaign.audit-2026-05-17"
        assert _BRAIN_KEY_SLUG_RE.match(key)


class TestIsFresh:
    def _entry(self, sha: str, age_days: int = 0) -> CoverageEntry:
        when = datetime.now(tz=UTC) - timedelta(days=age_days)
        return CoverageEntry(
            rel_path="src/foo.py",
            audited_sha=sha,
            audited_at=when.isoformat(),
            session_ticket="TAP-1",
            campaign_id="c1",
        )

    def test_matching_sha_within_window(self) -> None:
        assert is_fresh(self._entry("abc1234", 5), "abc1234", max_age_days=30) is True

    def test_mismatched_sha(self) -> None:
        assert is_fresh(self._entry("abc1234", 5), "deadbee") is False

    def test_outside_window(self) -> None:
        assert is_fresh(self._entry("abc1234", 60), "abc1234", max_age_days=30) is False

    def test_empty_sha(self) -> None:
        assert is_fresh(self._entry("", 0), "abc1234") is False

    def test_malformed_timestamp(self) -> None:
        entry = CoverageEntry(
            rel_path="src/foo.py",
            audited_sha="abc1234",
            audited_at="not-a-date",
            session_ticket="TAP-1",
            campaign_id="c1",
        )
        assert is_fresh(entry, "abc1234") is False


class TestSerialization:
    def test_serialize_omits_rel_path(self) -> None:
        entry = CoverageEntry(
            rel_path="src/foo.py",
            audited_sha="abc1234",
            audited_at="2026-05-17T18:00:00+00:00",
            session_ticket="TAP-1",
            campaign_id="c1",
            findings=FindingCounts(p0=1, p2=3),
            finding_tickets=["TAP-2"],
        )
        payload = _serialize_coverage(entry)
        assert "rel_path" not in payload
        assert payload["audited_sha"] == "abc1234"
        assert payload["findings"]["p0"] == 1
        assert payload["finding_tickets"] == ["TAP-2"]

    def test_serialize_includes_fix_tickets(self) -> None:
        entry = CoverageEntry(
            rel_path="src/foo.py",
            audited_sha="abc1234",
            audited_at="2026-05-17T18:00:00+00:00",
            session_ticket="TAP-1",
            campaign_id="c1",
            finding_tickets=["TAP-2"],
            fix_tickets=["TAP-456"],
        )
        payload = _serialize_coverage(entry)
        assert payload["fix_tickets"] == ["TAP-456"]


class TestReadCoverage:
    @pytest.mark.asyncio
    async def test_empty_input(self, fake_bridge: FakeBridge) -> None:
        assert await read_coverage_for([]) == {}

    @pytest.mark.asyncio
    async def test_missing_returns_none(self, fake_bridge: FakeBridge) -> None:
        result = await read_coverage_for(["src/foo.py"])
        assert result == {"src/foo.py": None}

    @pytest.mark.asyncio
    async def test_round_trip(self, fake_bridge: FakeBridge) -> None:
        entry = CoverageEntry(
            rel_path="src/foo.py",
            audited_sha="abc1234",
            audited_at=now_iso(),
            session_ticket="TAP-1",
            campaign_id="c1",
            findings=FindingCounts(p2=2),
            finding_tickets=["TAP-2"],
        )
        assert await write_coverage(entry) is True
        result = await read_coverage_for(["src/foo.py"])
        loaded = result["src/foo.py"]
        assert loaded is not None
        assert loaded.audited_sha == "abc1234"
        assert loaded.session_ticket == "TAP-1"
        assert loaded.findings.p2 == 2
        assert loaded.finding_tickets == ["TAP-2"]

    @pytest.mark.asyncio
    async def test_corrupt_value_returns_none(self, fake_bridge: FakeBridge) -> None:
        fake_bridge.store[coverage_key("src/foo.py")] = {"value": "not-json"}
        result = await read_coverage_for(["src/foo.py"])
        assert result["src/foo.py"] is None


class TestCampaignSpec:
    @pytest.mark.asyncio
    async def test_save_and_load(self, fake_bridge: FakeBridge) -> None:
        spec = {"campaign_id": "c1", "total_files": 3, "sessions": []}
        assert await save_campaign_spec("c1", spec) is True
        loaded = await load_campaign_spec("c1")
        assert loaded == spec

    @pytest.mark.asyncio
    async def test_load_missing_returns_none(self, fake_bridge: FakeBridge) -> None:
        assert await load_campaign_spec("nope") is None

    @pytest.mark.asyncio
    async def test_corrupt_spec_returns_none(self, fake_bridge: FakeBridge) -> None:
        fake_bridge.store[campaign_key("c1")] = {"value": "not-json"}
        assert await load_campaign_spec("c1") is None

    @pytest.mark.asyncio
    async def test_save_uses_procedural_tier(self, fake_bridge: FakeBridge) -> None:
        await save_campaign_spec("c1", {"k": "v"})
        assert fake_bridge.save_calls[-1]["tier"] == "procedural"

    @pytest.mark.asyncio
    async def test_save_coverage_uses_pattern_tier(self, fake_bridge: FakeBridge) -> None:
        entry = CoverageEntry(
            rel_path="src/foo.py",
            audited_sha="abc1234",
            audited_at=now_iso(),
            session_ticket="TAP-1",
            campaign_id="c1",
        )
        await write_coverage(entry)
        assert fake_bridge.save_calls[-1]["tier"] == "pattern"


class TestDegradedMode:
    @pytest.mark.asyncio
    async def test_read_when_bridge_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
            lambda: None,
        )
        result = await read_coverage_for(["a.py", "b.py"])
        assert result == {"a.py": None, "b.py": None}

    @pytest.mark.asyncio
    async def test_write_when_bridge_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
            lambda: None,
        )
        entry = CoverageEntry(
            rel_path="a.py",
            audited_sha="abc",
            audited_at=now_iso(),
            session_ticket="TAP-1",
            campaign_id="c1",
        )
        assert await write_coverage(entry) is False

    @pytest.mark.asyncio
    async def test_save_campaign_when_bridge_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
            lambda: None,
        )
        assert await save_campaign_spec("c1", {}) is False


class TestBridgeFailures:
    """Bridge raises an exception (HTTP failure, circuit open, etc.) —
    all manifest helpers must catch and return degraded results.
    """

    @pytest.fixture
    def failing_bridge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _Failing:
            async def save(self, **_: Any) -> None:
                raise RuntimeError("bridge unavailable: HTTP 401")

            async def get(self, _: str) -> None:
                raise RuntimeError("bridge unavailable: HTTP 401")

        monkeypatch.setattr(
            "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
            lambda: _Failing(),
        )

    @pytest.mark.asyncio
    async def test_write_coverage_returns_false_on_exception(self, failing_bridge: None) -> None:
        entry = CoverageEntry(
            rel_path="a.py",
            audited_sha="abc",
            audited_at=now_iso(),
            session_ticket="TAP-1",
            campaign_id="c1",
        )
        assert await write_coverage(entry) is False

    @pytest.mark.asyncio
    async def test_write_coverage_returns_false_on_brain_error_dict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Rejecting:
            async def save(self, **_: Any) -> dict[str, str]:
                return {
                    "error": "bad_request",
                    "message": "Key must be a lowercase slug",
                }

        monkeypatch.setattr(
            "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
            lambda: _Rejecting(),
        )
        entry = CoverageEntry(
            rel_path="src/foo.py",
            audited_sha="abc",
            audited_at=now_iso(),
            session_ticket="TAP-1",
            campaign_id="c1",
        )
        assert await write_coverage(entry) is False

    @pytest.mark.asyncio
    async def test_save_campaign_returns_false_on_exception(self, failing_bridge: None) -> None:
        assert await save_campaign_spec("c1", {"k": "v"}) is False

    @pytest.mark.asyncio
    async def test_load_campaign_returns_none_on_exception(self, failing_bridge: None) -> None:
        assert await load_campaign_spec("c1") is None

    @pytest.mark.asyncio
    async def test_read_coverage_returns_none_on_exception(self, failing_bridge: None) -> None:
        result = await read_coverage_for(["a.py"])
        assert result == {"a.py": None}


class TestCloseCoverage:
    """TAP-2722: close_coverage updates SHA and links tickets."""

    def _entry(self, sha: str, age_days: int = 0) -> CoverageEntry:
        when = datetime.now(tz=UTC) - timedelta(days=age_days)
        return CoverageEntry(
            rel_path="src/foo.py",
            audited_sha=sha,
            audited_at=when.isoformat(),
            session_ticket="TAP-1",
            campaign_id="c1",
            finding_tickets=["TAP-2"],
        )

    @pytest.mark.asyncio
    async def test_records_fix_sha_without_marking_audited(self, fake_bridge: FakeBridge) -> None:
        # TAP-2799: close_coverage records the fix sha but does NOT claim the
        # post-fix content was audited — a fix is not an audit. audited_sha
        # still reflects the last sha actually audited (the pre-fix sha).
        await write_coverage(self._entry("audited-sha"))
        result = await close_coverage("src/foo.py", "post-fix-sha")
        assert result is True
        loaded = (await read_coverage_for(["src/foo.py"]))["src/foo.py"]
        assert loaded is not None
        assert loaded.fix_sha == "post-fix-sha"
        assert loaded.audited_sha == "audited-sha"

    @pytest.mark.asyncio
    async def test_re_audit_treats_fixed_file_as_changed(self, fake_bridge: FakeBridge) -> None:
        # TAP-2799 contradiction reproduction: after close_coverage, the fixed
        # file must read as NOT fresh at its post-fix sha so a subsequent
        # campaign RE-AUDITS it (re-audit-as-changed), matching the handoff
        # contract. The TAP-2722 bug set audited_sha=new_sha → is_fresh True →
        # the file was silently skipped, the opposite of the stated behavior.
        await write_coverage(self._entry("audited-sha"))
        await close_coverage("src/foo.py", "post-fix-sha")
        loaded = (await read_coverage_for(["src/foo.py"]))["src/foo.py"]
        assert loaded is not None
        # current sha == the post-fix sha → must be treated as changed.
        assert is_fresh(loaded, "post-fix-sha") is False

    @pytest.mark.asyncio
    async def test_appends_fix_ticket(self, fake_bridge: FakeBridge) -> None:
        await write_coverage(self._entry("old-sha"))
        await close_coverage("src/foo.py", "new-sha", fix_ticket="TAP-456")
        loaded = (await read_coverage_for(["src/foo.py"]))["src/foo.py"]
        assert loaded is not None
        assert "TAP-456" in loaded.fix_tickets

    @pytest.mark.asyncio
    async def test_ensures_finding_ticket_present(self, fake_bridge: FakeBridge) -> None:
        entry = CoverageEntry(
            rel_path="src/foo.py",
            audited_sha="old-sha",
            audited_at=now_iso(),
            session_ticket="TAP-1",
            campaign_id="c1",
        )
        await write_coverage(entry)
        await close_coverage("src/foo.py", "new-sha", finding_ticket="TAP-3")
        loaded = (await read_coverage_for(["src/foo.py"]))["src/foo.py"]
        assert loaded is not None
        assert "TAP-3" in loaded.finding_tickets

    @pytest.mark.asyncio
    async def test_no_duplicate_tickets(self, fake_bridge: FakeBridge) -> None:
        # self._entry already has finding_tickets=["TAP-2"]
        await write_coverage(self._entry("old-sha"))
        await close_coverage("src/foo.py", "new-sha", finding_ticket="TAP-2", fix_ticket="TAP-456")
        loaded = (await read_coverage_for(["src/foo.py"]))["src/foo.py"]
        assert loaded is not None
        assert loaded.finding_tickets.count("TAP-2") == 1
        assert "TAP-456" in loaded.fix_tickets

    @pytest.mark.asyncio
    async def test_missing_entry_returns_false(self, fake_bridge: FakeBridge) -> None:
        result = await close_coverage("nonexistent.py", "new-sha")
        assert result is False

    @pytest.mark.asyncio
    async def test_degraded_mode_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
            lambda: None,
        )
        result = await close_coverage("src/foo.py", "new-sha")
        assert result is False


class TestStoreShapes:
    """Bridge entries can be dict or pydantic-model — both work."""

    @pytest.mark.asyncio
    async def test_dict_value_with_value_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bridge = FakeBridge()
        bridge.store[coverage_key("a.py")] = {
            "value": json.dumps(
                {
                    "audited_sha": "abc",
                    "audited_at": now_iso(),
                    "session_ticket": "TAP-1",
                    "campaign_id": "c1",
                    "findings": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
                    "finding_tickets": [],
                }
            )
        }
        monkeypatch.setattr(
            "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
            lambda: bridge,
        )
        result = await read_coverage_for(["a.py"])
        assert result["a.py"] is not None
        assert result["a.py"].audited_sha == "abc"


class TestTappsAuditCloseCoverageHandler:
    """TAP-2798: the MCP wrapper around close_coverage."""

    def _entry(self, sha: str) -> CoverageEntry:
        return CoverageEntry(
            rel_path="src/foo.py",
            audited_sha=sha,
            audited_at=now_iso(),
            session_ticket="TAP-1",
            campaign_id="c1",
        )

    @pytest.mark.asyncio
    async def test_success_records_fix_sha(self, fake_bridge: FakeBridge) -> None:
        from tapps_mcp.server_analysis_tools import tapps_audit_close_coverage

        await write_coverage(self._entry("audited-sha"))
        result = await tapps_audit_close_coverage("src/foo.py", "post-fix-sha")
        assert result["success"] is True
        assert result["data"]["ok"] is True
        assert result["data"]["reason"] == ""
        loaded = (await read_coverage_for(["src/foo.py"]))["src/foo.py"]
        assert loaded is not None
        # TAP-2799: fix sha recorded; audited_sha unchanged so re-audit picks it up.
        assert loaded.fix_sha == "post-fix-sha"
        assert loaded.audited_sha == "audited-sha"
        assert is_fresh(loaded, "post-fix-sha") is False

    @pytest.mark.asyncio
    async def test_success_links_tickets(self, fake_bridge: FakeBridge) -> None:
        from tapps_mcp.server_analysis_tools import tapps_audit_close_coverage

        await write_coverage(self._entry("old-sha"))
        result = await tapps_audit_close_coverage(
            "src/foo.py", "new-sha", fix_ticket="TAP-2799", finding_ticket="TAP-2722"
        )
        assert result["data"]["ok"] is True
        loaded = (await read_coverage_for(["src/foo.py"]))["src/foo.py"]
        assert loaded is not None
        assert "TAP-2799" in loaded.fix_tickets
        assert "TAP-2722" in loaded.finding_tickets

    @pytest.mark.asyncio
    async def test_missing_entry_returns_ok_false(self, fake_bridge: FakeBridge) -> None:
        from tapps_mcp.server_analysis_tools import tapps_audit_close_coverage

        result = await tapps_audit_close_coverage("nonexistent.py", "new-sha")
        assert result["success"] is True
        assert result["data"]["ok"] is False
        assert result["data"]["reason"] == "coverage_entry_missing_or_write_failed"

    @pytest.mark.asyncio
    async def test_degraded_bridge_structured_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_mcp.server_analysis_tools import tapps_audit_close_coverage

        monkeypatch.setattr(
            "tapps_mcp.tools.audit_manifest._get_bridge_or_none",
            lambda: None,
        )
        result = await tapps_audit_close_coverage("src/foo.py", "new-sha")
        # Structured {ok:false, reason} instead of a bare False (TAP-2798).
        assert result["success"] is True
        assert result["degraded"] is True
        assert result["data"]["ok"] is False
        assert result["data"]["reason"] == "bridge_unavailable"

    @pytest.mark.asyncio
    async def test_empty_rel_path_is_error(self, fake_bridge: FakeBridge) -> None:
        from tapps_mcp.server_analysis_tools import tapps_audit_close_coverage

        result = await tapps_audit_close_coverage("", "new-sha")
        assert result["success"] is False
        assert result["error"]["code"] == "missing_rel_path"

    @pytest.mark.asyncio
    async def test_empty_new_sha_is_error(self, fake_bridge: FakeBridge) -> None:
        from tapps_mcp.server_analysis_tools import tapps_audit_close_coverage

        result = await tapps_audit_close_coverage("src/foo.py", "")
        assert result["success"] is False
        assert result["error"]["code"] == "missing_new_sha"
