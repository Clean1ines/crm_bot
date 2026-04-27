"""Shared utilities for the agent pipeline."""

from typing import SupportsInt


def coerce_int(value: object, default: int = 0) -> int:
    """
    Convert a value to int with a safe fallback.

    Args:
        value: object value that may represent an integer.
        default: Fallback value if conversion fails.

    Returns:
        Integer value or default.
    """
    if value is None:
        return default

    if not isinstance(value, str | bytes | bytearray | SupportsInt):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default
