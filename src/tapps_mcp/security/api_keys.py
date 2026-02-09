"""Secure API key handling.

Wraps API keys in ``pydantic.SecretStr`` so they never leak into logs,
error messages, or tool responses.
"""

from __future__ import annotations

import os

from pydantic import SecretStr


def load_api_key_from_env(env_var: str) -> SecretStr | None:
    """Load an API key from an environment variable as ``SecretStr``.

    Args:
        env_var: Name of the environment variable.

    Returns:
        ``SecretStr`` wrapping the value, or ``None`` if not set.
    """
    value = os.environ.get(env_var)
    if value:
        return SecretStr(value)
    return None
