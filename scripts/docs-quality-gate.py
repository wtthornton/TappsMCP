#!/usr/bin/env python3
"""CI docs quality gate — link, cross-ref, and completeness checks."""

from __future__ import annotations

import sys
from pathlib import Path

from docs_mcp.validators.completeness import CompletenessChecker
from docs_mcp.validators.cross_ref import CrossRefValidator
from docs_mcp.validators.link_checker import LinkChecker

MIN_COMPLETENESS = 96.0
MIN_CROSS_REF_SCORE = 80.0
ARCHIVE_GLOBS = ["docs/archive/**"]


def main() -> int:
    """Run link, cross-ref, and completeness checks; exit 1 on gate failure."""
    root = Path.cwd()
    failures: list[str] = []

    completeness = CompletenessChecker().check(
        root, exclude=ARCHIVE_GLOBS, respect_gitignore=True
    )
    score = completeness.overall_score
    if score <= 1.0:
        score *= 100
    print(f"completeness: {score:.1f}/100")
    if score < MIN_COMPLETENESS:
        failures.append(f"completeness {score:.1f} < {MIN_COMPLETENESS}")

    links = LinkChecker().check(
        root,
        broken_only=True,
        summary_only=True,
        include_backtick_refs=False,
        archive_paths=ARCHIVE_GLOBS,
    )
    broken = len(links.broken_links)
    print(f"broken_links: {broken} (score {links.score})")
    if broken > 0:
        failures.append(f"{broken} broken markdown links")

    cross = CrossRefValidator().validate(
        root,
        doc_dirs=["docs"],
        check_backlinks=False,
        archive_paths=ARCHIVE_GLOBS,
    )
    print(f"cross_refs: {cross.score:.0f}/100 (broken={cross.broken_count})")
    if cross.score < MIN_CROSS_REF_SCORE:
        failures.append(f"cross_ref score {cross.score:.0f} < {MIN_CROSS_REF_SCORE}")
    if cross.broken_count > 0:
        failures.append(f"{cross.broken_count} broken cross-references")

    if failures:
        print("docs-quality-gate: FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("docs-quality-gate: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
