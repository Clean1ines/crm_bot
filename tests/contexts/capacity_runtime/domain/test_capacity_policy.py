from pathlib import Path

import pytest

from src.contexts.capacity_runtime.domain import (
    CapacityAdmissionPolicy,
    CapacityAvailability,
    CapacityDecision,
    CapacityDecisionStatus,
    CapacityNeed,
    CapacityRequest,
    CapacityResourceKind,
    CapacitySnapshot,
    CapacityWorkClass,
)


def test_allow_when_all_needs_are_available() -> None:
    request = CapacityRequest(
        work_class=CapacityWorkClass.LLM_BOUND,
        needs=(
            CapacityNeed(
                resource_kind=CapacityResourceKind.WORKER_SLOT,
                amount=1,
            ),
            CapacityNeed(
                resource_kind=CapacityResourceKind.DB_CONNECTION,
                amount=1,
            ),
        ),
    )
    snapshot = CapacitySnapshot(
        availability=(
            CapacityAvailability(
                resource_kind=CapacityResourceKind.WORKER_SLOT,
                available_amount=4,
            ),
            CapacityAvailability(
                resource_kind=CapacityResourceKind.DB_CONNECTION,
                available_amount=8,
            ),
        ),
    )

    decision = CapacityAdmissionPolicy().decide(
        request=request,
        snapshot=snapshot,
    )

    assert decision.status is CapacityDecisionStatus.ALLOW
    assert decision.is_allowed()
    assert decision.blocking_resources == ()
    assert decision.reason == "capacity_available"
    assert decision.max_admissible_items == 1


def test_throttle_when_resource_is_insufficient_but_non_zero() -> None:
    request = CapacityRequest(
        work_class=CapacityWorkClass.CPU_BOUND,
        needs=(
            CapacityNeed(
                resource_kind=CapacityResourceKind.WORKER_SLOT,
                amount=4,
            ),
        ),
    )
    snapshot = CapacitySnapshot(
        availability=(
            CapacityAvailability(
                resource_kind=CapacityResourceKind.WORKER_SLOT,
                available_amount=2,
            ),
        ),
    )

    decision = CapacityAdmissionPolicy().decide(
        request=request,
        snapshot=snapshot,
    )

    assert decision.status is CapacityDecisionStatus.THROTTLE
    assert decision.is_allowed() is False
    assert decision.blocking_resources == (CapacityResourceKind.WORKER_SLOT,)
    assert decision.reason == "capacity_temporarily_insufficient"
    assert decision.max_admissible_items == 0


def test_reject_when_resource_unavailable() -> None:
    request = CapacityRequest(
        work_class=CapacityWorkClass.IO_BOUND,
        needs=(
            CapacityNeed(
                resource_kind=CapacityResourceKind.DB_CONNECTION,
                amount=1,
            ),
        ),
    )
    snapshot = CapacitySnapshot(
        availability=(
            CapacityAvailability(
                resource_kind=CapacityResourceKind.DB_CONNECTION,
                available_amount=0,
            ),
        ),
    )

    decision = CapacityAdmissionPolicy().decide(
        request=request,
        snapshot=snapshot,
    )

    assert decision.status is CapacityDecisionStatus.REJECT
    assert decision.is_allowed() is False
    assert decision.blocking_resources == (CapacityResourceKind.DB_CONNECTION,)
    assert decision.reason == "capacity_unavailable"
    assert decision.max_admissible_items == 0


def test_missing_resource_is_treated_as_zero() -> None:
    request = CapacityRequest(
        work_class=CapacityWorkClass.EMBEDDING_BOUND,
        needs=(
            CapacityNeed(
                resource_kind=CapacityResourceKind.LOCAL_GPU_LANE,
                amount=1,
            ),
        ),
    )
    snapshot = CapacitySnapshot(availability=())

    decision = CapacityAdmissionPolicy().decide(
        request=request,
        snapshot=snapshot,
    )

    assert decision.status is CapacityDecisionStatus.REJECT
    assert decision.blocking_resources == (CapacityResourceKind.LOCAL_GPU_LANE,)
    assert decision.reason == "capacity_unavailable"
    assert decision.max_admissible_items == 0


def test_multiple_blocking_resources_are_preserved_deterministically() -> None:
    request = CapacityRequest(
        work_class=CapacityWorkClass.PARSING_BOUND,
        needs=(
            CapacityNeed(
                resource_kind=CapacityResourceKind.WORKER_SLOT,
                amount=4,
            ),
            CapacityNeed(
                resource_kind=CapacityResourceKind.DB_CONNECTION,
                amount=2,
            ),
        ),
    )
    snapshot = CapacitySnapshot(
        availability=(
            CapacityAvailability(
                resource_kind=CapacityResourceKind.WORKER_SLOT,
                available_amount=1,
            ),
            CapacityAvailability(
                resource_kind=CapacityResourceKind.DB_CONNECTION,
                available_amount=0,
            ),
        ),
    )

    decision = CapacityAdmissionPolicy().decide(
        request=request,
        snapshot=snapshot,
    )

    assert decision.status is CapacityDecisionStatus.REJECT
    assert decision.blocking_resources == (
        CapacityResourceKind.WORKER_SLOT,
        CapacityResourceKind.DB_CONNECTION,
    )
    assert decision.reason == "capacity_unavailable"
    assert decision.max_admissible_items == 0


def test_validation_rejects_bad_shapes() -> None:
    with pytest.raises(ValueError, match="amount must be > 0"):
        CapacityNeed(
            resource_kind=CapacityResourceKind.WORKER_SLOT,
            amount=0,
        )

    with pytest.raises(ValueError, match="available_amount must be >= 0"):
        CapacityAvailability(
            resource_kind=CapacityResourceKind.WORKER_SLOT,
            available_amount=-1,
        )

    with pytest.raises(ValueError, match="needs must be non-empty"):
        CapacityRequest(
            work_class=CapacityWorkClass.CPU_BOUND,
            needs=(),
        )

    with pytest.raises(ValueError, match="needs must not contain duplicate"):
        CapacityRequest(
            work_class=CapacityWorkClass.CPU_BOUND,
            needs=(
                CapacityNeed(
                    resource_kind=CapacityResourceKind.WORKER_SLOT,
                    amount=1,
                ),
                CapacityNeed(
                    resource_kind=CapacityResourceKind.WORKER_SLOT,
                    amount=2,
                ),
            ),
        )

    with pytest.raises(ValueError, match="availability must not contain duplicate"):
        CapacitySnapshot(
            availability=(
                CapacityAvailability(
                    resource_kind=CapacityResourceKind.DB_CONNECTION,
                    available_amount=1,
                ),
                CapacityAvailability(
                    resource_kind=CapacityResourceKind.DB_CONNECTION,
                    available_amount=2,
                ),
            ),
        )

    with pytest.raises(ValueError, match="ALLOW decision must not have"):
        CapacityDecision(
            status=CapacityDecisionStatus.ALLOW,
            work_class=CapacityWorkClass.IO_BOUND,
            max_admissible_items=1,
            blocking_resources=(CapacityResourceKind.WORKER_SLOT,),
            reason="capacity_available",
        )

    with pytest.raises(
        ValueError, match="THROTTLE decision must have blocking_resources"
    ):
        CapacityDecision(
            status=CapacityDecisionStatus.THROTTLE,
            work_class=CapacityWorkClass.IO_BOUND,
            max_admissible_items=0,
            blocking_resources=(),
            reason="capacity_temporarily_insufficient",
        )

    with pytest.raises(ValueError, match="reason must be non-empty"):
        CapacityDecision(
            status=CapacityDecisionStatus.ALLOW,
            work_class=CapacityWorkClass.IO_BOUND,
            max_admissible_items=1,
            blocking_resources=(),
            reason="",
        )


def test_capacity_policy_source_guard() -> None:
    source = "\n".join(
        (
            Path(
                "src/contexts/capacity_runtime/domain/capacity_decision.py",
            ).read_text(encoding="utf-8"),
            Path(
                "src/contexts/capacity_runtime/domain/capacity_policy.py",
            ).read_text(encoding="utf-8"),
        ),
    )

    required_markers = [
        "CapacityResourceKind",
        "CapacityWorkClass",
        "CapacityDecisionStatus",
        "CapacityNeed",
        "CapacityAvailability",
        "CapacityRequest",
        "CapacitySnapshot",
        "CapacityDecision",
        "CapacityAdmissionPolicy",
        "WORKER_SLOT",
        "DB_CONNECTION",
        "LLM_BOUND",
        "PARSING_BOUND",
        "capacity_available",
        "capacity_temporarily_insufficient",
        "capacity_unavailable",
    ]
    forbidden_markers = [
        "llm_runtime",
        "ProviderAccount",
        "ModelProfile",
        "Groq",
        "Qwen",
        "openai",
        "provider",
        "model",
        "account",
        "quota",
        "RPM",
        "TPM",
        "execution_runtime",
        "WorkItem",
        "LeaseWorkItem",
        "knowledge_workbench",
        "SourceUnit",
        "SourceDocument",
        "Prompt",
        "PROMPT_A",
        "DraftObservationExtraction",
        "asyncpg",
        "postgres",
        "Postgres",
        "src.infrastructure",
        "worker_loop",
        "JobDispatcher",
        "outbox_events",
        "psutil",
        "cpu_percent",
        "memory",
    ]

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source


def test_allows_when_requested_items_fit_all_resources() -> None:
    request = CapacityRequest(
        work_class=CapacityWorkClass.IO_BOUND,
        requested_items=3,
        needs=(CapacityNeed(CapacityResourceKind.WORKER_SLOT, 1),),
    )
    snapshot = CapacitySnapshot(
        availability=(CapacityAvailability(CapacityResourceKind.WORKER_SLOT, 3),),
    )

    decision = CapacityAdmissionPolicy().decide(request=request, snapshot=snapshot)

    assert decision.status is CapacityDecisionStatus.ALLOW
    assert decision.max_admissible_items == 3
    assert decision.blocking_resources == ()


def test_throttles_with_partial_max_admissible_items() -> None:
    request = CapacityRequest(
        work_class=CapacityWorkClass.IO_BOUND,
        requested_items=8,
        needs=(CapacityNeed(CapacityResourceKind.WORKER_SLOT, 1),),
    )
    snapshot = CapacitySnapshot(
        availability=(CapacityAvailability(CapacityResourceKind.WORKER_SLOT, 3),),
    )

    decision = CapacityAdmissionPolicy().decide(request=request, snapshot=snapshot)

    assert decision.status is CapacityDecisionStatus.THROTTLE
    assert decision.max_admissible_items == 3
    assert decision.blocking_resources == (CapacityResourceKind.WORKER_SLOT,)


def test_rejects_with_zero_max_admissible_items_when_resource_unavailable() -> None:
    request = CapacityRequest(
        work_class=CapacityWorkClass.IO_BOUND,
        requested_items=8,
        needs=(CapacityNeed(CapacityResourceKind.WORKER_SLOT, 1),),
    )
    snapshot = CapacitySnapshot(
        availability=(CapacityAvailability(CapacityResourceKind.WORKER_SLOT, 0),),
    )

    decision = CapacityAdmissionPolicy().decide(request=request, snapshot=snapshot)

    assert decision.status is CapacityDecisionStatus.REJECT
    assert decision.max_admissible_items == 0


def test_multiple_needs_use_min_capacity() -> None:
    request = CapacityRequest(
        work_class=CapacityWorkClass.IO_BOUND,
        requested_items=8,
        needs=(
            CapacityNeed(CapacityResourceKind.WORKER_SLOT, 1),
            CapacityNeed(CapacityResourceKind.EXTERNAL_IO, 3500),
        ),
    )
    snapshot = CapacitySnapshot(
        availability=(
            CapacityAvailability(CapacityResourceKind.WORKER_SLOT, 8),
            CapacityAvailability(CapacityResourceKind.EXTERNAL_IO, 9000),
        ),
    )

    decision = CapacityAdmissionPolicy().decide(request=request, snapshot=snapshot)

    assert decision.status is CapacityDecisionStatus.THROTTLE
    assert decision.max_admissible_items == 2
    assert decision.blocking_resources == (CapacityResourceKind.EXTERNAL_IO,)


def test_requested_items_default_remains_one() -> None:
    request = CapacityRequest(
        work_class=CapacityWorkClass.IO_BOUND,
        needs=(CapacityNeed(CapacityResourceKind.WORKER_SLOT, 1),),
    )

    assert request.requested_items == 1
