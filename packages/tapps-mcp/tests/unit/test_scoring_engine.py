"""Coverage alias for scoring_engine.py — real tests in test_adaptive_scoring.py."""


def test_scoring_engine_importable() -> None:
    from tapps_mcp.adaptive import scoring_engine  # noqa: F401
