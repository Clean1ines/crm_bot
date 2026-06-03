from __future__ import annotations

from collections.abc import Mapping


DELETED_STATUS = "deleted"


def is_deleted_workbench_document(row: Mapping[str, object]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status == DELETED_STATUS:
        return True
    return row.get("deleted_at") is not None


__all__ = ["DELETED_STATUS", "is_deleted_workbench_document"]
