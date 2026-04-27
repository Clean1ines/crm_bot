"""Shared utilities for the agent pipeline."""



def coerce_int(value: object, default: int = 0) -> int:
    """
    Convert a value to int with a safe fallback.

    Args:
        value: object value that may represent an integer.
        default: Fallback value if conversion fails.

    Returns:
        Integer value or default.
    """
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default
