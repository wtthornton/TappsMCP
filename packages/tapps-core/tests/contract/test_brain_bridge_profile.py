"""TAP-1616: live contract test for BrainBridge's profile wire integration.

Runs writes (``memory_save``, ``memory_save_many``) against a real
``tapps-brain-http`` server (3.17.0+). Requires ``TAPPS_BRAIN_CONTRACT_TEST_URL``
to name a **disposable** brain instance explicitly — see the TAP-6803 note
below. Skipped (loudly) when that env var is unset, so a default ``pytest``
run never touches a live brain.

TAP-6803: this file used to default onto ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL``
/ ``http://127.0.0.1:8080`` — the project's *ambient* brain config — and a
plain ``uv run pytest`` in a dev environment with a reachable brain and an
auth token in the environment silently wrote 55 real entries (``memory_save``
+ ``memory_save_many``, best-effort cleanup only) into the live
``tapps-mcp`` project. ``TAPPS_BRAIN_CONTRACT_TEST_URL`` is a distinct env
var precisely so that having ``TAPPS_MCP_MEMORY_BRAIN_HTTP_URL`` set for
normal MCP operation can never accidentally satisfy this gate.

Run explicitly, pointed at a disposable brain instance:

    TAPPS_BRAIN_AUTH_TOKEN=... \\
    TAPPS_BRAIN_CONTRACT_TEST_URL=http://127.0.0.1:8080 \\
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

import contextlib
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


_REQUIRED_BRAIN_VERSION = (3, 28, 0)
#: TAP-6803: the ONLY env var that can point this suite at a brain to write
#: into. Deliberately distinct from TAPPS_MCP_MEMORY_BRAIN_HTTP_URL (normal
#: MCP operation config) so the latter being set can never accidentally
#: satisfy this gate and re-enable writes against the shared/production brain.
_CONTRACT_TEST_URL_ENV = "TAPPS_BRAIN_CONTRACT_TEST_URL"


def _parse_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in value.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _resolve_or_skip_brain_url() -> str:
    """Resolve the disposable contract-test brain URL, or skip loudly.

    TAP-6803: never reads TAPPS_MCP_MEMORY_BRAIN_HTTP_URL or any
    ``.tapps-mcp.yaml`` config as a fallback — those name the project's
    ambient/production brain. Only ``TAPPS_BRAIN_CONTRACT_TEST_URL``, set
    explicitly by the operator to a disposable instance, can unlock writes.
    """
    url = os.environ.get(_CONTRACT_TEST_URL_ENV, "").strip()
    if not url:
        pytest.skip(
            f"{_CONTRACT_TEST_URL_ENV} not set — this suite performs real "
            "writes (memory_save, memory_save_many) and refuses to default "
            "onto the ambient/project brain config (TAP-6803). Set it to a "
            "disposable tapps-brain instance to run this contract suite."
        )
    return url.rstrip("/")


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
        return f"tapps-brain version {version} below required 3.28.0"
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
    url = _resolve_or_skip_brain_url()
    skip_reason = _check_brain_reachable(url)
    if skip_reason:
        pytest.skip(skip_reason)
    return url


def test_default_run_makes_zero_brain_calls_without_the_disposable_url_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TAP-6803 guard: a default run (TAPPS_BRAIN_CONTRACT_TEST_URL unset)
    must refuse before any network call — even when the project's ambient
    TAPPS_MCP_MEMORY_BRAIN_HTTP_URL is set and points at a reachable brain,
    which is exactly the environment that caused the original data-loss
    incident (55 real entries written under project id ``tapps-mcp``).
    """
    monkeypatch.delenv(_CONTRACT_TEST_URL_ENV, raising=False)
    # The ambient config that USED to be silently read as a fallback before
    # this gate existed — confirm it is now inert for this file.
    monkeypatch.setenv("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "http://127.0.0.1:8080")

    def _fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            f"brain_contract suite made a network call without the {_CONTRACT_TEST_URL_ENV} opt-in"
        )

    monkeypatch.setattr(httpx, "get", _fail_if_called)
    monkeypatch.setattr(httpx, "post", _fail_if_called)

    with pytest.raises(pytest.skip.Exception):
        _resolve_or_skip_brain_url()


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
    """TAP-1629 happy path: the ``full`` profile exposes bridge tools.

    Under tapps-brain v3.19.0+ the server uses deferred loading (Tool Search
    BETA) so ``tools/list`` only returns the eager subset (~8 tools).
    Bridge-used tools absent from ``tools/list`` show up in
    ``gated_used_tools`` for diagnostic purposes but are still callable on
    the wire — the preflight short-circuit was removed in TAP-2100. The key
    invariant is that negotiation completes and the eager tools are present.
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
    # With deferred loading (v3.19.0+), only eager tools appear in tools/list.
    # Deferred tools are callable on the wire but absent from exposed_tools.
    # We verify the eager-loaded bridge tools are present; gated_used_tools
    # may be non-empty (deferred tools) without indicating a real profile issue.
    _EAGER_BRIDGE_TOOLS = {"memory_find_related", "brain_get_neighbors", "brain_explain_connection"}
    for tool in _EAGER_BRIDGE_TOOLS:
        assert tool in status["exposed_tools"], (
            f"expected eager bridge tool {tool!r} in exposed_tools; "
            f"got {sorted(status['exposed_tools'])}"
        )


@pytest.mark.asyncio
async def test_negotiation_against_coder_profile_surfaces_wire_denial(
    brain_url: str, auth_token: str, project_id: str
) -> None:
    """TAP-2100: under ``coder``, ``memory_save`` is hidden and the brain
    rejects it on the wire with ``-32602 out_of_profile``. The bridge no
    longer preflight-rejects — the wire is authoritative for the gating
    decision (the preflight produced false rejections under v3.19.0's
    deferred-loading catalog and was removed). ``profile_status`` still
    reports the diagnostic mismatch.
    """
    from tapps_core.brain_bridge import ToolNotInProfileError

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
                {"key": "tap-2100-should-not-write", "value": "blocked"},
            )
    finally:
        bridge.close()

    exc = excinfo.value
    assert exc.tool == "memory_save"
    assert exc.profile == "coder"
    assert isinstance(exc.data, dict)
    # Wire-origin denial — NOT the client_preflight transport tag (that
    # only came from the now-removed preflight short-circuit).
    assert exc.data.get("transport") != "client_preflight"
    # profile_status still reports the same gated tool for diagnostics.
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
    the brain without raising. Uses the ``full`` profile.

    Under tapps-brain v3.19.0+ the server uses deferred loading (Tool Search
    BETA), so ``tools/list`` only returns eager tools. ``memory_relations`` and
    ``memory_query_relations`` are deferred — they are callable on the wire but
    will not appear in ``exposed_tools``. We check only the eager graph tools
    for profile exposure and rely on the method calls below to verify the
    deferred tools reach the wire.
    """
    skip_reason = _check_profile_loaded_lenient(brain_url, auth_token, project_id, "full")
    if skip_reason:
        pytest.skip(skip_reason)

    bridge = _build_bridge(brain_url, auth_token, project_id, "full")
    try:
        # Drive negotiation first so profile_status() is populated.
        await bridge._http_mcp_call("brain_status", {})
        status = bridge.profile_status()
        # Only check eager-loaded graph tools in exposed_tools.
        # memory_relations / memory_query_relations are deferred under v3.19.0+.
        for tool in (
            "memory_find_related",
            "brain_get_neighbors",
            "brain_explain_connection",
        ):
            assert tool in status["exposed_tools"], tool

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

    # TAP-5841: an absolute wall-clock bound on a live external service
    # measures how loaded the box is, not how fast the brain is — this same
    # call runs in ~1s solo and took 11.44s with 20 xdist workers sharing one
    # brain, so the old ``elapsed < 10.0`` failed on machine contention alone.
    # Time a serial reference in the same run instead: both halves absorb
    # identical contention, so the ratio still catches a brain that regressed
    # while the noise divides out.
    serial_ref_count = 5
    ref_entries = [
        {"key": f"tap1631-serial-{run_id}-{i}", "value": f"serial value {i}", "tier": "context"}
        for i in range(serial_ref_count)
    ]
    ref_bridge = _build_bridge(brain_url, auth_token, project_id, "full")
    try:
        await ref_bridge._http_mcp_call("brain_status", {})
        ref_start = time.perf_counter()
        for entry in ref_entries:
            await ref_bridge.save(entry["key"], entry["value"], tier=entry["tier"])
        serial_per_entry = (time.perf_counter() - ref_start) / serial_ref_count
        for entry in ref_entries:
            with contextlib.suppress(Exception):
                await ref_bridge.delete(entry["key"])
    finally:
        ref_bridge.close()

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
    # Bound the cost against the same-run serial reference so a brain
    # regression that goes substantially backwards still fails the test even
    # though we don't hit 5x today. Batching is only ~1.1x faster per entry on
    # this brain (it loops server-side), so allow generous headroom — the
    # signal we want is "one batched round trip is not multiples worse than
    # doing them one at a time", not a tuned constant.
    serial_budget = serial_per_entry * N * 1.5
    assert elapsed < serial_budget, (
        f"save_many took {elapsed:.2f}s for {N} entries, over the "
        f"{serial_budget:.2f}s budget derived from {serial_per_entry:.3f}s "
        f"per serial save measured in the same run"
    )


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
    via the new bridge methods. Uses the ``full`` profile.

    Under tapps-brain v3.19.0+ the server uses deferred loading (Tool Search
    BETA). All three session tools are deferred — they will not appear in
    ``tools/list`` / ``exposed_tools`` but remain callable on the wire. We
    skip the profile-exposure assertions and rely on the method calls below
    to confirm the wire contract is satisfied.
    """
    import uuid

    skip_reason = _check_profile_loaded_lenient(brain_url, auth_token, project_id, "full")
    if skip_reason:
        pytest.skip(skip_reason)

    session_id = f"tap-1633-probe-{uuid.uuid4().hex[:8]}"
    bridge = _build_bridge(brain_url, auth_token, project_id, "full")
    try:
        # Drive negotiation so the bridge is initialized.
        # Session tools (memory_index_session / memory_search_sessions /
        # tapps_brain_session_end) are deferred under v3.19.0+ and absent from
        # exposed_tools — no profile-exposure assertion here.
        await bridge._http_mcp_call("brain_status", {})

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
