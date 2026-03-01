"""Coverage alias for server.py — real tests in test_server_tools.py."""


def test_server_importable() -> None:
    from tapps_mcp import server  # noqa: F401
