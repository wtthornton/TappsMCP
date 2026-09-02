"""HTTP transport helpers for shared MCP fleet (ADR-0024)."""

from tapps_core.http.auth import (
    AUTHORIZATION_HEADER,
    FLEET_AUTH_ENV,
    FLEET_CREDENTIAL_HEADER,
    FLEET_RUNTIME_ENV,
    SCOPE_OPERATOR,
    SCOPE_RUNTIME,
    FleetAuthConfig,
    extract_presented_token,
)
from tapps_core.http.bind_policy import (
    NonLoopbackBindRefusedError,
    is_loopback_host,
    require_safe_bind,
    resolve_fleet_auth,
)
from tapps_core.http.middleware import (
    TappsFleetAuthMiddleware,
    TappsProjectRootMiddleware,
    wrap_streamable_http_app,
)
from tapps_core.http.request_context import (
    PROJECT_ROOT_HEADER,
    get_request_auth_scope,
    get_request_project_root,
    reset_request_auth_scope,
    reset_request_project_root,
    set_request_auth_scope,
    set_request_project_root,
)

__all__ = [
    "AUTHORIZATION_HEADER",
    "FLEET_AUTH_ENV",
    "FLEET_CREDENTIAL_HEADER",
    "FLEET_RUNTIME_ENV",
    "PROJECT_ROOT_HEADER",
    "SCOPE_OPERATOR",
    "SCOPE_RUNTIME",
    "FleetAuthConfig",
    "NonLoopbackBindRefusedError",
    "TappsFleetAuthMiddleware",
    "TappsProjectRootMiddleware",
    "extract_presented_token",
    "get_request_auth_scope",
    "get_request_project_root",
    "is_loopback_host",
    "require_safe_bind",
    "reset_request_auth_scope",
    "reset_request_project_root",
    "resolve_fleet_auth",
    "set_request_auth_scope",
    "set_request_project_root",
    "wrap_streamable_http_app",
]
