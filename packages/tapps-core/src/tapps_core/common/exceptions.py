"""Exception hierarchy for the Tapps platform."""

from __future__ import annotations


class TappsMCPError(Exception):
    """Base exception for all TappsMCP errors."""


class ConfigurationError(TappsMCPError):
    """Raised when configuration is invalid or missing."""


class PathValidationError(TappsMCPError, ValueError):
    """Raised when path validation fails."""


class SecurityError(TappsMCPError):
    """Base exception for security-related errors."""


class FileOperationError(TappsMCPError):
    """Raised when file operations fail."""


class ToolExecutionError(TappsMCPError):
    """Raised when an external tool execution fails."""


class ToolNotFoundError(ToolExecutionError):
    """Raised when a required external tool is not installed."""


class QualityGateError(TappsMCPError):
    """Raised when quality gate evaluation fails."""
