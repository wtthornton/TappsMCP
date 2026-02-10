"""Coverage alias for handoff.py — real tests in test_pipeline_handoff.py."""


def test_handoff_importable() -> None:
    from tapps_mcp.pipeline import handoff  # noqa: F401
