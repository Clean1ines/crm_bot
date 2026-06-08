from __future__ import annotations

from enum import StrEnum


class DraftClaimGranularity(StrEnum):
    ATOMIC = "atomic"
    COMPOSITE = "composite"
