"""Doctor diagnostic check result (TAP-5606 split leaf).

:class:`CheckResult` has no dependencies on the rest of the doctor pipeline —
every ``doctor_*`` sibling module imports it from here.
"""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from typing import Any, ParamSpec

_P = ParamSpec("_P")


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


_CATEGORIES = ("release-health", "consumer-staleness")


class CheckResult:
    """A single diagnostic check result.

    ``severity`` is ``pass``, ``warn``, or ``fail``. Advisory context-budget and
    tool-budget checks that prefix their message with ``WARN:`` are classified
    as ``warn`` automatically (ADR-0031 — non-blocking). ``ok`` is ``True`` only
    for ``pass``; warn and fail both have ``ok=False`` so existing callers that
    treat ``ok`` as "clean" keep working, while doctor tally/exit use severity.

    ``category`` distinguishes findings about the *release itself* being
    unhealthy (``"release-health"``, the default) from findings that are only
    about a *consumer worktree* being stale (``"consumer-staleness"`` — missing
    ``.mcp.json``, scaffold/skip-token drift, skill currency). Post-flip smoke
    testing (TAP-6965, ``blue_green.smoke_test_release``) gates a deploy on
    every ``release-health`` failure and only reports ``consumer-staleness``
    ones. The default is ``"release-health"`` deliberately: an unrecognized or
    newly added check — including one that crashed (see ``doctor_runner._safe_check``,
    which never carries a category forward) — must gate rather than be
    silently treated as non-blocking staleness.
    """

    __slots__ = ("category", "detail", "message", "name", "ok", "severity")

    def __init__(
        self,
        name: str,
        ok: bool,
        message: str,
        detail: str = "",
        *,
        severity: str | None = None,
        category: str = "release-health",
    ) -> None:
        self.name = name
        self.message = message
        self.detail = detail
        if category not in _CATEGORIES:
            msg = f"invalid CheckResult category: {category!r}"
            raise ValueError(msg)
        self.category = category
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


_CONSUMER_STALENESS_MARKER = "__tapps_category__"


def consumer_staleness(fn: Callable[_P, CheckResult]) -> Callable[_P, CheckResult]:
    """Mark every ``CheckResult`` a doctor check produces as ``consumer-staleness``.

    Decorate a ``check_*`` function that genuinely measures the *consumer
    worktree's* freshness (a scaffolding file, a config entry, a skill's
    currency) rather than the release binary's health. Applied once at the
    function definition so the category lives with the check that knows what
    it measures, instead of being restated as a name list downstream.

    Also stamps the wrapper with ``__tapps_category__`` so a test can walk the
    doctor's check registry and derive which checks are expected to produce
    ``consumer-staleness`` rows directly from the decorator, rather than from
    a second, independently-maintained name list (see
    ``test_blue_green_post_flip_smoke.py``'s derived-guard test).
    """

    @functools.wraps(fn)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> CheckResult:
        result = fn(*args, **kwargs)
        result.category = "consumer-staleness"
        return result

    setattr(wrapper, _CONSUMER_STALENESS_MARKER, "consumer-staleness")
    return wrapper
