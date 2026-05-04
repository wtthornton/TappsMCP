"""TAP-1082: tapps_session_start hard-fails on brain auth probe 401/403.

Audit data: 38 sessions silently degraded over the 30-day window; one project
retried tapps_session_start 18 times in a single session because the failure
was buried in ``memory_status.auth_probe`` while the top-level ``success`` was
``true``.

These tests pin the new contract:

- ``memory.tolerate_brain_auth_failure: false`` (default) → ``success: false``
  with ``error.code == 'brain_auth_failed'`` and TAPPS_BRAIN_AUTH_TOKEN in the
  next_steps.
- ``memory.tolerate_brain_auth_failure: true`` → original soft-degraded
  behavior (``success: true`` with ``degraded: true`` inside memory_status).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from tapps_mcp.server_pipeline_tools import _detect_brain_auth_failure


class _FakeSecret:
    """Stand-in for pydantic.SecretStr with the same get_secret_value() shape."""

    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


class _FakeMemorySettings:
    def __init__(
        self,
        *,
        enabled: bool = True,
        tolerate: bool = False,
        token: str | None = "real-token-abc123",
    ) -> None:
        self.enabled = enabled
        self.tolerate_brain_auth_failure = tolerate
        self.brain_auth_token = _FakeSecret(token) if token is not None else None


class _FakeSettings:
    def __init__(self, memory: _FakeMemorySettings) -> None:
        self.memory = memory


def _ms(http_status: int | None, detail: str = "") -> dict[str, Any]:
    auth: dict[str, Any] = {"ok": False}
    if http_status is not None:
        auth["http_status"] = http_status
    if detail:
        auth["detail"] = detail
    return {
        "enabled": False,
        "mode": "http",
        "http_url": "http://localhost:8080",
        "degraded": True,
        "health_ok": True,
        "auth_probe": auth,
    }


class TestDetectBrainAuthFailure:
    """Unit tests for the _detect_brain_auth_failure helper."""

    def test_returns_error_envelope_on_403(self) -> None:
        settings = _FakeSettings(_FakeMemorySettings())
        result = _detect_brain_auth_failure(
            settings, _ms(403, '{"error":"forbidden","detail":"Invalid token."}'), 100
        )

        assert result is not None
        assert result["success"] is False
        assert result["error"]["code"] == "brain_auth_failed"
        assert result["error"]["http_status"] == 403
        next_steps = result["error"]["next_steps"]
        assert any("TAPPS_BRAIN_AUTH_TOKEN" in s for s in next_steps)
        assert any("tolerate_brain_auth_failure" in s for s in next_steps)

    def test_returns_error_envelope_on_401(self) -> None:
        settings = _FakeSettings(_FakeMemorySettings())
        result = _detect_brain_auth_failure(settings, _ms(401, "Unauthorized"), 50)

        assert result is not None
        assert result["error"]["code"] == "brain_auth_failed"
        assert result["error"]["http_status"] == 401

    def test_passes_through_when_tolerate_flag_set(self) -> None:
        settings = _FakeSettings(_FakeMemorySettings(tolerate=True))
        result = _detect_brain_auth_failure(settings, _ms(403), 0)

        assert result is None

    def test_passes_through_when_memory_disabled(self) -> None:
        settings = _FakeSettings(_FakeMemorySettings(enabled=False))
        result = _detect_brain_auth_failure(settings, _ms(403), 0)

        assert result is None

    def test_passes_through_on_200(self) -> None:
        settings = _FakeSettings(_FakeMemorySettings())
        result = _detect_brain_auth_failure(
            settings,
            {"enabled": True, "auth_probe": {"ok": True, "http_status": 200}},
            0,
        )

        assert result is None

    def test_passes_through_on_500(self) -> None:
        """Server errors are not auth failures — different remediation path."""
        settings = _FakeSettings(_FakeMemorySettings())
        result = _detect_brain_auth_failure(settings, _ms(500), 0)

        assert result is None

    def test_passes_through_when_no_memory_status(self) -> None:
        settings = _FakeSettings(_FakeMemorySettings())
        assert _detect_brain_auth_failure(settings, None, 0) is None
        assert _detect_brain_auth_failure(settings, {}, 0) is None

    def test_passes_through_when_no_auth_probe(self) -> None:
        settings = _FakeSettings(_FakeMemorySettings())
        result = _detect_brain_auth_failure(
            settings,
            {"enabled": False, "mode": "native"},
            0,
        )

        assert result is None

    def test_falls_back_to_error_when_no_detail(self) -> None:
        settings = _FakeSettings(_FakeMemorySettings())
        result = _detect_brain_auth_failure(
            settings,
            {"auth_probe": {"ok": False, "http_status": 403, "error": "probe_raised"}},
            0,
        )

        assert result is not None
        assert "probe_raised" in result["error"]["message"]

    def test_returns_project_id_missing_envelope_on_400(self) -> None:
        """TAP-1257: HTTP 400 with X-Project-Id in body → brain_project_id_missing."""
        settings = _FakeSettings(_FakeMemorySettings())
        body = '{"error":"bad_request","detail":"X-Project-Id header is required for /mcp requests."}'
        result = _detect_brain_auth_failure(settings, _ms(400, body), 25)

        assert result is not None
        assert result["success"] is False
        assert result["error"]["code"] == "brain_project_id_missing"
        assert result["error"]["http_status"] == 400
        next_steps = result["error"]["next_steps"]
        assert any("TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID" in s for s in next_steps)
        assert any("brain_project_id" in s for s in next_steps)

    def test_passes_through_on_400_without_project_id_phrase(self) -> None:
        """A generic 400 (not the X-Project-Id case) should not trigger the new code."""
        settings = _FakeSettings(_FakeMemorySettings())
        result = _detect_brain_auth_failure(
            settings, _ms(400, '{"error":"bad_request","detail":"Malformed JSON."}'), 0
        )

        assert result is None

    def test_400_project_id_missing_respects_tolerate_flag(self) -> None:
        settings = _FakeSettings(_FakeMemorySettings(tolerate=True))
        result = _detect_brain_auth_failure(
            settings,
            _ms(400, "X-Project-Id header is required for /mcp requests."),
            0,
        )

        assert result is None

    def test_unsubstituted_token_yields_distinct_error_code(self) -> None:
        """TAP-1336: literal ${TAPPS_BRAIN_AUTH_TOKEN} → propagation-failure error."""
        settings = _FakeSettings(_FakeMemorySettings(token="${TAPPS_BRAIN_AUTH_TOKEN}"))
        result = _detect_brain_auth_failure(settings, _ms(401, "Unauthorized"), 10)

        assert result is not None
        assert result["error"]["code"] == "brain_auth_token_unsubstituted"
        assert result["error"]["token_state"] == "unsubstituted"
        next_steps = result["error"]["next_steps"]
        assert any("Export TAPPS_BRAIN_AUTH_TOKEN" in s for s in next_steps)
        assert any(".mcp.json" in s for s in next_steps)

    def test_missing_token_yields_distinct_error_code(self) -> None:
        """TAP-1336: empty/None token → missing-token error."""
        settings = _FakeSettings(_FakeMemorySettings(token=None))
        result = _detect_brain_auth_failure(settings, _ms(401, "Unauthorized"), 10)

        assert result is not None
        assert result["error"]["code"] == "brain_auth_token_missing"
        assert result["error"]["token_state"] == "missing"

    def test_empty_string_token_treated_as_missing(self) -> None:
        settings = _FakeSettings(_FakeMemorySettings(token="   "))
        result = _detect_brain_auth_failure(settings, _ms(403, "Forbidden"), 0)

        assert result is not None
        assert result["error"]["code"] == "brain_auth_token_missing"

    def test_present_token_keeps_legacy_error_code(self) -> None:
        """Backward-compat: a real-looking token still returns brain_auth_failed."""
        settings = _FakeSettings(_FakeMemorySettings(token="abc.def.ghi"))
        result = _detect_brain_auth_failure(settings, _ms(403, "Invalid token"), 0)

        assert result is not None
        assert result["error"]["code"] == "brain_auth_failed"
        assert result["error"]["token_state"] == "present"

    def test_memory_status_is_preserved_in_error(self) -> None:
        """Agents that need the original memory_status payload can still get it."""
        settings = _FakeSettings(_FakeMemorySettings())
        ms = _ms(403, "Invalid token")
        result = _detect_brain_auth_failure(settings, ms, 100)

        assert result is not None
        assert result["error"]["memory_status"] == ms


@pytest.mark.asyncio()
class TestSessionStartIntegration:
    """End-to-end check: tapps_session_start returns the error envelope.

    Patches the brain auth probe so the helper sees a 403 response and the
    full handler returns the structured failure rather than success_response.
    """

    async def test_session_start_returns_brain_auth_failed_on_403(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Configure a real-looking token so the failure classifies as
        # "present token, server rejected" rather than missing/unsubstituted.
        monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN", "real-token-abc123")
        # Opt out of the conftest-level _tolerate_brain_auth_failure_in_tests
        # autouse fixture: this test exists specifically to verify the hard-error
        # path that the fixture suppresses.
        monkeypatch.delenv("TAPPS_MCP_MEMORY_TOLERATE_BRAIN_AUTH_FAILURE", raising=False)

        from tapps_mcp.tools import session_start_core as ssc

        async def fake_collect(_settings: Any) -> tuple[Any, dict, dict, dict, dict]:
            info = {
                "data": {
                    "configuration": {
                        "project_root": ".",
                        "quality_preset": "standard",
                    },
                },
            }
            memory_status = _ms(403, '{"error":"forbidden","detail":"Invalid token."}')
            hive_status = {"enabled": False}
            brain_health = {"ok": False}
            timings: dict[str, Any] = {}
            return info, memory_status, hive_status, brain_health, timings

        monkeypatch.setattr(ssc, "collect_session_start_phases", fake_collect)
        monkeypatch.setattr(
            ssc, "detect_path_mapping", lambda: (None, None)
        )
        monkeypatch.setattr(ssc, "get_checklist_session_id", lambda: None)
        monkeypatch.setattr(
            ssc,
            "build_session_start_data",
            lambda *_a, **_k: {
                "memory_status": _ms(
                    403, '{"error":"forbidden","detail":"Invalid token."}'
                ),
            },
        )

        with patch(
            "tapps_mcp.server_pipeline_tools._build_search_first",
            return_value=None,
        ):
            from tapps_mcp.server_pipeline_tools import tapps_session_start

            result = await tapps_session_start()

        assert result["success"] is False
        assert result["error"]["code"] == "brain_auth_failed"
        assert result["error"]["http_status"] == 403
        assert any(
            "TAPPS_BRAIN_AUTH_TOKEN" in step for step in result["error"]["next_steps"]
        )
