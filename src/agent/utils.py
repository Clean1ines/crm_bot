"""
Shared utilities and constants for the agent pipeline.
"""

from typing import Any, Dict, Optional

# Default dialog state to reset after ticket closure or first interaction
DEFAULT_DIALOG_STATE: Dict[str, Any] = {
    "last_intent": None,
    "last_cta": None,
    "last_topic": None,
    "repeat_count": 0,
    "lead_status": "active_client",
    "lifecycle": "active_client",
}


def coerce_int(value: Any, default: int = 0) -> int:
    """
    Convert a value to int with a safe fallback.

    Args:
        value: Any value that may represent an integer.
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
