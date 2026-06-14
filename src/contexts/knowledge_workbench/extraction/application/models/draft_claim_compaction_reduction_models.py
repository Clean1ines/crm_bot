from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionTriple,
)


PRIMARY_DRAFT_CLAIM_COMPACTION_MODEL_ID = "openai/gpt-oss-120b"
DEGRADED_DRAFT_CLAIM_COMPACTION_MODEL_ID = "llama-3.3-70b-versatile"


class DraftClaimCompactionNodeKind(StrEnum):
    RAW = "raw"
    COMPACTED = "compacted"


class DraftClaimCompactionComparisonStatus(StrEnum):
    PENDING = "pending"
    MERGED = "merged"
    NOT_MERGED = "not_merged"
    TOO_LARGE_FOR_PRIMARY_MODEL = "too_large_for_primary_model"
    WAITING_USER_MODEL_CHOICE = "waiting_user_model_choice"
    SUPERSEDED = "superseded"


class DraftClaimCompactionNextWorkItemType(StrEnum):
    DRAFT_VS_DRAFT = "draft_vs_draft"
    COMPACTED_VS_COMPACTED = "compacted_vs_compacted"
    MIXED = "mixed"
    REDUCED_REWRITE = "reduced_rewrite"
    WAIT_FOR_USER_MODEL_CHOICE = "wait_for_user_model_choice"
    DONE = "done"


class DraftClaimCompactionBudgetFitStatus(StrEnum):
    FITS_PRIMARY = "fits_primary"
    TOO_LARGE_FOR_PRIMARY = "too_large_for_primary"
    TOO_LARGE_EVEN_REDUCED = "too_large_even_reduced"


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionBudgetFit:
    status: DraftClaimCompactionBudgetFitStatus
    estimated_input_tokens: int = 0
    primary_model_id: str = PRIMARY_DRAFT_CLAIM_COMPACTION_MODEL_ID
    degraded_candidate_model_id: str = DEGRADED_DRAFT_CLAIM_COMPACTION_MODEL_ID

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", _budget_fit_status(self.status))
        if self.estimated_input_tokens < 0:
            raise ValueError("estimated_input_tokens must be >= 0")
        _text(self.primary_model_id, "primary_model_id")
        _text(self.degraded_candidate_model_id, "degraded_candidate_model_id")


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionNodeSource:
    source_ref: str
    source_kind: DraftClaimCompactionNodeKind

    def __post_init__(self) -> None:
        _text(self.source_ref, "source_ref")
        object.__setattr__(self, "source_kind", _node_kind(self.source_kind))


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionNode:
    node_ref: str
    node_kind: DraftClaimCompactionNodeKind
    source_claim_refs: tuple[str, ...]
    sources: tuple[DraftClaimCompactionNodeSource, ...] = ()
    active: bool = True
    supersedes_node_refs: tuple[str, ...] = ()
    estimated_input_tokens: int = 1
    compacted_key: str | None = None
    compacted_claim: str | None = None
    compacted_triples: tuple[DraftClaimCompactionTriple, ...] = ()

    def __post_init__(self) -> None:
        _text(self.node_ref, "node_ref")
        object.__setattr__(self, "node_kind", _node_kind(self.node_kind))
        _text_tuple(self.source_claim_refs, "source_claim_refs", allow_empty=False)
        _sources_tuple(self.sources)
        if not isinstance(self.active, bool):
            raise TypeError("active must be bool")
        _text_tuple(
            self.supersedes_node_refs,
            "supersedes_node_refs",
            allow_empty=True,
        )
        if self.estimated_input_tokens < 0:
            raise ValueError("estimated_input_tokens must be >= 0")
        if self.compacted_key is not None:
            _text(self.compacted_key, "compacted_key")
        if self.compacted_claim is not None:
            _text(self.compacted_claim, "compacted_claim")
        _triples_tuple(self.compacted_triples)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionComparison:
    left_node_ref: str
    right_node_ref: str
    status: DraftClaimCompactionComparisonStatus
    result_node_ref: str | None = None

    def __post_init__(self) -> None:
        _text(self.left_node_ref, "left_node_ref")
        _text(self.right_node_ref, "right_node_ref")
        if self.left_node_ref == self.right_node_ref:
            raise ValueError("comparison node refs must be different")
        object.__setattr__(self, "status", _comparison_status(self.status))
        if self.result_node_ref is not None:
            _text(self.result_node_ref, "result_node_ref")

    @property
    def pair_key(self) -> tuple[str, str]:
        left, right = sorted((self.left_node_ref, self.right_node_ref))
        return left, right

    def contains(self, node_ref: str) -> bool:
        return node_ref in {self.left_node_ref, self.right_node_ref}

    def other_node_ref(self, node_ref: str) -> str:
        if node_ref == self.left_node_ref:
            return self.right_node_ref
        if node_ref == self.right_node_ref:
            return self.left_node_ref
        raise ValueError("node_ref is not part of comparison")


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionRound:
    round_index: int
    comparisons: tuple[DraftClaimCompactionComparison, ...]

    def __post_init__(self) -> None:
        if self.round_index < 0:
            raise ValueError("round_index must be >= 0")
        _comparisons_tuple(self.comparisons)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionPlannerState:
    cluster_ref: str
    nodes: tuple[DraftClaimCompactionNode, ...]
    comparisons: tuple[DraftClaimCompactionComparison, ...] = ()
    rounds: tuple[DraftClaimCompactionRound, ...] = ()
    budget_fit: DraftClaimCompactionBudgetFit = field(
        default_factory=lambda: DraftClaimCompactionBudgetFit(
            DraftClaimCompactionBudgetFitStatus.FITS_PRIMARY,
        ),
    )
    primary_model_id: str = PRIMARY_DRAFT_CLAIM_COMPACTION_MODEL_ID
    degraded_candidate_model_id: str = DEGRADED_DRAFT_CLAIM_COMPACTION_MODEL_ID

    def __post_init__(self) -> None:
        _text(self.cluster_ref, "cluster_ref")
        _nodes_tuple(self.nodes)
        _comparisons_tuple(self.comparisons)
        _rounds_tuple(self.rounds)
        if not isinstance(self.budget_fit, DraftClaimCompactionBudgetFit):
            raise TypeError("budget_fit must be DraftClaimCompactionBudgetFit")
        _text(self.primary_model_id, "primary_model_id")
        _text(self.degraded_candidate_model_id, "degraded_candidate_model_id")
        refs = tuple(node.node_ref for node in self.nodes)
        if len(set(refs)) != len(refs):
            raise ValueError("node_ref values must be unique")

    def active_nodes(self) -> tuple[DraftClaimCompactionNode, ...]:
        return tuple(node for node in self.nodes if node.active)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionNextWorkItem:
    work_type: DraftClaimCompactionNextWorkItemType
    node_refs: tuple[str, ...]
    primary_model_id: str = PRIMARY_DRAFT_CLAIM_COMPACTION_MODEL_ID
    degraded_model_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "work_type", _next_work_item_type(self.work_type))
        _text_tuple(self.node_refs, "node_refs", allow_empty=True)
        _text(self.primary_model_id, "primary_model_id")
        if self.degraded_model_id is not None:
            _text(self.degraded_model_id, "degraded_model_id")


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionPlannerDecision:
    next_work_item: DraftClaimCompactionNextWorkItem
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.next_work_item, DraftClaimCompactionNextWorkItem):
            raise TypeError("next_work_item must be DraftClaimCompactionNextWorkItem")
        _text(self.reason, "reason")

    @property
    def work_type(self) -> DraftClaimCompactionNextWorkItemType:
        return self.next_work_item.work_type

    @property
    def node_refs(self) -> tuple[str, ...]:
        return self.next_work_item.node_refs


def _node_kind(
    value: DraftClaimCompactionNodeKind | str,
) -> DraftClaimCompactionNodeKind:
    try:
        return DraftClaimCompactionNodeKind(value)
    except ValueError as exc:
        raise ValueError("node_kind must be raw or compacted") from exc


def _comparison_status(
    value: DraftClaimCompactionComparisonStatus | str,
) -> DraftClaimCompactionComparisonStatus:
    try:
        return DraftClaimCompactionComparisonStatus(value)
    except ValueError as exc:
        raise ValueError("comparison status is not allowed") from exc


def _next_work_item_type(
    value: DraftClaimCompactionNextWorkItemType | str,
) -> DraftClaimCompactionNextWorkItemType:
    try:
        return DraftClaimCompactionNextWorkItemType(value)
    except ValueError as exc:
        raise ValueError("next work item type is not allowed") from exc


def _budget_fit_status(
    value: DraftClaimCompactionBudgetFitStatus | str,
) -> DraftClaimCompactionBudgetFitStatus:
    try:
        return DraftClaimCompactionBudgetFitStatus(value)
    except ValueError as exc:
        raise ValueError("budget fit status is not allowed") from exc


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")


def _text_tuple(value: tuple[str, ...], name: str, *, allow_empty: bool) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be tuple")
    if not value and not allow_empty:
        raise ValueError(f"{name} must be non-empty")
    for item in value:
        _text(item, name)


def _triples_tuple(
    value: tuple[DraftClaimCompactionTriple, ...],
) -> None:
    if not isinstance(value, tuple):
        raise TypeError("compacted_triples must be tuple")
    for triple in value:
        if not isinstance(triple, DraftClaimCompactionTriple):
            raise TypeError(
                "compacted_triples must contain DraftClaimCompactionTriple",
            )


def _sources_tuple(value: tuple[DraftClaimCompactionNodeSource, ...]) -> None:
    if not isinstance(value, tuple):
        raise TypeError("sources must be tuple")
    for source in value:
        if not isinstance(source, DraftClaimCompactionNodeSource):
            raise TypeError("sources must contain DraftClaimCompactionNodeSource")


def _nodes_tuple(value: tuple[DraftClaimCompactionNode, ...]) -> None:
    if not isinstance(value, tuple):
        raise TypeError("nodes must be tuple")
    for node in value:
        if not isinstance(node, DraftClaimCompactionNode):
            raise TypeError("nodes must contain DraftClaimCompactionNode")


def _comparisons_tuple(value: tuple[DraftClaimCompactionComparison, ...]) -> None:
    if not isinstance(value, tuple):
        raise TypeError("comparisons must be tuple")
    for comparison in value:
        if not isinstance(comparison, DraftClaimCompactionComparison):
            raise TypeError("comparisons must contain DraftClaimCompactionComparison")


def _rounds_tuple(value: tuple[DraftClaimCompactionRound, ...]) -> None:
    if not isinstance(value, tuple):
        raise TypeError("rounds must be tuple")
    for round_item in value:
        if not isinstance(round_item, DraftClaimCompactionRound):
            raise TypeError("rounds must contain DraftClaimCompactionRound")
