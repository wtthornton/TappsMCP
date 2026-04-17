"""Backward-compatible re-export."""

from __future__ import annotations

from tapps_core.knowledge.import_analyzer import (
    _detect_project_package as _detect_project_package,
)
from tapps_core.knowledge.import_analyzer import (
    extract_external_imports as extract_external_imports,
)
from tapps_core.knowledge.import_analyzer import (
    find_uncached_libraries as find_uncached_libraries,
)
