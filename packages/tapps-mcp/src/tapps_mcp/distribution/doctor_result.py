"""Doctor diagnostic check result (TAP-5606 split leaf).

:class:`CheckResult` has no dependencies on the rest of the doctor pipeline —
every ``doctor_*`` sibling module imports it from here.
"""

from __future__ import annotations

import sys
from typing import Any


def doctor_facade_attr(name: str, fallback: Any) -> Any:
    """Resolve *name* from the ``doctor`` facade when present (test monkeypatches).

    Siblings call this at runtime so ``patch("tapps_mcp.distribution.doctor.X")``
    still works after the TAP-5606 split without editing the mega test file.
    Falls back to the sibling's local binding when the facade is not loaded yet
    (import-time) or lacks the attribute.
    """
    doctor = sys.modules.get("tapps_mcp.distribution.doctor")
    if doctor is not None and hasattr(doctor, name):
        return getattr(doctor, name)
    return fallback


class CheckResult:
    """A single diagnostic check result.

    ``severity`` is ``pass``, ``warn``, or ``fail``. Advisory context-budget and
    tool-budget checks that prefix their message with ``WARN:`` are classified
    as ``warn`` automatically (ADR-0031 — non-blocking). ``ok`` is ``True`` only
    for ``pass``; warn and fail both have ``ok=False`` so existing callers that
    treat ``ok`` as "clean" keep working, while doctor tally/exit use severity.
    """

    __slots__ = ("detail", "message", "name", "ok", "severity")

    def __init__(
        self,
        name: str,
        ok: bool,
        message: str,
        detail: str = "",
        *,
        severity: str | None = None,
    ) -> None:
        self.name = name
        self.message = message
        self.detail = detail
        if severity is not None:
            if severity not in ("pass", "warn", "fail"):
                msg = f"invalid CheckResult severity: {severity!r}"
                raise ValueError(msg)
            self.severity = severity
            self.ok = severity == "pass"
        elif ok:
            self.severity = "pass"
            self.ok = True
        elif message.lstrip().startswith("WARN:"):
            self.severity = "warn"
            self.ok = False
        else:
            self.severity = "fail"
            self.ok = False
