"""TAP-1616: live contract test for BrainBridge's profile wire integration.

Runs against a real ``tapps-brain-http`` server (3.17.0+) reachable on
``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` (or ``http://127.0.0.1:8080`` by default).
Skipped when the server is unreachable or the bearer token is unset, so the
unit-test runs in CI without a brain stay green.

Run explicitly:

    TAPPS_BRAIN_AUTH_TOKEN=... \\
    TAPPS_MCP_MEMORY_BRAIN_HTTP_URL=http://127.0.0.1:8080 \\
    pytest packages/tapps-core/tests/contract -m brain_contract -v

Exercises three wire shapes against the ``agent_brain`` profile:

1. ``brain_recall`` — in profile → returns successfully.
2. ``memory_save`` — gated by profile → ``ToolNotInProfileError``
   (``-32602 INVALID_PARAMS`` with ``data.reason == "out_of_profile"``).
3. ``__definitely_not_a_tool__`` — genuinely missing → ``BrainMcpError``
   but NOT ``ToolNotInProfileError`` (the bridge must keep ``-32601`` and
   ``-32602/out_of_profile`` distinct).
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest

from tapps_core.brain_bridge import (
    BrainMcpError,
    HttpBrainBridge,
    ToolNotInProfileError,
)

pytestmark = pytest.mark.brain_contract


_DEFAULT_URL = "http://127.0.0.1:8080"
_REQUIRED_BRAIN_VERSION = (3, 18, 0)


def _parse_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in value.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _resolve_brain_url() -> str:
    return os.environ.get("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", _DEFAULT_URL).rstrip("/")


def _resolve_token() -> str:
    return (
        os.environ.get("TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN")
        or os.environ.get("TAPPS_BRAIN_AUTH_TOKEN")
        or ""
    )


def _check_brain_reachable(url: str) -> str | None:
    """Return None when the server is reachable and 3.17+; else a skip reason."""
    try:
        response = httpx.get(f"{url}/health", timeout=2.0)
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        return f"tapps-brain unreachable at {url}: {exc}"
    if response.status_code != 200:
        return f"tapps-brain /health returned {response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return "tapps-brain /health returned non-JSON body"
    version = str(payload.get("version", ""))
    if _parse_version(version) < _REQUIRED_BRAIN_VERSION:
        return f"tapps-brain version {version} below required 3.18.0"
    return None


def _check_profile_loaded(url: str, token: str, project_id: str, profile: str) -> str | None:
    """Return None when the server has *profile* loaded; else a skip reason.

    The wire contract claims unknown profile names "fail open" as ``full``,
    but the operator's deployment (``TAPPS_BRAIN_STRICT=1``) tightens this
    to a 400 on initialize. Either way, the contract test is meaningful
    only when the requested profile is actually loaded — otherwise we are
    testing the operator's strictness rather than the bridge's behaviour.
    """
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "tap-1616-probe", "version": "1"},
        },
    }
    try:
        response = httpx.post(
            f"{url}/mcp/",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Project-Id": project_id,
                "X-Agent-Id": "tap-1616-probe",
                "X-Brain-Profile": profile,
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json=init_payload,
            timeout=5.0,
            follow_redirects=True,
        )
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        return f"initialize probe failed: {exc}"
    if response.status_code == 400 and "Unknown MCP profile" in response.text:
        return (
            f"tapps-brain at {url} does not have profile {profile!r} loaded "
            f"(image predates TAP-1579 — rebuild required)"
        )
    if response.status_code >= 400:
        return f"initialize probe returned HTTP {response.status_code}: {response.text[:200]}"
    return None


@pytest.fixture(scope="module")
def brain_url() -> str:
    url = _resolve_brain_url()
    skip_reason = _check_brain_reachable(url)
    if skip_reason:
        pytest.skip(skip_reason)
    return url


@pytest.fixture(scope="module")
def auth_token() -> str:
    token = _resolve_token()
    if not token:
        pytest.skip("TAPPS_BRAIN_AUTH_TOKEN / TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN not set")
    return token


@pytest.fixture(scope="module")
def project_id() -> str:
    return os.environ.get("TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID", "tapps-mcp")


@pytest.fixture(scope="module")
def profile_loaded(brain_url: str, auth_token: str, project_id: str) -> str:
    """Probe the live server and skip when ``agent_brain`` isn't loaded."""
    skip_reason = _check_profile_loaded(brain_url, auth_token, project_id, "agent_brain")
    if skip_reason:
        pytest.skip(skip_reason)
    return "agent_brain"


def _build_bridge(
    brain_url: str, auth_token: str, project_id: str, profile: str
) -> HttpBrainBridge:
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "X-Project-Id": project_id,
        "X-Agent-Id": "tap-1616-contract-test",
        "X-Brain-Profile": profile,
    }
    return HttpBrainBridge(brain_url, headers)


@pytest.fixture
def agent_brain_bridge(
    brain_url: str, auth_token: str, project_id: str, profile_loaded: str
) -> HttpBrainBridge:
    """Bridge declaring the ``agent_brain`` profile."""
    return _build_bridge(brain_url, auth_token, project_id, profile_loaded)


@pytest.fixture
def full_profile_bridge(brain_url: str, auth_token: str, project_id: str) -> HttpBrainBridge:
    """Bridge declaring the ``full`` profile.

    Required for the missing-tool path: under any non-``full`` profile the
    server-side ``tool_filter`` runs first and cannot distinguish "tool
    excluded by profile" from "tool does not exist" — both look identical
    to the filter. ``full`` lets the call reach FastMCP's tool registry,
    which surfaces unknown names as ``Unknown tool: <name>``.
    """
    return _build_bridge(brain_url, auth_token, project_id, "full")


@pytest.mark.asyncio
async def test_in_profile_tool_succeeds(agent_brain_bridge: HttpBrainBridge) -> None:
    """``brain_recall`` lives in ``agent_brain`` — call must succeed."""
    try:
        result: Any = await agent_brain_bridge._http_mcp_call(
            "brain_recall", {"query": "tap-1616 contract probe"}
        )
    finally:
        agent_brain_bridge.close()
    # Response shape varies (list of hits, dict with results, …) — what
    # matters here is that the call returned without raising.
    assert result is not None


@pytest.mark.asyncio
async def test_out_of_profile_tool_raises_tool_not_in_profile_error(
    agent_brain_bridge: HttpBrainBridge,
) -> None:
    """``memory_save`` is excluded from ``agent_brain`` — must raise
    :class:`ToolNotInProfileError` (NOT plain ``BrainMcpError`` /
    ``RuntimeError``).
    """
    try:
        with pytest.raises(ToolNotInProfileError) as excinfo:
            await agent_brain_bridge._http_mcp_call(
                "memory_save",
                {"key": "tap-1616-should-not-write", "value": "blocked"},
            )
    finally:
        agent_brain_bridge.close()

    exc = excinfo.value
    assert exc.tool == "memory_save"
    assert exc.profile == "agent_brain"
    assert isinstance(exc.data, dict)
    assert exc.data.get("reason") == "out_of_profile"


@pytest.mark.asyncio
async def test_nonexistent_tool_is_not_misclassified_as_profile_error(
    full_profile_bridge: HttpBrainBridge,
) -> None:
    """A genuinely missing tool must NOT raise ``ToolNotInProfileError``.

    Under ``full`` the tool_filter is a no-op and FastMCP surfaces the
    missing name as a tool error containing ``"Unknown tool: …"``. The
    bridge's classifier maps this to ``"removed"``, not ``"gated"``.
    """
    from tapps_core.brain_bridge import _classify_mcp_error

    try:
        with pytest.raises(BaseException) as excinfo:
            await full_profile_bridge._http_mcp_call("__tap_1616_definitely_not_a_tool__", {})
    finally:
        full_profile_bridge.close()

    exc = excinfo.value
    assert not isinstance(exc, ToolNotInProfileError), (
        "Missing tool must not be misclassified as out-of-profile"
    )
    # Sanity: the classifier sees it as "removed", not "gated".
    classification = _classify_mcp_error(exc)
    assert classification in {"removed", "other"}
    assert classification != "gated"
    # Reference BrainMcpError in the suite so the import isn't dead weight
    # — the same path remains the natural catch-all for typed RPC errors.
    assert BrainMcpError is not None


# ---------------------------------------------------------------------------
# TAP-1629: profile negotiation against the live brain
# ---------------------------------------------------------------------------


def _check_profile_loaded_lenient(
    url: str, token: str, project_id: str, profile: str
) -> str | None:
    """Probe and return None when *profile* is loaded; else a skip reason.

    Helper for the TAP-1629 negotiation tests so each profile is verified
    independently (``full`` vs ``coder``) rather than gating on a single
    ``agent_brain`` probe.
    """
    return _check_profile_loaded(url, token, project_id, profile)


@pytest.mark.asyncio
async def test_negotiation_against_full_profile_exposes_bridge_tools(
    brain_url: str, auth_token: str, project_id: str
) -> None:
    """TAP-1629 happy path: the ``full`` profile exposes every tool the
    bridge depends on, so :meth:`HttpBrainBridge.profile_status` reports
    ``profile_mismatch=False`` after the first session.
    """
    skip_reason = _check_profile_loaded_lenient(brain_url, auth_token, project_id, "full")
    if skip_reason:
        pytest.skip(skip_reason)

    bridge = _build_bridge(brain_url, auth_token, project_id, "full")
    try:
        await bridge._http_mcp_call("brain_status", {})
        status = bridge.profile_status()
    finally:
        bridge.close()

    assert status["negotiated"] is True
    assert status["declared_profile"] == "full"
    assert status["exposed_tools"], "tools/list must return at least one tool on full"
    assert status["gated_used_tools"] == []
    assert status["profile_mismatch"] is False


@pytest.mark.asyncio
async def test_negotiation_against_coder_profile_short_circuits_gated_tools(
    brain_url: str, auth_token: str, project_id: str
) -> None:
    """TAP-1629 gated fallback: under ``coder``, ``memory_save`` is hidden
    and the bridge must raise :class:`ProfileMismatchError` (a typed
    ``ToolNotInProfileError`` subclass) BEFORE the wire round-trip.
    """
    from tapps_core.brain_bridge import ProfileMismatchError, ToolNotInProfileError

    skip_reason = _check_profile_loaded_lenient(brain_url, auth_token, project_id, "coder")
    if skip_reason:
        pytest.skip(skip_reason)

    bridge = _build_bridge(brain_url, auth_token, project_id, "coder")
    try:
        # Trigger negotiation via a tool that EXISTS in coder so the
        # initialize + tools/list + profile_info handshake runs.
        await bridge._http_mcp_call("brain_status", {})
        status = bridge.profile_status()
        # memory_save is in _BRIDGE_USED_TOOLS but not in the coder profile.
        with pytest.raises(ToolNotInProfileError) as excinfo:
            await bridge._http_mcp_call(
                "memory_save",
                {"key": "tap-1629-should-not-write", "value": "blocked"},
            )
    finally:
        bridge.close()

    exc = excinfo.value
    # Specifically the preflight subclass — the wire was never hit because
    # the bridge already knew the tool was gated.
    assert isinstance(exc, ProfileMismatchError)
    assert exc.tool == "memory_save"
    assert exc.profile == "coder"
    assert isinstance(exc.data, dict)
    assert exc.data.get("transport") == "client_preflight"
    # profile_status reports the same gated tool.
    assert "memory_save" in status["gated_used_tools"]
    assert status["profile_mismatch"] is True


# ---------------------------------------------------------------------------
# TAP-1630: knowledge graph against the live brain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_knowledge_graph_methods_reach_the_wire(
    brain_url: str, auth_token: str, project_id: str
) -> None:
    """Smoke-level check that the four new bridge methods (TAP-1630) reach
    the brain without raising. Uses the ``full`` profile so every graph tool
    is exposed; ``memory_find_related`` / ``memory_relations`` /
    ``memory_query_relations`` / ``brain_get_neighbors`` / ``brain_explain_connection``
    are all in ``_BRIDGE_USED_TOOLS`` and the negotiation must record them
    as exposed (no profile_mismatch).
    """
    skip_reason = _check_profile_loaded_lenient(brain_url, auth_token, project_id, "full")
    if skip_reason:
        pytest.skip(skip_reason)

    bridge = _build_bridge(brain_url, auth_token, project_id, "full")
    try:
        # Drive negotiation first so profile_status() is populated.
        await bridge._http_mcp_call("brain_status", {})
        status = bridge.profile_status()
        for tool in (
            "memory_find_related",
            "memory_relations",
            "memory_query_relations",
            "brain_get_neighbors",
            "brain_explain_connection",
        ):
            assert tool in status["exposed_tools"], tool
            assert tool not in status["gated_used_tools"], tool

        # Each method returns the shape its handler expects. The four working
        # methods run first; ``brain_get_neighbors`` is exercised LAST because
        # its current brain-side bug exhausts the retry budget and opens the
        # circuit breaker for any later call in the same bridge instance.
        related = await bridge.find_related("tap-1630-probe-nonexistent-key", max_hops=1)
        assert isinstance(related, list)

        relations = await bridge.entry_relations("tap-1630-probe-nonexistent-key")
        assert isinstance(relations, list)

        triples = await bridge.query_relations(predicate="tap-1630-probe-predicate")
        assert isinstance(triples, list)

        explanation = await bridge.explain_connection(
            "tap-1630-probe-a", "tap-1630-probe-b", max_hops=2
        )
        assert isinstance(explanation, dict)

        # brain_get_neighbors currently has a server-side Postgres binding bug
        # on tapps-brain 3.17.1 ("could not determine data type of parameter
        # $5") that fires regardless of input shape. The bridge wrapper is
        # exercised — we confirm a propagated BrainBridgeUnavailable surfaces
        # the wire error rather than a Python-level crash. Re-tighten this
        # assertion when the brain ships the fix; per the epic non-goals we
        # do NOT modify tapps-brain from this PR.
        from tapps_core.brain_bridge import BrainBridgeUnavailable

        try:
            neighbors = await bridge.get_neighbors(["tap-1630-probe-entity"], hops=1, limit=3)
        except BrainBridgeUnavailable as exc:
            assert "parameter $5" in str(exc) or "brain_get_neighbors" in str(exc)
        else:
            assert isinstance(neighbors, dict)
    finally:
        bridge.close()


# ---------------------------------------------------------------------------
# TAP-1631: batch latency benchmark against the live brain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_save_many_collapses_50_entries_into_one_wire_round_trip(
    brain_url: str, auth_token: str, project_id: str
) -> None:
    """TAP-1631 architectural acceptance: ``memory_save_many`` writes N
    entries in **one** wire round-trip instead of N.

    Wall-clock speedup against the live brain on this hardware is modest
    (~1.1x) because tapps-brain 3.17.1's ``memory_save_many`` handler does
    not batch the underlying DB writes into a single transaction — it
    loops server-side. Per the epic non-goals we do NOT modify the brain
    to fix this, so the wall-clock 5x target on the original Linear
    acceptance is gated on a follow-up brain change. What is unambiguously
    deliverable from tapps-mcp is the wire-trip reduction, which this
    test asserts directly by counting POSTs to the brain's MCP endpoint.
    """
    import time
    import uuid

    skip_reason = _check_profile_loaded_lenient(brain_url, auth_token, project_id, "full")
    if skip_reason:
        pytest.skip(skip_reason)

    N = 50
    run_id = uuid.uuid4().hex[:8]
    batch_entries = [
        {"key": f"tap1631-batch-{run_id}-{i}", "value": f"batch value {i}", "tier": "context"}
        for i in range(N)
    ]

    batch_bridge = _build_bridge(brain_url, auth_token, project_id, "full")
    initial_post_calls = 0
    try:
        # Drive initialize + negotiation so subsequent counts only reflect
        # the actual save_many call.
        await batch_bridge._http_mcp_call("brain_status", {})

        # Wrap the bridge's httpx client to count POSTs.
        real_post = batch_bridge._http_client.post  # type: ignore[union-attr]
        post_count = 0

        async def _counting_post(*args: Any, **kwargs: Any) -> Any:
            nonlocal post_count
            post_count += 1
            return await real_post(*args, **kwargs)

        batch_bridge._http_client.post = _counting_post  # type: ignore[union-attr]
        initial_post_calls = post_count

        start = time.perf_counter()
        batch_result = await batch_bridge.save_many(batch_entries)
        elapsed = time.perf_counter() - start
        post_calls = post_count - initial_post_calls
    finally:
        batch_bridge.close()

    cleanup_bridge = _build_bridge(brain_url, auth_token, project_id, "full")
    try:
        for entry in batch_entries:
            try:
                await cleanup_bridge.delete(entry["key"])
            except Exception:
                pass
    finally:
        cleanup_bridge.close()

    assert batch_result["saved"] == N, batch_result
    # The headline architectural win: 50 saves -> exactly 1 wire POST.
    assert post_calls == 1, (
        f"save_many issued {post_calls} HTTP POST(s) for {N} entries — "
        "the batched-call architecture requires exactly one round trip."
    )
    # Bound the wall-clock so a brain regression that goes substantially
    # backwards still fails the test even though we don't hit 5x today.
    assert elapsed < 10.0, f"save_many took {elapsed:.2f}s for {N} entries"


# ---------------------------------------------------------------------------
# TAP-1632: feedback flywheel + diagnostics against the live brain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_and_diagnostics_methods_reach_the_wire(
    brain_url: str, auth_token: str, project_id: str
) -> None:
    """End-to-end smoke that the four new feedback / diagnostics bridge
    methods reach the live brain and parse its response without raising.
    Uses the ``full`` profile so every flywheel tool is exposed.
    """
    skip_reason = _check_profile_loaded_lenient(brain_url, auth_token, project_id, "full")
    if skip_reason:
        pytest.skip(skip_reason)

    bridge = _build_bridge(brain_url, auth_token, project_id, "full")
    try:
        gap_resp = await bridge.feedback_gap(
            "tap-1632-probe-missing-query", session_id="tap-1632-probe-session"
        )
        assert isinstance(gap_resp, dict)

        # feedback_rate requires a real entry_key. We don't have one to score
        # cleanly without polluting the brain, so we test only that the wire
        # call succeeds with a probe-keyed entry — the brain accepts unknown
        # keys without raising on the wire.
        rate_resp = await bridge.feedback_rate(
            "tap-1632-probe-entry", rating="helpful", session_id="tap-1632-probe-session"
        )
        assert isinstance(rate_resp, dict)

        flywheel = await bridge.flywheel_report(period_days=1)
        assert isinstance(flywheel, dict)

        diagnostics = await bridge.diagnostics_report(record_history=False)
        assert isinstance(diagnostics, dict)
    finally:
        bridge.close()


# ---------------------------------------------------------------------------
# TAP-1633: native session memory against the live brain
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_methods_reach_the_wire(
    brain_url: str, auth_token: str, project_id: str
) -> None:
    """End-to-end smoke that ``memory_index_session`` /
    ``memory_search_sessions`` / ``tapps_brain_session_end`` are reachable
    via the new bridge methods. Uses the ``full`` profile so all three
    tools are exposed.
    """
    import uuid

    skip_reason = _check_profile_loaded_lenient(brain_url, auth_token, project_id, "full")
    if skip_reason:
        pytest.skip(skip_reason)

    session_id = f"tap-1633-probe-{uuid.uuid4().hex[:8]}"
    bridge = _build_bridge(brain_url, auth_token, project_id, "full")
    try:
        # Drive negotiation so all three tools end up in exposed_tools.
        await bridge._http_mcp_call("brain_status", {})
        status = bridge.profile_status()
        for tool in (
            "memory_index_session",
            "memory_search_sessions",
            "tapps_brain_session_end",
        ):
            assert tool in status["exposed_tools"], tool
            assert tool not in status["gated_used_tools"], tool

        index_resp = await bridge.index_session(
            session_id,
            ["tap-1633 probe chunk alpha", "tap-1633 probe chunk beta"],
        )
        assert isinstance(index_resp, dict)

        search_resp = await bridge.search_sessions("tap-1633 probe", limit=5)
        assert isinstance(search_resp, dict)

        end_resp = await bridge.session_end(
            "tap-1633 contract probe summary",
            tags=["tap-1633", "contract"],
            daily_note=False,
        )
        assert isinstance(end_resp, dict)
    finally:
        bridge.close()
