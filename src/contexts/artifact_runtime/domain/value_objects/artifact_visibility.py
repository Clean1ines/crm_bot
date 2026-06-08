from __future__ import annotations

from enum import StrEnum


class ArtifactVisibility(StrEnum):
    """Generic visibility level for artifact consumers."""

    INTERNAL = "internal"
    REVIEWABLE = "reviewable"
    EXTERNAL = "external"
