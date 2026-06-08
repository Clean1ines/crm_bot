from __future__ import annotations

from enum import StrEnum


class ModelLifecycle(StrEnum):
    PRODUCTION = "production"
    PREVIEW = "preview"
    DEPRECATED = "deprecated"
