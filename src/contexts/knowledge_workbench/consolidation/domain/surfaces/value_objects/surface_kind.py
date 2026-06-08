from __future__ import annotations

from enum import StrEnum


class SurfaceKind(StrEnum):
    OVERVIEW = "overview"
    DEFINITION = "definition"
    PROPERTY = "property"
    CAPABILITY = "capability"
    LIMITATION = "limitation"
    RULE = "rule"
    CONDITION = "condition"
    PROCESS = "process"
    LIST = "list"
    COMPARISON = "comparison"
    CRITERION = "criterion"
    EXAMPLE_SET = "example_set"
    VALUE = "value"
    EXCEPTION = "exception"
