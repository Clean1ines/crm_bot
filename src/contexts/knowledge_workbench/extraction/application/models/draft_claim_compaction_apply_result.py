from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionOutputClaim,
    DraftClaimReducedRewriteOutput,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionPlannerDecision,
)


class DraftClaimCompactionApplyOutputKind(StrEnum):
    COMPACTED_CLAIMS = "compacted_claims"
    REDUCED_REWRITE = "reduced_rewrite"


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionAppliedNode:
    node_ref: str
    source_claim_refs: tuple[str, ...]
    supersedes_node_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.node_ref, "node_ref")
        _text_tuple(self.source_claim_refs, "source_claim_refs", allow_empty=False)
        _text_tuple(
            self.supersedes_node_refs,
            "supersedes_node_refs",
            allow_empty=True,
        )


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionApplyResultCommand:
    workflow_run_id: str
    group_ref: str
    batch_ref: str
    work_item_id: str
    round_index: int
    compared_node_refs: tuple[str, ...]
    output_kind: DraftClaimCompactionApplyOutputKind
    compacted_claims: tuple[DraftClaimCompactionOutputClaim, ...]
    reduced_rewrite: DraftClaimReducedRewriteOutput | None
    created_at: datetime

    def __post_init__(self) -> None:
        _text(self.workflow_run_id, "workflow_run_id")
        _text(self.group_ref, "group_ref")
        _text(self.batch_ref, "batch_ref")
        _text(self.work_item_id, "work_item_id")
        if self.round_index < 0:
            raise ValueError("round_index must be >= 0")
        _text_tuple(
            self.compared_node_refs,
            "compared_node_refs",
            allow_empty=False,
        )
        object.__setattr__(
            self,
            "output_kind",
            DraftClaimCompactionApplyOutputKind(self.output_kind),
        )
        if not isinstance(self.compacted_claims, tuple):
            raise TypeError("compacted_claims must be tuple")
        for claim in self.compacted_claims:
            if not isinstance(claim, DraftClaimCompactionOutputClaim):
                raise TypeError(
                    "compacted_claims must contain DraftClaimCompactionOutputClaim",
                )
        if self.reduced_rewrite is not None and not isinstance(
            self.reduced_rewrite,
            DraftClaimReducedRewriteOutput,
        ):
            raise TypeError("reduced_rewrite must be DraftClaimReducedRewriteOutput")

        if self.output_kind is DraftClaimCompactionApplyOutputKind.COMPACTED_CLAIMS:
            if not self.compacted_claims:
                raise ValueError("compacted_claims output must be non-empty")
            if self.reduced_rewrite is not None:
                raise ValueError("compacted_claims output cannot include rewrite")
        if self.output_kind is DraftClaimCompactionApplyOutputKind.REDUCED_REWRITE:
            if len(self.compared_node_refs) != 2:
                raise ValueError(
                    "reduced_rewrite output requires exactly two compared_node_refs"
                )
            if self.reduced_rewrite is None:
                raise ValueError("reduced_rewrite output requires rewrite")
            if self.compacted_claims:
                raise ValueError("reduced_rewrite output cannot include claims")


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionApplyResultOutcome:
    created_node_refs: tuple[str, ...]
    superseded_node_refs: tuple[str, ...]
    comparison_refs: tuple[str, ...]
    next_decision: DraftClaimCompactionPlannerDecision

    def __post_init__(self) -> None:
        _text_tuple(self.created_node_refs, "created_node_refs", allow_empty=True)
        _text_tuple(
            self.superseded_node_refs,
            "superseded_node_refs",
            allow_empty=True,
        )
        _text_tuple(self.comparison_refs, "comparison_refs", allow_empty=True)
        if not isinstance(self.next_decision, DraftClaimCompactionPlannerDecision):
            raise TypeError("next_decision must be DraftClaimCompactionPlannerDecision")


def raw_claim_node_ref(
    *,
    workflow_run_id: str,
    group_ref: str,
    observation_ref: str,
) -> str:
    _text(workflow_run_id, "workflow_run_id")
    _text(group_ref, "group_ref")
    _text(observation_ref, "observation_ref")
    return f"raw:{workflow_run_id}:{group_ref}:{observation_ref}"


def compacted_claim_node_ref(
    *,
    workflow_run_id: str,
    group_ref: str,
    source_claim_refs: Iterable[str],
) -> str:
    refs = tuple(sorted(_dedupe_texts(tuple(source_claim_refs))))
    _text(workflow_run_id, "workflow_run_id")
    _text(group_ref, "group_ref")
    _text_tuple(refs, "source_claim_refs", allow_empty=False)
    digest = sha256(
        (workflow_run_id + ":" + group_ref + ":" + ":".join(refs)).encode("utf-8"),
    ).hexdigest()
    return f"compacted:{workflow_run_id}:{group_ref}:{digest}"


def comparison_ref(
    *,
    workflow_run_id: str,
    group_ref: str,
    round_index: int,
    left_node_ref: str,
    right_node_ref: str,
) -> str:
    left, right = ordered_pair(left_node_ref, right_node_ref)
    if round_index < 0:
        raise ValueError("round_index must be >= 0")
    return f"comparison:{workflow_run_id}:{group_ref}:{round_index}:{left}:{right}"


def ordered_pair(left_node_ref: str, right_node_ref: str) -> tuple[str, str]:
    _text(left_node_ref, "left_node_ref")
    _text(right_node_ref, "right_node_ref")
    if left_node_ref == right_node_ref:
        raise ValueError("comparison node refs must be different")
    left, right = sorted((left_node_ref, right_node_ref))
    return left, right


def _dedupe_texts(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        _text(value, "value")
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")


def _text_tuple(value: tuple[str, ...], field_name: str, *, allow_empty: bool) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    if not value and not allow_empty:
        raise ValueError(f"{field_name} must be non-empty")
    for item in value:
        _text(item, field_name)
