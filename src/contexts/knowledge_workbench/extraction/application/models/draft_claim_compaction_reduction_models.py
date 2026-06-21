from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionTriple,
)
from src.domain.project_plane.json_types import JsonObject, JsonValue


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
    compacted_claim_kind: str | None = None
    compacted_granularity: str | None = None
    compacted_merge_decision: str | None = None
    compacted_payload: JsonObject | None = None

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
        if self.compacted_claim_kind is not None:
            _text(self.compacted_claim_kind, "compacted_claim_kind")
        if self.compacted_granularity is not None:
            _text(self.compacted_granularity, "compacted_granularity")
        if self.compacted_merge_decision is not None:
            _text(self.compacted_merge_decision, "compacted_merge_decision")
        if self.compacted_payload is not None:
            _json_object(self.compacted_payload, "compacted_payload")


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionNodeReadModel:
    workflow_run_id: str
    group_ref: str
    node_ref: str
    node_kind: str
    active: bool
    source_claim_refs: tuple[str, ...]
    supersedes_node_refs: tuple[str, ...]
    estimated_input_tokens: int
    compacted_key: str | None
    compacted_claim: str | None
    compacted_claim_kind: str | None
    compacted_granularity: str | None
    compacted_merge_decision: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        for name, value in (
            ("workflow_run_id", self.workflow_run_id),
            ("group_ref", self.group_ref),
            ("node_ref", self.node_ref),
            ("node_kind", self.node_kind),
        ):
            _text(value, name)
        if self.node_kind not in {item.value for item in DraftClaimCompactionNodeKind}:
            raise ValueError("node_kind must be raw or compacted")
        if not isinstance(self.active, bool):
            raise TypeError("active must be bool")
        _text_tuple(self.source_claim_refs, "source_claim_refs", allow_empty=False)
        _text_tuple(self.supersedes_node_refs, "supersedes_node_refs", allow_empty=True)
        _non_negative_int(self.estimated_input_tokens, "estimated_input_tokens")
        if self.compacted_key is not None:
            _text(self.compacted_key, "compacted_key")
        if self.compacted_claim is not None:
            _text(self.compacted_claim, "compacted_claim")
        if self.compacted_claim_kind is not None:
            _text(self.compacted_claim_kind, "compacted_claim_kind")
        if self.compacted_granularity is not None:
            _text(self.compacted_granularity, "compacted_granularity")
        if self.compacted_merge_decision is not None:
            _text(self.compacted_merge_decision, "compacted_merge_decision")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be datetime")
        if not isinstance(self.updated_at, datetime):
            raise TypeError("updated_at must be datetime")


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
class DraftClaimCompactionComponent:
    component_ref: str
    representative_node_ref: str
    source_claim_refs: tuple[str, ...]
    active: bool = True
    supersedes_component_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.component_ref, "component_ref")
        _text(self.representative_node_ref, "representative_node_ref")
        _text_tuple(self.source_claim_refs, "source_claim_refs", allow_empty=False)
        if not isinstance(self.active, bool):
            raise TypeError("active must be bool")
        _text_tuple(
            self.supersedes_component_refs,
            "supersedes_component_refs",
            allow_empty=True,
        )


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionComponentIncompatibility:
    left_component_ref: str
    right_component_ref: str

    def __post_init__(self) -> None:
        _text(self.left_component_ref, "left_component_ref")
        _text(self.right_component_ref, "right_component_ref")
        if self.left_component_ref == self.right_component_ref:
            raise ValueError("incompatibility component refs must be different")

    @property
    def pair_key(self) -> tuple[str, str]:
        left, right = sorted((self.left_component_ref, self.right_component_ref))
        return left, right


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
    components: tuple[DraftClaimCompactionComponent, ...] = ()
    incompatibilities: tuple[DraftClaimCompactionComponentIncompatibility, ...] = ()
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
        _components_tuple(self.components)
        _incompatibilities_tuple(self.incompatibilities)
        if not isinstance(self.budget_fit, DraftClaimCompactionBudgetFit):
            raise TypeError("budget_fit must be DraftClaimCompactionBudgetFit")
        _text(self.primary_model_id, "primary_model_id")
        _text(self.degraded_candidate_model_id, "degraded_candidate_model_id")
        refs = tuple(node.node_ref for node in self.nodes)
        if len(set(refs)) != len(refs):
            raise ValueError("node_ref values must be unique")

    def active_nodes(self) -> tuple[DraftClaimCompactionNode, ...]:
        return tuple(node for node in self.nodes if node.active)

    def active_components(self) -> tuple[DraftClaimCompactionComponent, ...]:
        return tuple(component for component in self.components if component.active)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionNextWorkItem:
    work_type: DraftClaimCompactionNextWorkItemType
    node_refs: tuple[str, ...]
    primary_model_id: str = PRIMARY_DRAFT_CLAIM_COMPACTION_MODEL_ID
    degraded_model_id: str | None = None
    user_choice_resume_work_type: DraftClaimCompactionNextWorkItemType | None = None
    estimated_prompt_tokens: int = 0
    estimated_completion_tokens: int = 4000
    estimated_requests: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "work_type", _next_work_item_type(self.work_type))
        _text_tuple(self.node_refs, "node_refs", allow_empty=True)
        _text(self.primary_model_id, "primary_model_id")
        if self.degraded_model_id is not None:
            _text(self.degraded_model_id, "degraded_model_id")
        if self.user_choice_resume_work_type is not None:
            object.__setattr__(
                self,
                "user_choice_resume_work_type",
                _next_work_item_type(self.user_choice_resume_work_type),
            )
            if self.work_type is not (
                DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE
            ):
                raise ValueError(
                    "user_choice_resume_work_type requires wait_for_user_model_choice"
                )
            if self.user_choice_resume_work_type in {
                DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE,
                DraftClaimCompactionNextWorkItemType.DONE,
            }:
                raise ValueError("user choice resume work type must be executable")
        _non_negative_int(
            self.estimated_prompt_tokens,
            "estimated_prompt_tokens",
        )
        _non_negative_int(
            self.estimated_completion_tokens,
            "estimated_completion_tokens",
        )
        _positive_int(self.estimated_requests, "estimated_requests")


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


def _non_negative_int(value: int, name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{name} must be int")
    if value < 0:
        raise ValueError(f"{name} must be >= 0")


def _positive_int(value: int, name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{name} must be int")
    if value <= 0:
        raise ValueError(f"{name} must be > 0")


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


def _json_object(value: JsonObject, name: str) -> None:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be json object")
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{name} keys must be str")
        _json_value(item, name)


def _json_value(value: JsonValue, name: str) -> None:
    if value is None or isinstance(value, str | int | float | bool):
        return
    if isinstance(value, list):
        for item in value:
            _json_value(item, name)
        return
    if isinstance(value, dict):
        _json_object(value, name)
        return
    raise TypeError(f"{name} must be JSON-compatible")


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


def _components_tuple(value: tuple[DraftClaimCompactionComponent, ...]) -> None:
    if not isinstance(value, tuple):
        raise TypeError("components must be tuple")
    for component in value:
        if not isinstance(component, DraftClaimCompactionComponent):
            raise TypeError("components must contain DraftClaimCompactionComponent")


def _incompatibilities_tuple(
    value: tuple[DraftClaimCompactionComponentIncompatibility, ...],
) -> None:
    if not isinstance(value, tuple):
        raise TypeError("incompatibilities must be tuple")
    for incompatibility in value:
        if not isinstance(
            incompatibility, DraftClaimCompactionComponentIncompatibility
        ):
            raise TypeError(
                "incompatibilities must contain "
                "DraftClaimCompactionComponentIncompatibility",
            )


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
