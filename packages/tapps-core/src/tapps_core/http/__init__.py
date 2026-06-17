"""HTTP transport helpers for shared MCP fleet (ADR-0024)."""

from tapps_core.http.middleware import wrap_streamable_http_app
from tapps_core.http.request_context import (
    PROJECT_ROOT_HEADER,
    get_request_project_root,
    reset_request_project_root,
    set_request_project_root,
)

__all__ = [
    "PROJECT_ROOT_HEADER",
    "get_request_project_root",
    "reset_request_project_root",
    "set_request_project_root",
    "wrap_streamable_http_app",
]
