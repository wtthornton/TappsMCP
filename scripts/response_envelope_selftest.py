"""Self-test fixtures for the response-envelope lint (TAP-5660).

Kept beside the analyser rather than inside it: these are ~90 lines of sample
source that exist only to prove the lint still catches the two shapes that
escaped, and CI runs them via ``check-response-envelope.py --test`` where
pytest is not available. ``test_response_envelope_lint.py`` covers the same
ground from the suite.
"""

from __future__ import annotations

from response_envelope_lint import check_source

_BAD = """
from dataclasses import dataclass
from typing import Any

@dataclass
class R:
    brain_mirror: dict[str, Any] | None = None

def tool(result: R):
    data = {"brain_mirror": result.brain_mirror}
    return success_response("tool", 1, data)
"""

_GOOD_BRANCHED = """
from dataclasses import dataclass
from typing import Any

@dataclass
class R:
    brain_mirror: dict[str, Any] | None = None

def tool(result: R):
    data = {"brain_mirror": result.brain_mirror}
    if result.brain_mirror and not result.brain_mirror.get("success"):
        return success_response("tool", 1, data, degraded=True)
    return success_response("tool", 1, data)
"""

_GOOD_DEGRADED = """
from dataclasses import dataclass
from typing import Any

@dataclass
class R:
    session_end: dict[str, Any] | None = None

def tool(result: R):
    data = {"session_end": result.session_end}
    return success_response("tool", 1, data, degraded=True)
"""

_GOOD_ALLOWLISTED = """
from dataclasses import dataclass
from typing import Any

@dataclass
class R:
    telemetry: dict[str, Any] | None = None

def tool(result: R):
    data = {"telemetry": result.telemetry}  # envelope-ok: advisory counters only
    return success_response("tool", 1, data)
"""

_BAD_BARE_MARKER = """
from dataclasses import dataclass
from typing import Any

@dataclass
class R:
    telemetry: dict[str, Any] | None = None

def tool(result: R):
    data = {"telemetry": result.telemetry}  # envelope-ok:
    return success_response("tool", 1, data)
"""


def self_test() -> int:
    cases: list[tuple[str, str, int]] = [
        ("unchecked sub-result", _BAD, 1),
        ("branched on failure", _GOOD_BRANCHED, 0),
        ("explicitly degraded", _GOOD_DEGRADED, 0),
        ("allowlisted with reason", _GOOD_ALLOWLISTED, 0),
        ("allowlisted without reason", _BAD_BARE_MARKER, 1),
    ]
    failures = 0
    for label, source, expected in cases:
        actual = len(check_source(source, f"<{label}>"))
        status = "ok  " if actual == expected else "FAIL"
        if actual != expected:
            failures += 1
        print(f"  [{status}] {label}: expected {expected} finding(s), got {actual}")
    if failures:
        print(f"\nself-test FAILED ({failures} case(s))")
        return 1
    print(f"\nself-test passed ({len(cases)} cases)")
    return 0
