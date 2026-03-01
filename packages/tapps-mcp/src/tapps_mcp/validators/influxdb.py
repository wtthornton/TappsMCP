"""InfluxDB validator — Flux query, connection, and data modelling checks."""

from __future__ import annotations

import re

from tapps_core.knowledge.models import ConfigValidationResult, ValidationFinding

# Detection
_INFLUX_PATTERN = re.compile(r"InfluxDBClient|influxdb|from\(bucket:", re.IGNORECASE)

# Flux query patterns
_FROM_BUCKET = re.compile(r"from\(bucket:", re.IGNORECASE)
_RANGE = re.compile(r"range\(start:", re.IGNORECASE)
_FILTER = re.compile(r"filter\(fn:", re.IGNORECASE)
_AGGREGATE = re.compile(r"aggregateWindow", re.IGNORECASE)
_CREATE_EMPTY = re.compile(r"createEmpty:\s*false", re.IGNORECASE)
_LIMIT = re.compile(r"\|>\s*limit\(", re.IGNORECASE)

# Connection patterns
_CONTEXT_MANAGER = re.compile(r"with\s+InfluxDBClient|async\s+with", re.IGNORECASE)
_ERROR_HANDLING = re.compile(r"except\s+|\.catch\(|try\s*\{", re.IGNORECASE)
_RETRY = re.compile(r"retry|backoff|retries", re.IGNORECASE)

# Data modelling
_POINT = re.compile(r"Point\(", re.IGNORECASE)
_TIMESTAMP_TAG = re.compile(r"\.tag\([^)]*(?:time|timestamp|date)", re.IGNORECASE)
_WRITE_API = re.compile(r"write_api|write\(", re.IGNORECASE)
_MAX_WRITE_CALLS = 5


def validate_influxdb(file_path: str, content: str) -> ConfigValidationResult:
    """Validate InfluxDB patterns in source code."""
    findings: list[ValidationFinding] = []
    suggestions: list[str] = []

    if not _INFLUX_PATTERN.search(content):
        return ConfigValidationResult(
            file_path=file_path,
            config_type="influxdb",
            valid=True,
            findings=[],
            suggestions=["No InfluxDB patterns detected in this file."],
        )

    # --- Flux query validation ---
    has_flux = _FROM_BUCKET.search(content)
    if has_flux:
        # Range after from
        if not _RANGE.search(content):
            findings.append(
                ValidationFinding(
                    severity="warning",
                    message="Flux: add range() after from() to bound queries.",
                    category="flux_query",
                )
            )

        # aggregateWindow without createEmpty
        if _AGGREGATE.search(content) and not _CREATE_EMPTY.search(content):
            suggestions.append("Add 'createEmpty: false' to aggregateWindow to avoid null fill.")

        # Missing limit
        if not _LIMIT.search(content):
            suggestions.append("Add limit() to Flux queries to cap result size.")

        # Filter order: should come after range
        range_match = _RANGE.search(content)
        filter_match = _FILTER.search(content)
        if range_match and filter_match and filter_match.start() < range_match.start():
            findings.append(
                ValidationFinding(
                    severity="info",
                    message="Place range() before filter() for efficient query execution.",
                    category="flux_query",
                )
            )

    # --- Connection patterns ---
    if not _CONTEXT_MANAGER.search(content):
        findings.append(
            ValidationFinding(
                severity="warning",
                message="Use context manager (with) for InfluxDB connections.",
                category="connection",
            )
        )

    if not _ERROR_HANDLING.search(content):
        findings.append(
            ValidationFinding(
                severity="warning",
                message="Add error handling for InfluxDB operations.",
                category="reliability",
            )
        )

    if not _RETRY.search(content):
        suggestions.append("Add retry logic for InfluxDB connection failures.")

    # --- Data modelling ---
    if _POINT.search(content) and _TIMESTAMP_TAG.search(content):
        findings.append(
            ValidationFinding(
                severity="warning",
                message="Timestamps in tags cause high cardinality. Use time field instead.",
                category="data_model",
            )
        )

    # Multiple write calls suggest batching
    write_count = len(_WRITE_API.findall(content))
    if write_count > _MAX_WRITE_CALLS:
        suggestions.append(f"Found {write_count} write calls. Use batch writes for efficiency.")

    return ConfigValidationResult(
        file_path=file_path,
        config_type="influxdb",
        valid=True,
        findings=findings,
        suggestions=suggestions,
    )
