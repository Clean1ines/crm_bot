"""
UUID utility functions for safe conversion between string and UUID objects.
"""

import uuid


def ensure_uuid(value: str | uuid.UUID) -> uuid.UUID:
    """
    Convert a string or UUID object to a UUID object.
    If the input is already a UUID, return it unchanged.
    Raises ValueError if the string is not a valid UUID.
    """
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(value)
