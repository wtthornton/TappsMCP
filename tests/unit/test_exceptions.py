"""Tests for common.exceptions."""

from tapps_mcp.common.exceptions import (
    ConfigurationError,
    PathValidationError,
    SecurityError,
    TappsMCPError,
    ToolExecutionError,
    ToolNotFoundError,
)


class TestExceptionHierarchy:
    def test_base_exception(self):
        with_err = TappsMCPError("test")
        assert str(with_err) == "test"
        assert isinstance(with_err, Exception)

    def test_config_error_inherits(self):
        assert issubclass(ConfigurationError, TappsMCPError)

    def test_path_validation_is_value_error(self):
        err = PathValidationError("bad path")
        assert isinstance(err, ValueError)
        assert isinstance(err, TappsMCPError)

    def test_security_error(self):
        assert issubclass(SecurityError, TappsMCPError)

    def test_tool_not_found_inherits(self):
        assert issubclass(ToolNotFoundError, ToolExecutionError)
        assert issubclass(ToolNotFoundError, TappsMCPError)
