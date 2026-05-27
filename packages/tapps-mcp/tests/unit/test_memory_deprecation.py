"""TAP-1994 (Phase 3): tapps_memory deprecation tests removed.

TAP-1991 (deprecation docstring) and TAP-1992 (telemetry) tests were
specific to the tapps_memory MCP tool.  TAP-1994 removed tapps_memory from
the MCP catalog entirely, so testing the tool's own deprecation notices no
longer makes sense.  The internal ``tapps_memory`` function still exists as
a lifecycle helper — its behaviour is covered by test_server_memory_tools.py.
"""
