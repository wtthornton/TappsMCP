"""HTTP health/auth/close probes mixin for :class:`HttpBrainBridge`.

Split out of ``brain_bridge_http_transport.py`` (TAP-6736, further split). No
behavior change: each method body below is moved byte-for-byte. Composed as
``_HttpHealthMixin`` alongside ``_HttpSessionMixin``, ``_HttpOpsMixin``, and
``BrainBridge`` into the public ``HttpBrainBridge`` class in the facade
module.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

import httpx

from tapps_core.brain_bridge_errors import (
    _BRAIN_HEALTH_TIMEOUT_SECONDS,
    _DRAIN_DEADLINE_SECONDS,
    _HEALTH_CHECK_PROBE_TIMEOUT_SECONDS,
    _MCP_ACCEPT_HEADERS,
    BrainBridgeUnavailable,
)


def _log() -> Any:
    """Lazy accessor for the facade's structlog logger.

    A top-level ``import tapps_core.brain_bridge as _facade`` deadlocks when
    THIS module is the one that gets imported first (its own definitions
    aren't done yet when the facade tries to import back from it) — verified
    empirically while wiring the TAP-6736 split. Deferring the import to
    call time (only here, not at every call site) breaks the cycle cleanly.
    """
    import tapps_core.brain_bridge as _facade

    return _facade.logger


class _HttpHealthMixin:
    """Health/auth/close probes (``/healthz``, ``/health``, tool discovery)."""

    def health_check(self) -> dict[str, Any]:
        """Probe ``{brain_http_url}/healthz`` (TAP-2115 / TAP-1970).

        Prefers the v3.19.0 phased ``/healthz`` endpoint (returns
        ``{ok, db_ok, mcp_ok, queue_depth, circuit_state, brain_version}``)
        so the operator can see WHY a brain is degraded — DB unreachable
        vs MCP cold-starting vs queue flooded — without scraping
        ``/metrics``. Falls back to the legacy 3-field ``/health`` route
        on 404 (brains <3.19.0). The HTTP status is still authoritative
        for the ``ok`` flag (200 ⇒ healthy, 503 ⇒ degraded) — the JSON
        body just enriches ``details`` with the offending phase.

        TAP-6591: consults the circuit breaker before dialing (returns a
        failure envelope immediately when the circuit is open) and bounds
        the probe to ``_HEALTH_CHECK_PROBE_TIMEOUT_SECONDS`` (~1s) rather
        than the longer ``_BRAIN_HEALTH_TIMEOUT_SECONDS`` used by other
        bridge calls — callers on the metrics read hot path
        (``brain_metrics_bridge_available``) cannot afford to block for a
        full HTTP timeout against a stalling brain.
        """
        details: dict[str, Any] = {"http_url": self._http_url, "mode": "http"}
        if self.circuit_open:
            return self._health_check_failure(details, BrainBridgeUnavailable("circuit open"))
        try:
            response = httpx.get(
                f"{self._http_url}/healthz", timeout=_HEALTH_CHECK_PROBE_TIMEOUT_SECONDS
            )
        except Exception as exc:
            return self._health_check_failure(details, exc)
        if response.status_code == 404:
            # Pre-v3.19.0 brain: re-probe the legacy /health route.
            return self._health_check_legacy(details)
        body: dict[str, Any] | None = None
        with contextlib.suppress(Exception):
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        if body is not None:
            self._merge_healthz_fields(details, body)
        if response.status_code == 200:
            return self._health_check_ok(details)
        if response.status_code == 503:
            return self._health_check_degraded(details, body)
        try:
            response.raise_for_status()
        except Exception as exc:
            return self._health_check_failure(details, exc)
        return self._health_check_ok(details)

    @staticmethod
    def _merge_healthz_fields(details: dict[str, Any], body: dict[str, Any]) -> None:
        """Copy phased ``/healthz`` fields (TAP-1970) into the details block.

        Tolerates the legacy ``{"status": ..., "version": ...}`` shape (pre-
        v3.19.0 brains, or brains that route ``/healthz`` to the same handler
        as ``/health``) by reading ``version`` when ``brain_version`` is absent
        and ``status`` when ``ok`` is absent.
        """
        for key in ("db_ok", "mcp_ok", "queue_depth", "circuit_state"):
            if key in body:
                details[key] = body[key]
        if "brain_version" in body:
            details["brain_version"] = body["brain_version"]
        elif "version" in body:
            details["brain_version"] = body["version"]
        if "ok" in body:
            details["brain_status"] = "ok" if body["ok"] else "degraded"
        elif "status" in body:
            details["brain_status"] = body["status"]

    def _health_check_ok(self, details: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "dsn_reachable": True,
            "pool_config_valid": True,
            "native_health_ok": True,
            "errors": [],
            "warnings": [],
            "details": details,
        }

    def _health_check_failure(self, details: dict[str, Any], exc: BaseException) -> dict[str, Any]:
        return {
            "ok": False,
            "dsn_reachable": False,
            "pool_config_valid": True,
            "native_health_ok": False,
            "errors": [f"http_health_failed: {exc}"],
            "warnings": [],
            "details": details,
        }

    def _health_check_degraded(
        self, details: dict[str, Any], body: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Format a 503 response — preserves phased details so operators see
        which phase failed (``db_ok=false``, ``mcp_ok=false`` …).
        """
        offending: list[str] = []
        if isinstance(body, dict):
            offending.extend(key for key in ("db_ok", "mcp_ok") if body.get(key) is False)
        err = "brain_degraded"
        if offending:
            err = f"brain_degraded: {', '.join(offending)}=false"
        return {
            "ok": False,
            # HTTP responded (503 body received) — transport reached the brain.
            "dsn_reachable": True,
            "pool_config_valid": True,
            "native_health_ok": False,
            "errors": [err],
            "warnings": [],
            "details": details,
        }

    def _health_check_legacy(self, details: dict[str, Any]) -> dict[str, Any]:
        """Fallback for pre-v3.19.0 brains that don't expose ``/healthz``."""
        try:
            response = httpx.get(
                f"{self._http_url}/health", timeout=_HEALTH_CHECK_PROBE_TIMEOUT_SECONDS
            )
            response.raise_for_status()
        except Exception as exc:
            return self._health_check_failure(details, exc)
        with contextlib.suppress(Exception):
            payload = response.json()
            if isinstance(payload, dict):
                details["brain_version"] = payload.get("version")
                details["brain_status"] = payload.get("status")
        return self._health_check_ok(details)

    def auth_probe(self) -> dict[str, Any]:
        """Probe ``{brain_http_url}/mcp`` with a cheap authenticated call.

        Complements :meth:`health_check` which only probes the unauthenticated
        ``/health`` endpoint. This sends a real ``tools/call`` (``memory_list``
        with ``limit=1``) carrying the configured Bearer token and
        ``X-Project-Id`` / ``X-Agent-Id`` headers, so a failure here means the
        same auth that runtime memory calls use is rejected by the server.

        Returns a dict with ``ok`` (bool) and diagnostic fields:

        - ``ok=True, http_status=200`` — auth works.
        - ``ok=False, http_status=401|403, detail=<body>`` — server rejected auth.
        - ``ok=False, http_status=200, gated=True, tool, profile, suggested_profile``
          — TAP-2098: server returned ``200`` but the JSON-RPC body carries an
          ``out_of_profile`` error (TAP-1616 / TAP-1972, v3.19.0+). The probe
          tool is hidden by the active profile; ``suggested_profile`` is the
          smallest profile that exposes it (``None`` on brains <3.19.0).
        - ``ok=False, http_status=200, detail=<rpc_error>`` — TAP-2098: ``200``
          response but body carries a non-``out_of_profile`` JSON-RPC error.
        - ``ok=False, error=<str>`` — transport failed (DNS, connection refused, etc.).
        """
        # TAP-836: run the full initialize handshake synchronously. Brain
        # 3.10.3+ returns 400 "Missing session ID" on any tools/call that
        # doesn't carry an Mcp-Session-Id; we fall back to no-session
        # mode if the server doesn't return a session id (older brains).
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "tapps-mcp", "version": "http-bridge"},
            },
        }
        try:
            init_response = httpx.post(
                f"{self._http_url}/mcp/",
                json=init_payload,
                headers={**self._http_headers, **_MCP_ACCEPT_HEADERS},
                timeout=_BRAIN_HEALTH_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        except Exception as exc:
            return {"ok": False, "error": f"probe_failed: {exc}"}
        if init_response.status_code in {401, 403}:
            return {
                "ok": False,
                "http_status": init_response.status_code,
                "detail": init_response.text[:200] if init_response.text else "",
            }
        session_id = init_response.headers.get("mcp-session-id", "")

        probe_headers = {**self._http_headers, **_MCP_ACCEPT_HEADERS}
        if session_id:
            probe_headers["Mcp-Session-Id"] = session_id
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "memory_list", "arguments": {"limit": 1}},
        }
        try:
            response = httpx.post(
                f"{self._http_url}/mcp/",
                json=payload,
                headers=probe_headers,
                timeout=_BRAIN_HEALTH_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        except Exception as exc:
            return {"ok": False, "error": f"probe_failed: {exc}"}
        if response.status_code == 200:
            # TAP-2098: a 200 with an ``out_of_profile`` JSON-RPC error body
            # means the configured profile hides the probe tool — same
            # caller-side fix as a 401/403, so report it as a probe failure
            # rather than silently passing. Tolerates non-JSON or
            # unstructured bodies (no error envelope ⇒ probe ok).
            return self._parse_probe_body(response)
        detail = response.text[:200] if response.text else ""
        return {
            "ok": False,
            "http_status": response.status_code,
            "detail": detail,
        }

    def docs_tools_probe(self) -> dict[str, Any]:
        """Probe ``docs_lookup`` on the brain HTTP MCP endpoint (ADR-0014).

        Used by ``tapps-mcp doctor`` when ``docs_via_brain`` is enabled.
        Returns the same shape as :meth:`auth_probe` (``ok``, ``gated``, …).
        """
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "tapps-mcp", "version": "http-bridge"},
            },
        }
        try:
            init_response = httpx.post(
                f"{self._http_url}/mcp/",
                json=init_payload,
                headers={**self._http_headers, **_MCP_ACCEPT_HEADERS},
                timeout=_BRAIN_HEALTH_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        except Exception as exc:
            return {"ok": False, "error": f"probe_failed: {exc}"}
        if init_response.status_code in {401, 403}:
            return {
                "ok": False,
                "http_status": init_response.status_code,
                "detail": init_response.text[:200] if init_response.text else "",
            }
        session_id = init_response.headers.get("mcp-session-id", "")

        probe_headers = {**self._http_headers, **_MCP_ACCEPT_HEADERS}
        if session_id:
            probe_headers["Mcp-Session-Id"] = session_id
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "docs_lookup",
                "arguments": {"library": "structlog", "topic": "overview", "mode": "code"},
            },
        }
        try:
            response = httpx.post(
                f"{self._http_url}/mcp/",
                json=payload,
                headers=probe_headers,
                timeout=_BRAIN_HEALTH_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
        except Exception as exc:
            return {"ok": False, "error": f"probe_failed: {exc}"}
        if response.status_code == 200:
            parsed = self._parse_probe_body(response)
            if parsed.get("gated"):
                parsed["tool"] = parsed.get("tool") or "docs_lookup"
            return parsed
        detail = response.text[:200] if response.text else ""
        return {
            "ok": False,
            "http_status": response.status_code,
            "detail": detail,
        }

    @staticmethod
    def _parse_probe_body(response: httpx.Response) -> dict[str, Any]:
        """Classify a 200 ``tools/call`` probe response from its JSON-RPC body.

        TAP-2098. Returns one of:

        - ``{"ok": True, "http_status": 200}`` — body has no ``error`` field
          (or is non-JSON / non-dict; the legacy behaviour is preserved).
        - ``{"ok": False, "http_status": 200, "gated": True, "tool", "profile",
          "suggested_profile"}`` — body carries an ``out_of_profile`` envelope
          (TAP-1616 / TAP-1972). ``suggested_profile`` is ``None`` when the
          brain pre-dates v3.19.0.
        - ``{"ok": False, "http_status": 200, "detail": <str>}`` — body carries
          a non-``out_of_profile`` JSON-RPC error.
        """
        try:
            body = response.json()
        except Exception:
            return {"ok": True, "http_status": 200}
        if not isinstance(body, dict):
            return {"ok": True, "http_status": 200}
        rpc_error = body.get("error")
        if not isinstance(rpc_error, dict):
            return {"ok": True, "http_status": 200}
        err_code = rpc_error.get("code")
        err_data = rpc_error.get("data")
        if (
            err_code == -32602
            and isinstance(err_data, dict)
            and err_data.get("reason") == "out_of_profile"
        ):
            return {
                "ok": False,
                "http_status": 200,
                "gated": True,
                "tool": err_data.get("tool") or "memory_list",
                "profile": err_data.get("profile"),
                "suggested_profile": err_data.get("suggested_profile"),
            }
        return {
            "ok": False,
            "http_status": 200,
            "detail": str(rpc_error)[:200],
        }

    @property
    def store(self) -> None:
        """Not available in HTTP mode — callers must use async BrainBridge methods."""
        return None

    # -------------------------------------------------------------------------
    # Lifecycle (HTTP overrides)
    # -------------------------------------------------------------------------

    def drain_blocking(self, timeout: float = _DRAIN_DEADLINE_SECONDS) -> dict[str, int]:
        """Drain the offline write queue via synchronous HTTP calls."""
        deadline = time.monotonic() + max(0.0, timeout)
        drained = 0
        dropped = 0
        while not self._write_queue.empty():
            if time.monotonic() >= deadline:
                break
            try:
                entry = self._write_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                httpx.post(
                    f"{self._http_url}/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "memory_save", "arguments": entry},
                    },
                    headers={**self._http_headers, **_MCP_ACCEPT_HEADERS},
                    timeout=5.0,
                    follow_redirects=True,
                )
                drained += 1
            except Exception as exc:
                _log().warning(
                    "brain_bridge.drain_blocking_http_failed",
                    error=str(exc),
                    key=entry.get("key"),
                )
                dropped += 1
        remaining = self._write_queue.qsize()
        if drained or dropped or remaining:
            _log().info(
                "brain_bridge.drain_blocking_complete",
                drained=drained,
                dropped=dropped,
                remaining=remaining,
                deadline_exceeded=time.monotonic() >= deadline,
            )
        return {"drained": drained, "dropped": dropped, "remaining": remaining}

    def close(self, drain_timeout: float = _DRAIN_DEADLINE_SECONDS) -> None:
        """Drain queued writes then close the async HTTP client.

        TAP-1744: the old implementation used the deprecated
        ``asyncio.get_event_loop()`` and silently skipped ``aclose()`` when
        called from inside a running loop (Jupyter / embedded async context),
        leaking the connection pool.  The new approach:

        * If a loop is already running → schedule ``aclose()`` as a task so
          the coroutine is awaited on the next iteration without blocking.
        * If no loop is running → use ``asyncio.run()`` for a clean
          synchronous teardown.
        * Failures are surfaced via ``logger.warning`` instead of swallowed.
        """
        try:
            self.drain_blocking(drain_timeout)
        except Exception as exc:
            _log().warning("brain_bridge.drain_on_close_failed", error=str(exc))
        client = self._http_client
        self._http_client = None
        self._session_id = None
        if client is not None:
            try:
                # Running loop detected (e.g. embedded MCP server, Jupyter).
                # Schedule aclose as a fire-and-forget task; the coroutine will
                # execute on the next event-loop iteration.
                loop = asyncio.get_running_loop()
                if loop.is_closed():
                    # TAP-5277: Cursor MCP reload closes the loop before atexit
                    # teardown — scheduling on a closed loop spam-logs
                    # "Event loop is closed". Close on a fresh loop instead.
                    self._aclose_on_fresh_loop(client)
                else:
                    loop.create_task(client.aclose())  # noqa: RUF006 — intentional fire-and-forget on shutdown
            except RuntimeError:
                # No running loop — close synchronously on a fresh loop.
                self._aclose_on_fresh_loop(client)

    @staticmethod
    def _aclose_on_fresh_loop(client: object) -> None:
        """Close *client* without touching a closed/stale event loop (TAP-5277)."""
        aclose = getattr(client, "aclose", None)
        if aclose is None:
            return
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(aclose())
        except Exception as exc:
            # Swallow closed-loop noise; real close failures still warn.
            msg = str(exc).lower()
            if "event loop is closed" in msg or "loop is closed" in msg:
                _log().debug("brain_bridge.http_client_close_skipped_closed_loop", error=str(exc))
            else:
                _log().warning("brain_bridge.http_client_close_failed", error=str(exc))
        finally:
            loop.close()


# -----------------------------------------------------------------------------
# Remote brain version probe (TAP-519)
# -----------------------------------------------------------------------------


