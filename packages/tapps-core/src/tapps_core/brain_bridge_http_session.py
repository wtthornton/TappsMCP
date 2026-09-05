"""HTTP session handshake, capability negotiation, and raw POST layer mixin.

Split out of ``brain_bridge_http_transport.py`` (TAP-6736, further split). No
behavior change: each method body below is moved byte-for-byte. Composed as
``_HttpSessionMixin`` alongside ``_HttpHealthMixin``, ``_HttpOpsMixin``, and
``BrainBridge`` into the public ``HttpBrainBridge`` class in the facade
module.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from tapps_core.brain_bridge_errors import (
    _BRAIN_VERSION_CEILING,
    _BRAIN_VERSION_FLOOR,
    _MCP_ACCEPT_HEADERS,
    _RETRY_ATTEMPTS,
    _RETRY_BASE,
    _RETRY_MAX,
    _WRITE_QUEUE_CAP,
    BRAIN_PROFILES_NARROW_OK,
    BadJsonError,
    BrainBridgeUnavailable,
    BrainMcpError,
    ToolNotInProfileError,
    _parse_out_of_profile_message,
    _raise_with_body,
    _read_tools_warm_cache,
    _tenant_override_headers,
    _write_tools_warm_cache,
    get_bridge_used_tools,
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


class _HttpSessionMixin:
    """Session handshake, capability negotiation, and raw HTTP POST layer."""

    def __init__(
        self, http_url: str, headers: dict[str, str], *, cache_dir: Path | None = None
    ) -> None:
        # Initialise shared resilience state without a local AgentBrain.
        self._failures: int = 0
        self._open_at: float | None = None
        self._write_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_WRITE_QUEUE_CAP)
        self._drain_task: asyncio.Task[None] | None = None
        self._version_check: dict[str, Any] = {
            "ok": True,
            "skipped": True,
            "degraded": False,
            "url": "",
            "floor": _BRAIN_VERSION_FLOOR,
            "ceiling": _BRAIN_VERSION_CEILING,
            "version": None,
            "errors": [],
            "warnings": [],
        }
        self._http_url: str = http_url.rstrip("/")
        self._http_headers: dict[str, str] = dict(headers)
        # TAP-1616 / TAP-1924: declare ``X-Brain-Profile`` only when the
        # header has not already been set by the factory.  Resolution order:
        #
        #   1. ``settings.memory.brain_profile`` / ``TAPPS_BRAIN_PROFILE`` env
        #      → resolved by ``build_brain_headers`` in ``_create_http_bridge``.
        #   2. ``default_profile`` arg to ``create_brain_bridge`` (caller-set
        #      minimum surface, e.g. ``"coder"`` for tapps-mcp, TAP-1924).
        #   3. This env-var fallback — covers direct construction without a
        #      factory (tests, CLI one-shots with ``settings=None``).
        #
        # When the factory already set the header (steps 1-2), the check below
        # is False and the env var is NOT re-read, avoiding a double-resolution.
        if "X-Brain-Profile" not in self._http_headers:
            env_profile = os.environ.get("TAPPS_BRAIN_PROFILE", "").strip()
            if env_profile:
                self._http_headers["X-Brain-Profile"] = env_profile
        self._http_client: httpx.AsyncClient | None = None
        # TAP-836: brain 3.10.3+ enforces the MCP streamable-HTTP session
        # lifecycle — an initialize handshake returns an Mcp-Session-Id
        # that must accompany every subsequent tools/call. Cached lazily
        # on first call; cleared via close() or when the server rejects
        # the session ID and we need to re-handshake.
        self._session_id: str | None = None
        self._session_lock: asyncio.Lock = asyncio.Lock()
        # TAP-1629: capability negotiation cache. Populated lazily on the
        # first ``_ensure_session`` via ``_negotiate_profile_locked``. ``exposed_tools``
        # is the set of MCP tool names the server's active profile reveals
        # (from ``tools/list``); ``memory_profile`` is the layer/decay/scoring
        # config returned by the brain's ``profile_info`` tool. Both are
        # advisory — surfaced via :meth:`profile_status` and used to short-
        # circuit calls in :meth:`_http_mcp_call`.
        self._negotiated: bool = False
        self._exposed_tools: frozenset[str] | None = None
        self._memory_profile: dict[str, Any] | None = None
        self._negotiation_error: str | None = None
        # TAP-2014: elevation guard (shared attribute; set by server_helpers).
        self.elevation_guard: Callable[[str], bool] | None = None
        # TAP-1927: directory for the tools-list pre-warm cache.  Resolved from
        # the project root by ``_create_http_bridge``; ``None`` disables caching.
        self._tools_cache_dir: Path | None = cache_dir

    # -------------------------------------------------------------------------
    # HTTP JSON-RPC call layer
    # -------------------------------------------------------------------------

    async def _http_mcp_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        project_id: str | None = None,
    ) -> Any:
        """Call a tapps-brain MCP tool with circuit-breaker + retry semantics."""
        if self.circuit_open:
            raise BrainBridgeUnavailable("circuit open")

        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                result = await self._do_mcp_post(tool_name, arguments, project_id=project_id)
                self._record_success()
                return result
            except BrainBridgeUnavailable:
                raise
            except ToolNotInProfileError:
                # TAP-1616: gated tools are a deterministic server decision —
                # retrying wastes time and trips the circuit breaker. Surface
                # the typed exception to the caller immediately.
                raise
            except Exception as exc:
                last_exc = exc
                self._record_failure()
                if self.circuit_open:
                    break
                if attempt < _RETRY_ATTEMPTS - 1:
                    delay = min(_RETRY_BASE * (2**attempt), _RETRY_MAX)
                    delay += random.uniform(0, delay * 0.1)  # noqa: S311
                    await asyncio.sleep(delay)

        raise BrainBridgeUnavailable(f"all retries exhausted: {last_exc}") from last_exc

    async def _ensure_session(self) -> str:
        """Return a valid MCP session id, establishing one via ``initialize``.

        brain 3.10.3+ requires the MCP streamable-HTTP session handshake
        (TAP-836). Older brains ignore the header so sending it is
        back-compat safe.
        """
        if self._session_id and self._negotiated:
            return self._session_id
        async with self._session_lock:
            if self._session_id is None:
                if self._http_client is None:
                    self._http_client = httpx.AsyncClient(
                        headers={**self._http_headers, **_MCP_ACCEPT_HEADERS},
                        timeout=30.0,
                        follow_redirects=True,
                    )
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
                response = await self._http_client.post(f"{self._http_url}/mcp/", json=init_payload)
                _raise_with_body(response, "initialize")
                session_id = response.headers.get("mcp-session-id")
                if not session_id:
                    # Older brains that don't use the session model — use a
                    # sentinel so we don't re-handshake every call.
                    session_id = "__no_session__"
                self._session_id = session_id
            # TAP-1629: negotiate capabilities inside the same lock so the
            # first batch of concurrent callers all see populated caches
            # before they short-circuit gated tools. Negotiation cannot raise
            # past this point — failures land in ``_negotiation_error``.
            if not self._negotiated:
                await self._negotiate_profile_locked()
            assert self._session_id is not None
            return self._session_id

    def _check_tools_warm_cache(self) -> Path | None:
        """Populate :attr:`_exposed_tools` from the warm-cache file if fresh.

        Extracted from :meth:`_negotiate_profile_locked` (TAP-6736) to cut its
        cyclomatic complexity — pure refactor, no behavior change. Returns the
        resolved cache path (or ``None``) so the caller can write back a
        freshly-fetched tools list.
        """
        if self._tools_cache_dir is None:
            return None
        _raw_profile = self._http_headers.get("X-Brain-Profile") or ""
        _safe_profile = re.sub(r"[^A-Za-z0-9_-]", "_", _raw_profile) if _raw_profile else ""
        _cache_path = self._tools_cache_dir / f".brain-tools-list.{_safe_profile}.json"
        _cached_tools = _read_tools_warm_cache(_cache_path)
        if _cached_tools is not None:
            self._exposed_tools = _cached_tools
            _log().debug(
                "brain_bridge.tools_list_warm_hit",
                tool_count=len(_cached_tools),
                declared_profile=_raw_profile or None,
            )
        return _cache_path

    async def _fetch_tools_list_live(
        self, extra_headers: dict[str, str], _cache_path: Path | None
    ) -> None:
        """Live ``tools/list`` MCP round-trip (skipped on warm-cache hit).

        Extracted from :meth:`_negotiate_profile_locked` (TAP-6736) — pure
        refactor, no behavior change.
        """
        try:
            tools_response = await self._http_client.post(
                f"{self._http_url}/mcp/",
                json={"jsonrpc": "2.0", "id": "negotiate_tools", "method": "tools/list"},
                headers=extra_headers,
            )
            tools_response.raise_for_status()
            tools_payload = tools_response.json()
            tools = tools_payload.get("result", {}).get("tools", [])
            tool_names: set[str] = {
                str(t["name"])
                for t in tools
                if isinstance(t, dict) and isinstance(t.get("name"), str) and t["name"]
            }
            if tool_names:
                # Only cache when we actually got a non-empty list — a malformed
                # response or empty array (impossible on a healthy brain even on
                # the narrowest profile, which always exposes brain_*) would
                # otherwise short-circuit every subsequent bridge call. Surface
                # the anomaly via ``negotiation_error`` instead.
                self._exposed_tools = frozenset(tool_names)
                if _cache_path is not None:
                    _write_tools_warm_cache(_cache_path, frozenset(tool_names))
            else:
                self._negotiation_error = "tools_list_empty"
                _log().warning(
                    "brain_bridge.tools_list_empty",
                    declared_profile=self._http_headers.get("X-Brain-Profile") or None,
                )
        except Exception as exc:
            self._negotiation_error = f"tools_list_failed: {exc}"
            _log().warning("brain_bridge.tools_list_failed", error=str(exc))

    async def _fetch_profile_info(self, extra_headers: dict[str, str]) -> None:
        """Best-effort ``profile_info`` MCP call.

        Extracted from :meth:`_negotiate_profile_locked` (TAP-6736) — pure
        refactor, no behavior change.
        """
        try:
            profile_response = await self._http_client.post(
                f"{self._http_url}/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "id": "negotiate_profile",
                    "method": "tools/call",
                    "params": {"name": "profile_info", "arguments": {}},
                },
                headers=extra_headers,
            )
            profile_response.raise_for_status()
            profile_payload = profile_response.json()
            result = profile_payload.get("result", {})
            if not result.get("isError"):
                content_items = result.get("content", [])
                if content_items and content_items[0].get("type") == "text":
                    text = content_items[0]["text"]
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        self._memory_profile = parsed
        except Exception as exc:
            _log().debug("brain_bridge.profile_info_failed", error=str(exc))

    def _log_profile_mismatch(self) -> None:
        """Log a warning/debug when the negotiated profile hides used tools.

        Extracted from :meth:`_negotiate_profile_locked` (TAP-6736) — pure
        refactor, no behavior change.
        """
        if self._exposed_tools is None:
            return
        gated_used = sorted(get_bridge_used_tools() - self._exposed_tools)
        if not gated_used:
            return
        declared = self._http_headers.get("X-Brain-Profile") or None
        if declared in BRAIN_PROFILES_NARROW_OK:
            # Expected by construction — a narrow profile deliberately
            # exposes a subset — so this fired on 100% of sessions and
            # listed every gated tool. The actionable signal is
            # ProfileMismatchError when a gated tool is actually
            # invoked; the full list stays available via
            # profile_status() for doctor and the health action. Log a
            # count so the condition remains observable without noise.
            _log().debug(
                "brain_bridge.profile_mismatch",
                declared_profile=declared,
                gated_used_count=len(gated_used),
            )
        else:
            _log().warning(
                "brain_bridge.profile_mismatch",
                declared_profile=declared,
                gated_used_tools=gated_used,
            )

    async def _negotiate_profile_locked(self) -> None:
        """Run capability negotiation while the session lock is held.

        Caller must hold :attr:`_session_lock`. Exists as a separate method
        so unit tests can drive negotiation in isolation without re-entering
        the session bootstrap.
        """
        if self._negotiated:
            return
        if self._http_client is None or self._session_id is None:
            self._negotiation_error = "session_unavailable"
            self._negotiated = True
            return

        session_id = self._session_id
        extra_headers: dict[str, str] = {}
        if session_id and session_id != "__no_session__":
            extra_headers["Mcp-Session-Id"] = session_id

        # --- tools/list warm-cache check (TAP-1927) ---------------------------
        # A session-start hook writes .tapps-mcp/.brain-tools-list.<profile>.json
        # via a background curl so the live MCP round-trip can be skipped here.
        _cache_path = self._check_tools_warm_cache()

        # --- tools/list (live MCP round-trip — skipped on warm-cache hit) ---
        if self._exposed_tools is None:
            await self._fetch_tools_list_live(extra_headers, _cache_path)

        # --- profile_info (best-effort) ------------------------------------
        await self._fetch_profile_info(extra_headers)

        self._negotiated = True
        self._log_profile_mismatch()

    def profile_status(self) -> dict[str, Any]:
        """Snapshot the negotiated brain capability profile (TAP-1629).

        Always returns a fully-shaped dict so callers (health action, doctor)
        can render predictable output even before the first session
        handshake.

        Keys:
            negotiated: True after the first :meth:`_negotiate_profile_locked` run.
            declared_profile: Value of ``X-Brain-Profile`` sent on the wire
                (``None`` when no header is set; server-side default applies).
            memory_profile: Memory layer/decay config from the brain's
                ``profile_info`` tool (``None`` if not yet fetched).
            exposed_tools: Sorted list of tool names the server's ``tools/list``
                returned for this profile (``[]`` if not yet fetched).
            bridge_used_tools: Sorted list of tools the bridge actually calls.
            gated_used_tools: Sorted list of bridge tools missing from
                ``exposed_tools`` — these will raise
                :class:`ProfileMismatchError` when invoked.
            profile_mismatch: True when ``gated_used_tools`` is non-empty.
            negotiation_error: Last error from negotiation (``None`` on success).
        """
        declared = self._http_headers.get("X-Brain-Profile") or None
        exposed = self._exposed_tools
        memory_profile_name: str | None = None
        if isinstance(self._memory_profile, dict):
            name = self._memory_profile.get("name")
            if isinstance(name, str):
                memory_profile_name = name
        if exposed is None:
            return {
                "negotiated": self._negotiated,
                "declared_profile": declared,
                "memory_profile_name": memory_profile_name,
                "memory_profile": self._memory_profile,
                "exposed_tools": [],
                "bridge_used_tools": sorted(get_bridge_used_tools()),
                "gated_used_tools": [],
                "profile_mismatch": False,
                "negotiation_error": self._negotiation_error,
            }
        gated_used = sorted(get_bridge_used_tools() - exposed)
        return {
            "negotiated": True,
            "declared_profile": declared,
            "memory_profile_name": memory_profile_name,
            "memory_profile": self._memory_profile,
            "exposed_tools": sorted(exposed),
            "bridge_used_tools": sorted(get_bridge_used_tools()),
            "gated_used_tools": gated_used,
            "profile_mismatch": bool(gated_used),
            "negotiation_error": self._negotiation_error,
        }

    @staticmethod
    def _raise_for_rpc_error(rpc_error: Any, tool_name: str) -> None:
        """Raise the typed exception for a JSON-RPC ``error`` envelope.

        Extracted from :meth:`_do_mcp_post` (TAP-6736) to cut its cyclomatic
        complexity — pure refactor, no behavior change.
        """
        err_code = rpc_error.get("code") if isinstance(rpc_error, dict) else None
        err_data = rpc_error.get("data") if isinstance(rpc_error, dict) else None
        # TAP-1967 / TAP-1968 / TAP-1969 (v3.19.0+): malformed ``*_json``
        # argument on KG MCP tools. Surface ``field`` + ``detail`` so the
        # typo is visible to the caller instead of silent no-op.
        if isinstance(err_data, dict) and err_data.get("error") == "bad_json":
            bad_field = err_data.get("field") or ""
            bad_detail = err_data.get("detail") or ""
            raise BadJsonError(
                f"tapps-brain rejected malformed JSON argument {bad_field!r}: {bad_detail}",
                code=err_code,
                data=err_data,
                tool_name=tool_name,
                field=bad_field,
                detail=bad_detail,
            )
        # TAP-1616: ``-32602 INVALID_PARAMS`` with
        # ``data.reason == "out_of_profile"`` is the wire signal that the
        # tool is hidden by the active server-side profile (not removed
        # — that stays ``-32601 METHOD_NOT_FOUND``). Surface it as a
        # distinct exception so callers can dispatch.
        if (
            err_code == -32602
            and isinstance(err_data, dict)
            and err_data.get("reason") == "out_of_profile"
        ):
            gated_profile = err_data.get("profile")
            gated_tool = err_data.get("tool") or tool_name
            # TAP-1972 (v3.19.0+): server may include the smallest profile
            # that exposes the denied tool; tolerate absence on older brains.
            suggested = err_data.get("suggested_profile")
            raise ToolNotInProfileError(
                f"tapps-brain tool {gated_tool!r} is hidden by profile {gated_profile!r}",
                tool=gated_tool,
                profile=gated_profile,
                data=err_data,
                suggested_profile=suggested,
            )
        raise BrainMcpError(
            f"tapps-brain MCP RPC error: {rpc_error}",
            code=err_code,
            data=err_data,
            tool_name=tool_name,
        )

    @staticmethod
    def _raise_for_error_result(result: dict[str, Any], tool_name: str) -> None:
        """Raise the typed exception for a ``result.isError=true`` envelope.

        Extracted from :meth:`_do_mcp_post` (TAP-6736) to cut its cyclomatic
        complexity — pure refactor, no behavior change.
        """
        content = result.get("content", [])
        msg = content[0].get("text", str(result)) if content else str(result)
        # TAP-1616: tapps-brain raises ``McpError(ErrorData(code=-32602,
        # data={"reason": "out_of_profile", ...}))`` for gated tools, but
        # ``mcp`` 1.27.x's FastMCP HTTP transport currently swallows the
        # ``data`` payload and surfaces the failure as ``result.isError=true``
        # with a text-only message — the documented JSON-RPC contract
        # never reaches the wire. Parse the canonical message shape
        # (``Tool 'X' is not available in profile 'Y'.``) so callers see
        # the typed exception today; the JSON-RPC branch above will keep
        # working once upstream surfaces ``ErrorData`` correctly.
        gated = _parse_out_of_profile_message(msg)
        if gated is not None:
            gated_tool, gated_profile = gated
            raise ToolNotInProfileError(
                f"tapps-brain tool {gated_tool!r} is hidden by profile {gated_profile!r}",
                tool=gated_tool,
                profile=gated_profile,
                data={
                    "reason": "out_of_profile",
                    "tool": gated_tool,
                    "profile": gated_profile,
                    "transport": "is_error_envelope",
                },
            )
        raise RuntimeError(f"tapps-brain tool error: {msg}")

    async def _post_tools_call(
        self, tool_name: str, arguments: dict[str, Any], project_id: str
    ) -> httpx.Response:
        """POST the ``tools/call`` payload, retrying once on a rejected session.

        Extracted from :meth:`_do_mcp_post` (TAP-6736) to cut its cyclomatic
        complexity — pure refactor, no behavior change.
        """
        session_id = await self._ensure_session()
        # TAP-1629: short-circuit calls to tools the negotiated profile does
        # not expose. Skips the wire round-trip and raises the same typed
        # error agents already handle (``ToolNotInProfileError`` subclass).
        # TAP-2100: preflight short-circuit removed. The brain's v3.19.0
        # ``full``/``operator`` profiles default to an 8-tool eager
        # ``tools/list`` (TAP-1985) — the remaining 51 tools carry
        # ``defer_loading: true`` and are still callable via ``tools/call``,
        # but absent from the catalog. Comparing against ``_exposed_tools``
        # therefore produces false rejections on 22 of 27 ``_BRIDGE_USED_TOOLS``
        # under v3.19.0+. ``_exposed_tools`` is still populated for
        # diagnostics (``profile_status``, ``tapps doctor check_brain_profile``)
        # but the wire is now authoritative — a genuinely gated tool still
        # surfaces as :class:`ToolNotInProfileError` from the brain's
        # ``-32602 INVALID_PARAMS`` response, just one round-trip later.
        extra_headers = _tenant_override_headers(project_id)
        if session_id and session_id != "__no_session__":
            extra_headers["Mcp-Session-Id"] = session_id
        params: dict[str, Any] = {"name": tool_name, "arguments": arguments}
        if project_id:
            params["_meta"] = {"project_id": project_id}
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": params,
        }
        response = await self._http_client.post(
            f"{self._http_url}/mcp/", json=payload, headers=extra_headers
        )
        # If the server rejects the session, drop it and retry once with a
        # fresh handshake. 404 = session not found (common after brain
        # restart); 400 with "Missing session ID" indicates we never got
        # an Mcp-Session-Id header in the first place.
        if response.status_code in {400, 404} and self._session_id:
            self._session_id = None
            session_id = await self._ensure_session()
            extra_headers = _tenant_override_headers(project_id)
            if session_id != "__no_session__":
                extra_headers["Mcp-Session-Id"] = session_id
            response = await self._http_client.post(
                f"{self._http_url}/mcp/", json=payload, headers=extra_headers
            )
        return response

    async def _do_mcp_post(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        project_id: str | None = None,
    ) -> Any:
        """POST a single ``tools/call`` to ``{brain_http_url}/mcp``."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                headers={**self._http_headers, **_MCP_ACCEPT_HEADERS},
                timeout=30.0,
                follow_redirects=True,
            )
        response = await self._post_tools_call(tool_name, arguments, (project_id or "").strip())
        _raise_with_body(response, tool_name)
        data: dict[str, Any] = response.json()

        rpc_error = data.get("error")
        if rpc_error:
            self._raise_for_rpc_error(rpc_error, tool_name)

        result: dict[str, Any] = data.get("result", {})
        if result.get("isError"):
            self._raise_for_error_result(result, tool_name)

        content_items: list[dict[str, Any]] = result.get("content", [])
        if content_items and content_items[0].get("type") == "text":
            text = content_items[0]["text"]
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"value": text}
        return result
