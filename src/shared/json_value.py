from __future__ import annotations

JsonInputValue = (
    str
    | int
    | float
    | bool
    | None
    | list["JsonInputValue"]
    | tuple["JsonInputValue", ...]
    | dict[str, "JsonInputValue"]
)
