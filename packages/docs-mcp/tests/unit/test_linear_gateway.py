"""Tests for docs_mcp.integrations.linear_gateway (TAP-2009 / TAP-6924).

Covers:
- check_validate_sentinel: absent, fresh, stale, malformed (legacy, hook-shared file)
- compute_payload_digest / _normalize_payload_text: normalisation rules
- check_payload_sentinel: missing, fresh+match, fresh+mismatch, stale
- validate_missing_envelope / payload_mismatch_envelope: shape and fields
- gate_linear_save: pass, validate_missing, payload_mismatch, bypass
- docs_save_linear_issue handler: gate pass, gate fire, config error
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from docs_mcp.integrations.linear_gateway import (
    _PAYLOAD_SENTINEL_REL,
    _SENTINEL_MAX_AGE_S,
    _SENTINEL_REL,
    check_payload_sentinel,
    check_validate_sentinel,
    compute_payload_digest,
    gate_linear_save,
    payload_mismatch_envelope,
    validate_missing_envelope,
    write_payload_sentinel,
    write_validate_sentinel,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TITLE = "Fresh title"
_DESCRIPTION = "Fresh description\nwith two lines"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """A temporary project directory (no sentinel by default)."""
    return tmp_path


@pytest.fixture
def fresh_sentinel(project_dir: Path) -> Path:
    """Write a fresh legacy + payload sentinel for (_TITLE, _DESCRIPTION)."""
    sentinel = project_dir / _SENTINEL_REL
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(str(time.time()), encoding="utf-8")
    write_payload_sentinel(project_dir, _TITLE, _DESCRIPTION)
    return project_dir


@pytest.fixture
def stale_sentinel(project_dir: Path) -> Path:
    """Write a stale legacy + payload sentinel (age > TTL) for (_TITLE, _DESCRIPTION)."""
    sentinel = project_dir / _SENTINEL_REL
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    stale_epoch = time.time() - _SENTINEL_MAX_AGE_S - 60
    sentinel.write_text(str(stale_epoch), encoding="utf-8")

    payload_sentinel = project_dir / _PAYLOAD_SENTINEL_REL
    payload_sentinel.parent.mkdir(parents=True, exist_ok=True)
    record = {"digest": compute_payload_digest(_TITLE, _DESCRIPTION), "ts": int(stale_epoch)}
    payload_sentinel.write_text(json.dumps(record), encoding="utf-8")
    return project_dir


# ---------------------------------------------------------------------------
# write_validate_sentinel / check_validate_sentinel (legacy, hook-shared file)
# ---------------------------------------------------------------------------


class TestWriteValidateSentinel:
    def test_writes_sentinel_file(self, project_dir: Path) -> None:
        assert write_validate_sentinel(project_dir) is True
        sentinel = project_dir / _SENTINEL_REL
        assert sentinel.exists()
        ts = int(sentinel.read_text(encoding="utf-8").strip())
        assert ts > 0

    def test_creates_parent_directory(self, project_dir: Path) -> None:
        write_validate_sentinel(project_dir)
        assert (project_dir / ".tapps-mcp").is_dir()

    def test_fresh_write_passes_gate_check(self, project_dir: Path) -> None:
        write_validate_sentinel(project_dir)
        assert check_validate_sentinel(project_dir) is True

    def test_written_content_is_bare_integer(self, project_dir: Path) -> None:
        """The hook pair parses this file as a bare epoch integer — format is frozen."""
        write_validate_sentinel(project_dir)
        content = (project_dir / _SENTINEL_REL).read_text(encoding="utf-8").strip()
        assert content.isdigit()


class TestCheckValidateSentinel:
    def test_no_sentinel_file_returns_false(self, project_dir: Path) -> None:
        assert check_validate_sentinel(project_dir) is False

    def test_fresh_sentinel_returns_true(self, fresh_sentinel: Path) -> None:
        assert check_validate_sentinel(fresh_sentinel) is True

    def test_stale_sentinel_returns_false(self, stale_sentinel: Path) -> None:
        assert check_validate_sentinel(stale_sentinel) is False

    def test_malformed_sentinel_content_returns_false(self, project_dir: Path) -> None:
        sentinel = project_dir / _SENTINEL_REL
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("not-a-number", encoding="utf-8")
        assert check_validate_sentinel(project_dir) is False

    def test_empty_sentinel_content_returns_false(self, project_dir: Path) -> None:
        sentinel = project_dir / _SENTINEL_REL
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("", encoding="utf-8")
        assert check_validate_sentinel(project_dir) is False

    def test_sentinel_exactly_at_ttl_boundary_returns_false(self, project_dir: Path) -> None:
        sentinel = project_dir / _SENTINEL_REL
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        # Exactly at the TTL boundary — should be outside the window
        sentinel.write_text(str(time.time() - _SENTINEL_MAX_AGE_S - 1), encoding="utf-8")
        assert check_validate_sentinel(project_dir) is False

    def test_sentinel_just_inside_ttl_returns_true(self, project_dir: Path) -> None:
        sentinel = project_dir / _SENTINEL_REL
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text(str(time.time() - _SENTINEL_MAX_AGE_S + 10), encoding="utf-8")
        assert check_validate_sentinel(project_dir) is True


# ---------------------------------------------------------------------------
# compute_payload_digest / normalisation (TAP-6924)
# ---------------------------------------------------------------------------


class TestComputePayloadDigest:
    def test_identical_payload_same_digest(self) -> None:
        a = compute_payload_digest("Title", "Body text")
        b = compute_payload_digest("Title", "Body text")
        assert a == b

    def test_different_description_different_digest(self) -> None:
        a = compute_payload_digest("Title", "Body text")
        b = compute_payload_digest("Title", "Totally different body")
        assert a != b

    def test_different_title_different_digest(self) -> None:
        a = compute_payload_digest("Title A", "Body text")
        b = compute_payload_digest("Title B", "Body text")
        assert a != b

    def test_allows_trailing_whitespace_difference(self) -> None:
        """Deliberately allowed: trailing whitespace on a line."""
        a = compute_payload_digest("Title", "Line one\nLine two")
        b = compute_payload_digest("Title", "Line one   \nLine two\t")
        assert a == b

    def test_allows_crlf_vs_lf_difference(self) -> None:
        """Deliberately allowed: CRLF vs LF line endings."""
        a = compute_payload_digest("Title", "Line one\nLine two")
        b = compute_payload_digest("Title", "Line one\r\nLine two")
        assert a == b

    def test_allows_trailing_blank_line_difference(self) -> None:
        """Deliberately allowed: a trailing blank line at end of body."""
        a = compute_payload_digest("Title", "Line one\nLine two")
        b = compute_payload_digest("Title", "Line one\nLine two\n\n")
        assert a == b

    def test_refuses_wording_change(self) -> None:
        """Deliberately refused: an actual wording difference, not whitespace."""
        a = compute_payload_digest("Title", "a thing breaks")
        b = compute_payload_digest("Title", "a different thing breaks")
        assert a != b

    def test_refuses_case_change(self) -> None:
        """Deliberately refused: case differences are a real content change."""
        a = compute_payload_digest("Title", "Body Text")
        b = compute_payload_digest("Title", "body text")
        assert a != b


# ---------------------------------------------------------------------------
# write_payload_sentinel / check_payload_sentinel (TAP-6924)
# ---------------------------------------------------------------------------


class TestPayloadSentinel:
    def test_write_creates_json_file(self, project_dir: Path) -> None:
        assert write_payload_sentinel(project_dir, _TITLE, _DESCRIPTION) is True
        sentinel = project_dir / _PAYLOAD_SENTINEL_REL
        assert sentinel.exists()
        record = json.loads(sentinel.read_text(encoding="utf-8"))
        assert record["digest"] == compute_payload_digest(_TITLE, _DESCRIPTION)
        assert record["ts"] > 0

    def test_check_missing_when_no_file(self, project_dir: Path) -> None:
        assert check_payload_sentinel(project_dir, _TITLE, _DESCRIPTION) == "missing"

    def test_check_ok_when_fresh_and_matching(self, fresh_sentinel: Path) -> None:
        assert check_payload_sentinel(fresh_sentinel, _TITLE, _DESCRIPTION) == "ok"

    def test_check_mismatch_when_fresh_but_different_payload(self, fresh_sentinel: Path) -> None:
        assert (
            check_payload_sentinel(fresh_sentinel, _TITLE, "a completely different body")
            == "mismatch"
        )

    def test_check_stale_when_ttl_exceeded(self, stale_sentinel: Path) -> None:
        assert check_payload_sentinel(stale_sentinel, _TITLE, _DESCRIPTION) == "stale"

    def test_check_missing_on_malformed_json(self, project_dir: Path) -> None:
        sentinel = project_dir / _PAYLOAD_SENTINEL_REL
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("not-json", encoding="utf-8")
        assert check_payload_sentinel(project_dir, _TITLE, _DESCRIPTION) == "missing"

    def test_check_allows_normalisation_difference(self, fresh_sentinel: Path) -> None:
        """Positive control: a trailing-whitespace-only diff still matches."""
        assert check_payload_sentinel(fresh_sentinel, _TITLE, _DESCRIPTION + "   ") == "ok"


# ---------------------------------------------------------------------------
# validate_missing_envelope / payload_mismatch_envelope
# ---------------------------------------------------------------------------


class TestValidateMissingEnvelope:
    def test_returns_ok_false(self) -> None:
        env = validate_missing_envelope("My issue", "description here")
        assert env["ok"] is False

    def test_code_is_validate_missing(self) -> None:
        env = validate_missing_envelope("My issue", "description here")
        assert env["code"] == "validate_missing"

    def test_gate_field(self) -> None:
        env = validate_missing_envelope("My issue", "description here")
        assert env["gate"] == "linear_write_validation"

    def test_use_field_names_correct_tool(self) -> None:
        env = validate_missing_envelope("My issue", "description here")
        assert env["use"] == "docs_validate_linear_issue"

    def test_args_contains_title_and_description(self) -> None:
        env = validate_missing_envelope("My issue", "desc")
        assert env["args"]["title"] == "My issue"
        assert env["args"]["description"] == "desc"

    def test_bypass_env_present(self) -> None:
        env = validate_missing_envelope("t", "d")
        assert env["bypass_env"] == "TAPPS_LINEAR_SKIP_VALIDATE"

    def test_logged_to_present(self) -> None:
        env = validate_missing_envelope("t", "d")
        assert ".bypass-log.jsonl" in env["logged_to"]

    def test_hint_is_string(self) -> None:
        env = validate_missing_envelope("t", "d")
        assert isinstance(env["hint"], str)
        assert len(env["hint"]) > 0


class TestPayloadMismatchEnvelope:
    def test_returns_ok_false(self) -> None:
        env = payload_mismatch_envelope("My issue", "description here")
        assert env["ok"] is False

    def test_code_is_payload_mismatch(self) -> None:
        env = payload_mismatch_envelope("My issue", "description here")
        assert env["code"] == "payload_mismatch"

    def test_code_differs_from_validate_missing(self) -> None:
        mismatch = payload_mismatch_envelope("t", "d")
        missing = validate_missing_envelope("t", "d")
        assert mismatch["code"] != missing["code"]

    def test_gate_field_matches_validate_missing(self) -> None:
        """Same logical gate, distinguished by code — not a new gate name."""
        env = payload_mismatch_envelope("My issue", "description here")
        assert env["gate"] == "linear_write_validation"

    def test_hint_names_the_mismatch(self) -> None:
        env = payload_mismatch_envelope("t", "d")
        assert "match" in env["hint"].lower()

    def test_bypass_env_present(self) -> None:
        env = payload_mismatch_envelope("t", "d")
        assert env["bypass_env"] == "TAPPS_LINEAR_SKIP_VALIDATE"


# ---------------------------------------------------------------------------
# gate_linear_save
# ---------------------------------------------------------------------------


class TestGateLinearSave:
    def test_returns_none_when_fresh_sentinel_matches(self, fresh_sentinel: Path) -> None:
        result = gate_linear_save(fresh_sentinel, _TITLE, _DESCRIPTION)
        assert result is None

    def test_returns_envelope_when_no_sentinel(self, project_dir: Path) -> None:
        result = gate_linear_save(project_dir, "My issue", "desc")
        assert result is not None
        assert result["ok"] is False
        assert result["code"] == "validate_missing"

    def test_returns_envelope_when_stale_sentinel(self, stale_sentinel: Path) -> None:
        result = gate_linear_save(stale_sentinel, _TITLE, _DESCRIPTION)
        assert result is not None
        assert result["code"] == "validate_missing"

    def test_returns_mismatch_envelope_when_payload_differs(self, fresh_sentinel: Path) -> None:
        """Negative control: validate body A, then attempt to save body B."""
        result = gate_linear_save(fresh_sentinel, _TITLE, "a completely different placeholder body")
        assert result is not None
        assert result["ok"] is False
        assert result["code"] == "payload_mismatch"

    def test_allows_normalisation_difference(self, fresh_sentinel: Path) -> None:
        """Positive control: trailing whitespace difference is allowed through."""
        result = gate_linear_save(fresh_sentinel, _TITLE, _DESCRIPTION + "  \n")
        assert result is None

    def test_bypass_env_skips_check(self, project_dir: Path, monkeypatch: Any) -> None:
        monkeypatch.setenv("TAPPS_LINEAR_SKIP_VALIDATE", "1")
        # Even with no sentinel, bypass returns None (gate passes)
        result = gate_linear_save(project_dir, "title", "desc")
        assert result is None

    def test_bypass_env_not_set_enforces_gate(self, project_dir: Path, monkeypatch: Any) -> None:
        monkeypatch.delenv("TAPPS_LINEAR_SKIP_VALIDATE", raising=False)
        result = gate_linear_save(project_dir, "title", "desc")
        assert result is not None
        assert result["ok"] is False

    def test_envelope_args_carry_input_title(self, project_dir: Path) -> None:
        result = gate_linear_save(project_dir, "Specific title", "body")
        assert result is not None
        assert result["args"]["title"] == "Specific title"


# ---------------------------------------------------------------------------
# docs_save_linear_issue handler (integration-style, no real MCP stack)
# ---------------------------------------------------------------------------


class TestDocsSaveLinearIssueHandler:
    @pytest.mark.asyncio
    async def test_gate_passes_when_fresh_sentinel_matches(self, fresh_sentinel: Path) -> None:
        """Gate passes → returns ok: true."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = fresh_sentinel

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            result = await docs_save_linear_issue(_TITLE, _DESCRIPTION, str(fresh_sentinel))

        assert result["success"] is True
        assert result["data"]["ok"] is True

    @pytest.mark.asyncio
    async def test_gate_fires_when_no_sentinel(self, project_dir: Path) -> None:
        """Gate fires → returns validate_missing envelope in data."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = project_dir

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            result = await docs_save_linear_issue("My issue", "desc", str(project_dir))

        assert result["success"] is True  # tool ran OK at transport level
        assert result["data"]["ok"] is False
        assert result["data"]["code"] == "validate_missing"

    @pytest.mark.asyncio
    async def test_gate_fires_mismatch_when_sentinel_for_different_payload(
        self, fresh_sentinel: Path
    ) -> None:
        """Gate fires with payload_mismatch → refusal names the mismatch, not a pass."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = fresh_sentinel

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            result = await docs_save_linear_issue(
                _TITLE, "two-line placeholder\nnothing like the validated body", str(fresh_sentinel)
            )

        assert result["data"]["ok"] is False
        assert result["data"]["code"] == "payload_mismatch"

    @pytest.mark.asyncio
    async def test_next_steps_on_gate_fire(self, project_dir: Path) -> None:
        """Gate fire response includes next_steps with the validator call."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = project_dir

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            result = await docs_save_linear_issue("My issue", "desc", str(project_dir))

        next_steps = result["data"].get("next_steps", [])
        assert any("docs_validate_linear_issue" in step for step in next_steps)

    @pytest.mark.asyncio
    async def test_next_steps_on_gate_pass(self, fresh_sentinel: Path) -> None:
        """Gate pass response includes next_steps pointing to save_issue."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = fresh_sentinel

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            result = await docs_save_linear_issue(_TITLE, _DESCRIPTION, str(fresh_sentinel))

        next_steps = result["data"].get("next_steps", [])
        assert any("save_issue" in step for step in next_steps)

    @pytest.mark.asyncio
    async def test_config_error_returns_error_response(self) -> None:
        """Settings failure returns an error response (not a crash)."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        with patch(
            "docs_mcp.config.settings.load_docs_settings",
            side_effect=RuntimeError("config broken"),
        ):
            result = await docs_save_linear_issue("title", "desc")

        assert result["success"] is False
        assert result["error"]["code"] == "CONFIG_ERROR"

    @pytest.mark.asyncio
    async def test_bypass_env_allows_save_without_sentinel(
        self, project_dir: Path, monkeypatch: Any
    ) -> None:
        """TAPPS_LINEAR_SKIP_VALIDATE bypasses the gate check."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue

        monkeypatch.setenv("TAPPS_LINEAR_SKIP_VALIDATE", "1")

        settings_mock = MagicMock()
        settings_mock.project_root = project_dir

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            result = await docs_save_linear_issue("title", "desc", str(project_dir))

        assert result["data"]["ok"] is True


_AGENT_READY_DESCRIPTION = (
    "## What\na thing breaks\n\n"
    "## Where\n`packages/foo/foo.py:12-20`\n\n"
    "## Acceptance\n- [ ] `pytest tests/test_foo.py` passes\n"
)


class TestValidateToSaveRoundTrip:
    @pytest.mark.asyncio
    async def test_validate_writes_sentinel_then_save_passes(self, project_dir: Path) -> None:
        """Server-side sentinel write unlocks docs_save_linear_issue (no hook)."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue, docs_validate_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = project_dir

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            validate_result = await docs_validate_linear_issue(
                "foo.py: something breaks",
                _AGENT_READY_DESCRIPTION,
                priority=2,
                estimate=2.0,
                project_root=str(project_dir),
            )
            save_result = await docs_save_linear_issue(
                "foo.py: something breaks",
                _AGENT_READY_DESCRIPTION,
                str(project_dir),
            )

        assert validate_result["data"]["agent_ready"] is True
        assert (project_dir / _SENTINEL_REL).exists()
        assert (project_dir / _PAYLOAD_SENTINEL_REL).exists()
        assert save_result["data"]["ok"] is True

    @pytest.mark.asyncio
    async def test_failed_validate_does_not_write_sentinel(self, project_dir: Path) -> None:
        from docs_mcp.server_linear_tools import docs_validate_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = project_dir

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            result = await docs_validate_linear_issue(
                "bad title that is way too long and should never be used for a real issue",
                "## What\nno anchors\n",
                project_root=str(project_dir),
            )

        assert result["data"]["agent_ready"] is False
        assert not (project_dir / _SENTINEL_REL).exists()
        assert not (project_dir / _PAYLOAD_SENTINEL_REL).exists()

    @pytest.mark.asyncio
    async def test_validate_body_a_then_save_body_b_is_refused(self, project_dir: Path) -> None:
        """The reproduced defect (TAP-6924): validating A must not authorize saving B."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue, docs_validate_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = project_dir

        placeholder_description = "two-line placeholder\nnothing like the validated body"

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            validate_result = await docs_validate_linear_issue(
                "foo.py: something breaks",
                _AGENT_READY_DESCRIPTION,
                priority=2,
                estimate=2.0,
                project_root=str(project_dir),
            )
            save_result = await docs_save_linear_issue(
                "foo.py: something breaks",
                placeholder_description,
                str(project_dir),
            )

        assert validate_result["data"]["agent_ready"] is True
        assert save_result["data"]["ok"] is False
        assert save_result["data"]["code"] == "payload_mismatch"

    @pytest.mark.asyncio
    async def test_validate_then_save_with_only_whitespace_diff_passes(
        self, project_dir: Path
    ) -> None:
        """Positive control: a validated body saved with trailing whitespace differences."""
        from docs_mcp.server_linear_tools import docs_save_linear_issue, docs_validate_linear_issue

        settings_mock = MagicMock()
        settings_mock.project_root = project_dir

        crlf_description = _AGENT_READY_DESCRIPTION.replace("\n", "\r\n") + "   \n"

        with patch("docs_mcp.config.settings.load_docs_settings", return_value=settings_mock):
            await docs_validate_linear_issue(
                "foo.py: something breaks",
                _AGENT_READY_DESCRIPTION,
                priority=2,
                estimate=2.0,
                project_root=str(project_dir),
            )
            save_result = await docs_save_linear_issue(
                "foo.py: something breaks",
                crlf_description,
                str(project_dir),
            )

        assert save_result["data"]["ok"] is True
