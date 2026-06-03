from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkbenchTargetRefKind(StrEnum):
    FACT_ID = "fact_id"
    CLAIM_LOCAL_REF = "claim_local_ref"
    CLAIM_TEXT = "claim_text"


@dataclass(frozen=True, slots=True)
class WorkbenchTargetRef:
    kind: WorkbenchTargetRefKind
    value: str


def fact_target_refs(
    *,
    fact_id: str | None = None,
    claim_local_ref: str | None = None,
    claim: str | None = None,
) -> tuple[WorkbenchTargetRef, ...]:
    refs: list[WorkbenchTargetRef] = []
    if fact_id:
        refs.append(WorkbenchTargetRef(WorkbenchTargetRefKind.FACT_ID, fact_id))
    if claim_local_ref:
        refs.append(WorkbenchTargetRef(WorkbenchTargetRefKind.CLAIM_LOCAL_REF, claim_local_ref))
    if claim:
        refs.append(WorkbenchTargetRef(WorkbenchTargetRefKind.CLAIM_TEXT, claim.strip()))
    return tuple(refs)


__all__ = ["WorkbenchTargetRef", "WorkbenchTargetRefKind", "fact_target_refs"]
