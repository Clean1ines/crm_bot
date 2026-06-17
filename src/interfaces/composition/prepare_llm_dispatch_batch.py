from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import TracebackType
from typing import Protocol, cast

import asyncpg

import structlog

from src.contexts.capacity_runtime.domain.capacity_decision import (
    CapacityAvailability,
    CapacityDecision,
    CapacityDecisionStatus,
    CapacityNeed,
    CapacityResourceKind,
    CapacitySnapshot,
    CapacityWorkClass,
)
from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    DueWorkItemRecord,
    WorkItemLeaseRepositoryPort,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.execution_runtime.application.use_cases.lease_admitted_work_items import (
    LeaseAdmittedWorkItemsResult,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_attempt_dispatch_repository import (
    PostgresWorkItemAttemptDispatchRepository,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_lease_repository import (
    PostgresWorkItemLeaseRepository,
)
from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
)
from src.contexts.capacity_runtime.infrastructure.postgres.postgres_llm_attempt_capacity_observation_repository import (
    PostgresLlmAttemptCapacityObservationRepository,
)
from src.contexts.knowledge_workbench.application.sagas.claim_builder_dispatch_preparation import (
    ClaimBuilderDispatchPreparationBuilder,
)
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    LlmCapacityAllocationSlot,
    LlmCapacityProjectionResult,
    zero_llm_capacity_projection,
)
from src.contexts.llm_runtime.application.capacity.select_active_llm_model_capacity import (
    SelectActiveLlmModelCapacity,
    SelectActiveLlmModelCapacityResult,
)
from src.contexts.llm_runtime.application.capacity.resolve_llm_dispatch_preparation_strategy import (
    ResolveLlmDispatchPreparationStrategy,
    ResolveLlmDispatchPreparationStrategyCommand,
)
from src.contexts.llm_runtime.application.capacity.resolve_llm_dispatch_input_size_preflight import (
    LlmDispatchInputSizePreflightDecision,
    ResolveLlmDispatchInputSizePreflight,
    ResolveLlmDispatchInputSizePreflightCommand,
    ResolveLlmDispatchInputSizePreflightResult,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelRouteCatalog,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.infrastructure.config.llm_runtime_settings import (
    LlmRuntimeSettings,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    build_groq_free_plan_model_profiles,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.interfaces.composition.lease_llm_admitted_work_items import (
    LlmAdmittedLeasedWorkItem,
    LeaseLlmAdmittedWorkItemsResult,
)
from src.interfaces.composition.start_llm_admitted_work_item_attempts import (
    StartLlmAdmittedWorkItemAttempts,
    StartLlmAdmittedWorkItemAttemptsCommand,
    StartLlmAdmittedWorkItemAttemptsResult,
)


LOGGER = structlog.get_logger(__name__)


class AsyncTransaction(Protocol):
    async def __aenter__(self) -> object: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


class AsyncConnection(Protocol):
    def transaction(self) -> AsyncTransaction: ...


class AsyncPool(Protocol):
    async def acquire(self) -> AsyncConnection: ...

    async def release(self, connection: AsyncConnection) -> None: ...


@dataclass(frozen=True, slots=True)
class PrepareLlmDispatchBatchCommand:
    work_kind: WorkKind
    requested_items: int
    worker: WorkerRef
    lease_token_prefix: str
    lease_expires_at: datetime
    now: datetime
    started_at: datetime
    profile: LlmTaskCapacityProfile | None = None
    account_capacities: tuple[LlmProviderAccountCapacity, ...] = ()
    active_model_ref: str | None = None
    dispatch_preparation_strategy: str | None = None
    use_local_active_model_tpm_budget: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.work_kind, WorkKind):
            raise TypeError("work_kind must be WorkKind")
        _require_positive_int(self.requested_items, field_name="requested_items")
        if not isinstance(self.worker, WorkerRef):
            raise TypeError("worker must be WorkerRef")
        _require_non_empty_text(
            self.lease_token_prefix, field_name="lease_token_prefix"
        )
        _require_timezone_aware(self.lease_expires_at, field_name="lease_expires_at")
        _require_timezone_aware(self.now, field_name="now")
        if self.lease_expires_at <= self.now:
            raise ValueError("lease_expires_at must be > now")
        if self.profile is not None and not isinstance(
            self.profile,
            LlmTaskCapacityProfile,
        ):
            raise TypeError("profile must be LlmTaskCapacityProfile when provided")
        if not isinstance(self.account_capacities, tuple):
            raise TypeError("account_capacities must be tuple")
        for account_capacity in self.account_capacities:
            if not isinstance(account_capacity, LlmProviderAccountCapacity):
                raise TypeError(
                    "account_capacities must contain LlmProviderAccountCapacity",
                )
        if self.active_model_ref is not None:
            _require_non_empty_text(
                self.active_model_ref,
                field_name="active_model_ref",
            )
        _require_timezone_aware(self.started_at, field_name="started_at")
        if self.dispatch_preparation_strategy is not None:
            _require_non_empty_text(
                self.dispatch_preparation_strategy,
                field_name="dispatch_preparation_strategy",
            )
        if not isinstance(self.use_local_active_model_tpm_budget, bool):
            raise TypeError("use_local_active_model_tpm_budget must be bool")
        if self.started_at < self.now:
            raise ValueError("started_at must be >= now")


@dataclass(frozen=True, slots=True)
class PrepareLlmDispatchBatchResult:
    lease_result: LeaseLlmAdmittedWorkItemsResult
    attempt_result: StartLlmAdmittedWorkItemAttemptsResult
    input_size_preflight_decision: str = (
        LlmDispatchInputSizePreflightDecision.USE_ACTIVE_MODEL.value
    )
    input_size_preflight_reason: str = "input size preflight used active model"
    input_size_preflight_active_model_ref: str | None = None
    source_split_required: bool = False
    affected_work_item_refs: tuple[str, ...] = ()
    source_unit_refs: tuple[str, ...] = ()
    capacity_retry_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.lease_result, LeaseLlmAdmittedWorkItemsResult):
            raise TypeError("lease_result must be LeaseLlmAdmittedWorkItemsResult")
        if not isinstance(
            self.attempt_result,
            StartLlmAdmittedWorkItemAttemptsResult,
        ):
            raise TypeError(
                "attempt_result must be StartLlmAdmittedWorkItemAttemptsResult",
            )
        if len(self.attempt_result.started_attempts) != len(self.lease_result.leased):
            raise ValueError("started attempt count must equal leased item count")
        _require_non_empty_text(
            self.input_size_preflight_decision,
            field_name="input_size_preflight_decision",
        )
        _require_non_empty_text(
            self.input_size_preflight_reason,
            field_name="input_size_preflight_reason",
        )
        if self.input_size_preflight_active_model_ref is not None:
            _require_non_empty_text(
                self.input_size_preflight_active_model_ref,
                field_name="input_size_preflight_active_model_ref",
            )
        if not isinstance(self.source_split_required, bool):
            raise TypeError("source_split_required must be bool")
        if self.capacity_retry_at is not None:
            _require_timezone_aware(
                self.capacity_retry_at,
                field_name="capacity_retry_at",
            )
        _require_non_empty_text_tuple(
            self.affected_work_item_refs,
            field_name="affected_work_item_refs",
        )
        _require_non_empty_text_tuple(
            self.source_unit_refs,
            field_name="source_unit_refs",
        )
        if self.source_split_required:
            if self.lease_result.leased:
                raise ValueError("source split required result must not lease items")
            if self.attempt_result.started_attempts:
                raise ValueError("source split required result must not start attempts")
            if not self.affected_work_item_refs:
                raise ValueError(
                    "source split required result must include affected_work_item_refs"
                )
            if not self.source_unit_refs:
                raise ValueError(
                    "source split required result must include source_unit_refs"
                )


@dataclass(frozen=True, slots=True)
class PrepareLlmDispatchBatch:
    pool: AsyncPool
    capacity_policy: CapacityAdmissionPolicy
    active_model_capacity_selector: SelectActiveLlmModelCapacity
    route_catalog: LlmModelRouteCatalog
    provider_account_refs: tuple[str, ...] = ()
    model_profiles: tuple[ModelProfile, ...] = ()
    dispatch_preparation_builder: ClaimBuilderDispatchPreparationBuilder = field(
        default_factory=ClaimBuilderDispatchPreparationBuilder,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.route_catalog, LlmModelRouteCatalog):
            raise TypeError("route_catalog must be LlmModelRouteCatalog")
        if not isinstance(
            self.dispatch_preparation_builder,
            ClaimBuilderDispatchPreparationBuilder,
        ):
            raise TypeError(
                "dispatch_preparation_builder must be "
                "ClaimBuilderDispatchPreparationBuilder",
            )

    async def execute(
        self,
        command: PrepareLlmDispatchBatchCommand,
    ) -> PrepareLlmDispatchBatchResult:
        connection = await self.pool.acquire()
        try:
            async with connection.transaction():
                asyncpg_connection = cast(asyncpg.Connection, connection)
                lease_repository = PostgresWorkItemLeaseRepository(asyncpg_connection)
                attempt_repository = PostgresWorkItemAttemptDispatchRepository(
                    asyncpg_connection,
                )
                capacity_observation_repository = (
                    PostgresLlmAttemptCapacityObservationRepository(asyncpg_connection)
                )

                due_records = await lease_repository.peek_due_work_items(
                    work_kind=command.work_kind,
                    requested_items=command.requested_items,
                    now=command.now,
                )
                LOGGER.info(
                    "knowledge_llm_prepare_due_records",
                    work_kind=command.work_kind.value,
                    requested_items=command.requested_items,
                    due_record_count=len(due_records),
                    now=command.now.isoformat(),
                )
                preparation_profile = _preparation_profile(
                    command=command,
                    due_records=due_records,
                    builder=self.dispatch_preparation_builder,
                )
                initial_model_ref = command.active_model_ref
                if initial_model_ref is None:
                    initial_model_ref = self.route_catalog.primary_model_ref()

                strategy_result = ResolveLlmDispatchPreparationStrategy().execute(
                    ResolveLlmDispatchPreparationStrategyCommand(
                        current_active_model_ref=initial_model_ref,
                        strategy=command.dispatch_preparation_strategy,
                        route_catalog=self.route_catalog,
                    )
                )
                preflight_result = ResolveLlmDispatchInputSizePreflight().execute(
                    ResolveLlmDispatchInputSizePreflightCommand(
                        active_model_ref=strategy_result.active_model_ref,
                        profile=preparation_profile,
                        route_catalog=self.route_catalog,
                    )
                )
                LOGGER.info(
                    "knowledge_llm_prepare_preflight",
                    work_kind=command.work_kind.value,
                    profile_id=preparation_profile.profile_id,
                    estimated_prompt_tokens=preparation_profile.estimated_prompt_tokens,
                    estimated_completion_tokens=preparation_profile.estimated_completion_tokens,
                    estimated_total_tokens=preparation_profile.estimated_total_tokens,
                    estimated_tpm_input_tokens=preparation_profile.estimated_prompt_tokens,
                    estimated_requests=preparation_profile.estimated_requests,
                    initial_model_ref=initial_model_ref,
                    strategy_active_model_ref=strategy_result.active_model_ref,
                    preflight_decision=preflight_result.decision.value,
                    preflight_reason=preflight_result.reason,
                    preflight_active_model_ref=preflight_result.active_model_ref,
                )
                resolved_active_model_ref = preflight_result.active_model_ref
                use_local_active_model_tpm_budget = (
                    command.use_local_active_model_tpm_budget
                    or resolved_active_model_ref
                    == self.route_catalog.primary_model_ref()
                )
                if (
                    preflight_result.decision
                    is LlmDispatchInputSizePreflightDecision.SOURCE_SPLIT_REQUIRED
                ):
                    return await _source_split_required_result(
                        command=command,
                        preflight_result=preflight_result,
                        lease_repository=lease_repository,
                    )

                provider_account_refs = _resolved_provider_account_refs(
                    self.provider_account_refs,
                )
                account_capacities = await _preparation_account_capacities(
                    command=command,
                    due_records=due_records,
                    builder=self.dispatch_preparation_builder,
                    active_model_ref=resolved_active_model_ref,
                    provider_account_refs=provider_account_refs,
                    model_profiles=_resolved_model_profiles(self.model_profiles),
                    capacity_observation_repository=capacity_observation_repository,
                    profile=preparation_profile,
                    now=command.now,
                    use_local_active_model_tpm_budget=use_local_active_model_tpm_budget,
                )
                LOGGER.info(
                    "knowledge_llm_prepare_account_capacities",
                    work_kind=command.work_kind.value,
                    active_model_ref=resolved_active_model_ref,
                    provider_account_refs=provider_account_refs,
                    account_capacities=[
                        {
                            "provider": capacity.provider,
                            "account_ref": capacity.account_ref,
                            "model_ref": capacity.model_ref,
                            "remaining_minute_requests": capacity.remaining_minute_requests,
                            "remaining_minute_tokens": capacity.remaining_minute_tokens,
                            "remaining_daily_requests": capacity.remaining_daily_requests,
                            "remaining_daily_tokens": capacity.remaining_daily_tokens,
                        }
                        for capacity in account_capacities
                    ],
                )
                capacity_retry_at = None
                if not use_local_active_model_tpm_budget:
                    capacity_retry_at = await _next_capacity_retry_at(
                        capacity_observation_repository=capacity_observation_repository,
                        provider_account_refs=provider_account_refs,
                        model_ref=resolved_active_model_ref,
                        now=command.now,
                    )

                lease_result = await _lease_input_admitted_work_items(
                    lease_repository=lease_repository,
                    due_records=due_records,
                    account_capacities=account_capacities,
                    active_model_ref=resolved_active_model_ref,
                    requested_items=command.requested_items,
                    worker=command.worker,
                    lease_token_prefix=command.lease_token_prefix,
                    lease_expires_at=command.lease_expires_at,
                    now=command.now,
                    route_catalog=self.route_catalog,
                )

                LOGGER.info(
                    "knowledge_llm_prepare_lease_result",
                    work_kind=command.work_kind.value,
                    active_model_ref=resolved_active_model_ref,
                    capacity_decision_status=lease_result.lease_result.capacity_decision.status.value,
                    capacity_decision_reason=lease_result.lease_result.capacity_decision.reason,
                    max_admissible_items=lease_result.lease_result.capacity_decision.max_admissible_items,
                    leased_count=len(lease_result.leased),
                    selected_accounts=[
                        {
                            "provider": account.provider,
                            "account_ref": account.account_ref,
                            "model_ref": account.model_ref,
                            "slot_index": getattr(account, "slot_index", None),
                        }
                        for account in lease_result.active_model_capacity_selection.selected_accounts
                    ],
                    capacity_retry_at=capacity_retry_at.isoformat()
                    if capacity_retry_at is not None
                    else None,
                )

                attempt_result = await StartLlmAdmittedWorkItemAttempts(
                    repository=attempt_repository,
                ).execute(
                    StartLlmAdmittedWorkItemAttemptsCommand(
                        leased_items=lease_result.leased,
                        started_at=command.started_at,
                    ),
                )

                LOGGER.info(
                    "knowledge_llm_prepare_attempts_started",
                    work_kind=command.work_kind.value,
                    started_attempt_count=len(attempt_result.started_attempts),
                    started_attempt_ids=[
                        attempt.attempt_id
                        for attempt in attempt_result.started_attempts
                    ],
                )

                next_capacity_retry_at = capacity_retry_at
                if (
                    use_local_active_model_tpm_budget
                    and due_records
                    and not lease_result.leased
                ):
                    next_capacity_retry_at = _local_active_model_capacity_retry_at(
                        account_capacities=account_capacities,
                        active_model_ref=resolved_active_model_ref,
                        now=command.now,
                    )
                elif attempt_result.started_attempts and next_capacity_retry_at is None:
                    next_capacity_retry_at = command.now + timedelta(seconds=60)

                return PrepareLlmDispatchBatchResult(
                    lease_result=lease_result,
                    attempt_result=attempt_result,
                    input_size_preflight_decision=preflight_result.decision.value,
                    input_size_preflight_reason=preflight_result.reason,
                    input_size_preflight_active_model_ref=(
                        preflight_result.active_model_ref
                    ),
                    source_split_required=False,
                    capacity_retry_at=next_capacity_retry_at,
                )
        finally:
            await self.pool.release(connection)


@dataclass(frozen=True, slots=True)
class _InputAdmittedCandidate:
    record: DueWorkItemRecord
    provider: str
    account_ref: str
    model_ref: str
    estimated_input_tokens: int


@dataclass(slots=True)
class _LocalAccountUsage:
    request_count: int = 0
    token_count: int = 0
    minute_exhausted: bool = False
    daily_exhausted: bool = False

    def record(self, *, token_count: int | None) -> None:
        self.request_count += 1
        if token_count is not None:
            self.token_count += token_count

    def exhaust_minute(self) -> None:
        self.minute_exhausted = True

    def exhaust_daily(self) -> None:
        self.daily_exhausted = True


@dataclass(slots=True)
class _MutableInputCapacity:
    provider: str
    account_ref: str
    model_ref: str
    remaining_minute_requests: int
    remaining_minute_tokens: int
    remaining_daily_requests: int
    remaining_daily_tokens: int

    @classmethod
    def from_capacity(
        cls,
        capacity: LlmProviderAccountCapacity,
    ) -> _MutableInputCapacity:
        return cls(
            provider=capacity.provider,
            account_ref=capacity.account_ref,
            model_ref=capacity.model_ref,
            remaining_minute_requests=capacity.remaining_minute_requests,
            remaining_minute_tokens=capacity.remaining_minute_tokens,
            remaining_daily_requests=capacity.remaining_daily_requests,
            remaining_daily_tokens=capacity.remaining_daily_tokens,
        )

    def can_admit(self, *, estimated_input_tokens: int) -> bool:
        return (
            self.remaining_minute_requests > 0
            and self.remaining_daily_requests > 0
            and self.remaining_minute_tokens >= estimated_input_tokens
            and self.remaining_daily_tokens >= estimated_input_tokens
        )

    def consume(self, *, estimated_input_tokens: int) -> None:
        if not self.can_admit(estimated_input_tokens=estimated_input_tokens):
            raise ValueError("input capacity cannot admit work item")
        self.remaining_minute_requests -= 1
        self.remaining_daily_requests -= 1
        self.remaining_minute_tokens -= estimated_input_tokens
        self.remaining_daily_tokens -= estimated_input_tokens


def _admission_lane_due_records(
    due_records: tuple[DueWorkItemRecord, ...],
) -> tuple[DueWorkItemRecord, ...]:
    retry_lane = tuple(
        record
        for record in due_records
        if record.work_item.status
        in {WorkItemStatus.RETRYABLE_FAILED, WorkItemStatus.DEFERRED}
    )
    if retry_lane:
        return retry_lane
    return due_records


async def _lease_input_admitted_work_items(
    *,
    lease_repository: PostgresWorkItemLeaseRepository,
    due_records: tuple[DueWorkItemRecord, ...],
    account_capacities: tuple[LlmProviderAccountCapacity, ...],
    active_model_ref: str,
    requested_items: int,
    worker: WorkerRef,
    lease_token_prefix: str,
    lease_expires_at: datetime,
    now: datetime,
    route_catalog: LlmModelRouteCatalog,
) -> LeaseLlmAdmittedWorkItemsResult:
    active_accounts = tuple(
        account
        for account in account_capacities
        if account.model_ref == active_model_ref
    )
    mutable_accounts = [
        _MutableInputCapacity.from_capacity(account) for account in active_accounts
    ]
    admission_records = _admission_lane_due_records(due_records)
    candidates = _input_admitted_candidates(
        due_records=admission_records,
        mutable_accounts=mutable_accounts,
        requested_items=requested_items,
    )

    execution_settings = route_catalog.execution_settings_for_model_ref(
        active_model_ref,
    )
    leased_items: list[LlmAdmittedLeasedWorkItem] = []
    allocations: list[LlmCapacityAllocationSlot] = []

    for candidate in candidates:
        leased_record = await lease_repository.lease_due_work_item_by_id(
            work_kind=candidate.record.work_item.work_kind,
            work_item_id=candidate.record.work_item.work_item_id,
            worker=worker,
            lease_token=LeaseToken(f"{lease_token_prefix}:{len(leased_items)}"),
            lease_expires_at=lease_expires_at,
            now=now,
        )
        if leased_record is None:
            continue

        allocation = LlmCapacityAllocationSlot(
            provider=candidate.provider,
            account_ref=candidate.account_ref,
            model_ref=candidate.model_ref,
            slot_index=len(allocations),
        )
        allocations.append(allocation)
        leased_items.append(
            LlmAdmittedLeasedWorkItem(
                leased=leased_record,
                allocation=allocation,
                execution_settings=execution_settings,
            ),
        )

    projection = _input_admitted_projection(
        requested_items=requested_items,
        allocations=tuple(allocations),
    )
    decision = _input_admitted_capacity_decision(projected_items=len(leased_items))

    return LeaseLlmAdmittedWorkItemsResult(
        active_model_capacity_selection=SelectActiveLlmModelCapacityResult(
            active_model_ref=active_model_ref,
            selected_accounts=active_accounts,
            projection=projection,
        ),
        lease_result=LeaseAdmittedWorkItemsResult(
            capacity_decision=decision,
            leased=tuple(item.leased for item in leased_items),
        ),
        leased=tuple(leased_items),
    )


def _input_admitted_candidates(
    *,
    due_records: tuple[DueWorkItemRecord, ...],
    mutable_accounts: list[_MutableInputCapacity],
    requested_items: int,
) -> tuple[_InputAdmittedCandidate, ...]:
    candidates: list[_InputAdmittedCandidate] = []
    for record in due_records:
        if len(candidates) >= requested_items:
            break

        estimated_input_tokens = _estimated_input_tokens_from_due_record(record)
        for account in mutable_accounts:
            if not account.can_admit(estimated_input_tokens=estimated_input_tokens):
                continue

            account.consume(estimated_input_tokens=estimated_input_tokens)
            candidates.append(
                _InputAdmittedCandidate(
                    record=record,
                    provider=account.provider,
                    account_ref=account.account_ref,
                    model_ref=account.model_ref,
                    estimated_input_tokens=estimated_input_tokens,
                ),
            )
            break

    return tuple(candidates)


def _estimated_input_tokens_from_due_record(record: DueWorkItemRecord) -> int:
    estimate_payload = record.schedule_payload.get("llm_capacity_estimate")
    if not isinstance(estimate_payload, Mapping):
        raise ValueError("schedule_payload.llm_capacity_estimate is required")

    value = estimate_payload.get("estimated_input_tokens")
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("llm_capacity_estimate.estimated_input_tokens must be int")
    if value <= 0:
        raise ValueError("llm_capacity_estimate.estimated_input_tokens must be > 0")
    return value


def _input_admitted_projection(
    *,
    requested_items: int,
    allocations: tuple[LlmCapacityAllocationSlot, ...],
) -> LlmCapacityProjectionResult:
    projected_items = len(allocations)
    return LlmCapacityProjectionResult(
        capacity_needs=(
            CapacityNeed(
                resource_kind=CapacityResourceKind.EXTERNAL_IO,
                amount=1,
            ),
        ),
        capacity_snapshot=CapacitySnapshot(
            availability=(
                CapacityAvailability(
                    resource_kind=CapacityResourceKind.EXTERNAL_IO,
                    available_amount=projected_items,
                ),
            ),
        ),
        requested_items=requested_items,
        max_projected_items=projected_items,
        allocations=allocations,
    )


def _input_admitted_capacity_decision(*, projected_items: int) -> CapacityDecision:
    if projected_items > 0:
        return CapacityDecision(
            status=CapacityDecisionStatus.ALLOW,
            work_class=CapacityWorkClass.LLM_BOUND,
            max_admissible_items=projected_items,
            reason="input token capacity available",
        )

    return CapacityDecision(
        status=CapacityDecisionStatus.REJECT,
        work_class=CapacityWorkClass.LLM_BOUND,
        max_admissible_items=0,
        blocking_resources=(CapacityResourceKind.EXTERNAL_IO,),
        reason="input token capacity unavailable",
    )


async def _source_split_required_result(
    *,
    command: PrepareLlmDispatchBatchCommand,
    preflight_result: ResolveLlmDispatchInputSizePreflightResult,
    lease_repository: WorkItemLeaseRepositoryPort,
) -> PrepareLlmDispatchBatchResult:
    projection = zero_llm_capacity_projection(
        requested_items=command.requested_items,
    )
    affected_records = await lease_repository.peek_due_work_items(
        work_kind=command.work_kind,
        requested_items=command.requested_items,
        now=command.now,
    )
    affected_work_item_refs = _affected_work_item_refs(affected_records)
    source_unit_refs = _source_unit_refs(affected_records)

    return PrepareLlmDispatchBatchResult(
        lease_result=LeaseLlmAdmittedWorkItemsResult(
            active_model_capacity_selection=SelectActiveLlmModelCapacityResult(
                active_model_ref=preflight_result.active_model_ref,
                selected_accounts=(),
                projection=projection,
            ),
            lease_result=LeaseAdmittedWorkItemsResult(
                capacity_decision=CapacityDecision(
                    status=CapacityDecisionStatus.REJECT,
                    work_class=CapacityWorkClass.LLM_BOUND,
                    max_admissible_items=0,
                    blocking_resources=(CapacityResourceKind.EXTERNAL_IO,),
                    reason=preflight_result.reason,
                ),
                leased=(),
            ),
            leased=(),
        ),
        attempt_result=StartLlmAdmittedWorkItemAttemptsResult(
            started_attempts=(),
        ),
        input_size_preflight_decision=preflight_result.decision.value,
        input_size_preflight_reason=preflight_result.reason,
        input_size_preflight_active_model_ref=preflight_result.active_model_ref,
        source_split_required=True,
        affected_work_item_refs=affected_work_item_refs,
        source_unit_refs=source_unit_refs,
    )


def _preparation_profile(
    *,
    command: PrepareLlmDispatchBatchCommand,
    due_records: tuple[DueWorkItemRecord, ...],
    builder: ClaimBuilderDispatchPreparationBuilder,
) -> LlmTaskCapacityProfile:
    if due_records:
        return builder.build_profile_from_due_work_items(due_records)
    if command.profile is None:
        raise ValueError("PrepareLlmDispatchBatch requires due work item estimates")
    return command.profile


async def _preparation_account_capacities(
    *,
    command: PrepareLlmDispatchBatchCommand,
    due_records: tuple[DueWorkItemRecord, ...],
    builder: ClaimBuilderDispatchPreparationBuilder,
    active_model_ref: str,
    provider_account_refs: tuple[str, ...],
    model_profiles: tuple[ModelProfile, ...],
    capacity_observation_repository: PostgresLlmAttemptCapacityObservationRepository,
    profile: LlmTaskCapacityProfile,
    now: datetime,
    use_local_active_model_tpm_budget: bool,
) -> tuple[LlmProviderAccountCapacity, ...]:
    if not due_records:
        if not command.account_capacities:
            raise ValueError("PrepareLlmDispatchBatch requires account capacities")
        return command.account_capacities

    seed_capacities = (
        command.account_capacities
        if command.account_capacities
        else builder.build_account_capacities(
            active_model_ref=active_model_ref,
            provider_account_refs=provider_account_refs,
            model_profiles=model_profiles,
        )
    )
    observation_account_refs = _capacity_account_refs_for_observations(
        provider_account_refs=provider_account_refs,
        seed_capacities=seed_capacities,
    )
    if use_local_active_model_tpm_budget:
        observations = (
            await capacity_observation_repository.observations_for_accounts_since(
                provider="groq",
                account_refs=observation_account_refs,
                model_ref=active_model_ref,
                since=now - timedelta(seconds=60),
            )
        )
        return _local_active_model_tpm_account_capacities(
            seed_capacities=seed_capacities,
            observations=observations,
        )

    observations = (
        await capacity_observation_repository.latest_observations_for_accounts(
            provider="groq",
            account_refs=observation_account_refs,
            model_ref=active_model_ref,
        )
    )
    observations_by_account_ref = {
        observation.account_ref: observation for observation in observations
    }

    return tuple(
        _capacity_from_latest_observation(
            seed_capacity=seed_capacity,
            observation=observations_by_account_ref.get(seed_capacity.account_ref),
            profile=profile,
            now=now,
        )
        for seed_capacity in seed_capacities
    )


def _capacity_account_refs_for_observations(
    *,
    provider_account_refs: tuple[str, ...],
    seed_capacities: tuple[LlmProviderAccountCapacity, ...],
) -> tuple[str, ...]:
    refs: list[str] = []
    for seed_capacity in seed_capacities:
        if seed_capacity.account_ref not in refs:
            refs.append(seed_capacity.account_ref)

    if refs:
        return tuple(refs)

    return provider_account_refs


def _local_active_model_tpm_account_capacities(
    *,
    seed_capacities: tuple[LlmProviderAccountCapacity, ...],
    observations: tuple[LlmAttemptCapacityObservation, ...],
) -> tuple[LlmProviderAccountCapacity, ...]:
    usage_by_account_ref = {
        seed_capacity.account_ref: _LocalAccountUsage()
        for seed_capacity in seed_capacities
    }

    for observation in observations:
        usage = usage_by_account_ref.get(observation.account_ref)
        if usage is None:
            continue

        if _daily_capacity_exhausted(observation):
            usage.exhaust_daily()

        actual_token_usage = _actual_token_usage(observation)
        if observation.outcome_class == "deferred" and actual_token_usage is None:
            usage.exhaust_minute()
            continue

        usage.record(token_count=actual_token_usage)

    capacities: list[LlmProviderAccountCapacity] = []
    for seed_capacity in seed_capacities:
        usage = usage_by_account_ref[seed_capacity.account_ref]
        if usage.minute_exhausted:
            remaining_minute_requests = 0
            remaining_minute_tokens = 0
        else:
            remaining_minute_requests = max(
                seed_capacity.remaining_minute_requests - usage.request_count,
                0,
            )
            remaining_minute_tokens = max(
                seed_capacity.remaining_minute_tokens - usage.token_count,
                0,
            )

        if usage.daily_exhausted:
            remaining_daily_requests = 0
            remaining_daily_tokens = 0
        else:
            remaining_daily_requests = seed_capacity.remaining_daily_requests
            remaining_daily_tokens = seed_capacity.remaining_daily_tokens

        capacities.append(
            LlmProviderAccountCapacity(
                provider=seed_capacity.provider,
                account_ref=seed_capacity.account_ref,
                model_ref=seed_capacity.model_ref,
                remaining_minute_requests=remaining_minute_requests,
                remaining_minute_tokens=remaining_minute_tokens,
                remaining_daily_requests=remaining_daily_requests,
                remaining_daily_tokens=remaining_daily_tokens,
            ),
        )

    return tuple(capacities)


def _daily_capacity_exhausted(observation: LlmAttemptCapacityObservation) -> bool:
    return (
        observation.remaining_daily_requests == 0
        or observation.remaining_daily_tokens == 0
    )


def _local_active_model_capacity_retry_at(
    *,
    account_capacities: tuple[LlmProviderAccountCapacity, ...],
    active_model_ref: str,
    now: datetime,
) -> datetime | None:
    for capacity in account_capacities:
        if capacity.model_ref != active_model_ref:
            continue
        if (
            capacity.remaining_daily_requests == 0
            or capacity.remaining_daily_tokens == 0
        ):
            continue
        if (
            capacity.remaining_minute_requests == 0
            or capacity.remaining_minute_tokens == 0
        ):
            return now + timedelta(seconds=60)
    return None


def _actual_token_usage(observation: LlmAttemptCapacityObservation) -> int | None:
    if observation.actual_total_tokens is not None:
        return observation.actual_total_tokens
    if (
        observation.actual_prompt_tokens is not None
        and observation.actual_completion_tokens is not None
    ):
        return observation.actual_prompt_tokens + observation.actual_completion_tokens
    if observation.actual_prompt_tokens is not None:
        return observation.actual_prompt_tokens
    return None


def _capacity_from_latest_observation(
    *,
    seed_capacity: LlmProviderAccountCapacity,
    observation: LlmAttemptCapacityObservation | None,
    profile: LlmTaskCapacityProfile,
    now: datetime,
) -> LlmProviderAccountCapacity:
    if observation is None:
        return _capacity_with_token_floor(
            seed_capacity=seed_capacity,
            profile=profile,
        )

    remaining_minute_requests = _observed_or_seed(
        observation.remaining_minute_requests,
        seed_capacity.remaining_minute_requests,
    )
    remaining_minute_tokens = _observed_or_seed(
        observation.remaining_minute_tokens,
        seed_capacity.remaining_minute_tokens,
    )
    remaining_daily_requests = _observed_or_seed(
        observation.remaining_daily_requests,
        seed_capacity.remaining_daily_requests,
    )
    remaining_daily_tokens = _observed_or_seed(
        observation.remaining_daily_tokens,
        seed_capacity.remaining_daily_tokens,
    )

    seed_after_reset = _capacity_with_token_floor(
        seed_capacity=seed_capacity,
        profile=profile,
    )

    minute_reset_at = _minute_reset_at_from_observation(observation)
    if minute_reset_at is not None and minute_reset_at <= now:
        remaining_minute_requests = seed_after_reset.remaining_minute_requests
        remaining_minute_tokens = seed_after_reset.remaining_minute_tokens

    if observation.daily_reset_at is not None and observation.daily_reset_at <= now:
        remaining_daily_requests = seed_after_reset.remaining_daily_requests
        remaining_daily_tokens = seed_after_reset.remaining_daily_tokens

    return LlmProviderAccountCapacity(
        provider=seed_capacity.provider,
        account_ref=seed_capacity.account_ref,
        model_ref=seed_capacity.model_ref,
        remaining_minute_requests=remaining_minute_requests,
        remaining_minute_tokens=remaining_minute_tokens,
        remaining_daily_requests=remaining_daily_requests,
        remaining_daily_tokens=remaining_daily_tokens,
    )


def _capacity_with_token_floor(
    *,
    seed_capacity: LlmProviderAccountCapacity,
    profile: LlmTaskCapacityProfile,
) -> LlmProviderAccountCapacity:
    _ = profile
    return seed_capacity


def _observed_or_seed(observed: int | None, seed: int) -> int:
    if observed is None:
        return seed
    return observed


def _minute_reset_at_from_observation(
    observation: LlmAttemptCapacityObservation,
) -> datetime | None:
    if observation.minute_reset_at is not None:
        return observation.minute_reset_at

    if (
        observation.remaining_minute_requests == 0
        or observation.remaining_minute_tokens == 0
        or observation.actual_prompt_tokens is not None
    ):
        return observation.observed_at + timedelta(seconds=60)

    return None


async def _next_capacity_retry_at(
    *,
    capacity_observation_repository: PostgresLlmAttemptCapacityObservationRepository,
    provider_account_refs: tuple[str, ...],
    model_ref: str,
    now: datetime,
) -> datetime | None:
    observations = (
        await capacity_observation_repository.latest_observations_for_accounts(
            provider="groq",
            account_refs=provider_account_refs,
            model_ref=model_ref,
        )
    )
    retry_candidates = tuple(
        retry_at
        for observation in observations
        for retry_at in (_observation_retry_at(observation=observation, now=now),)
        if retry_at is not None
    )
    if not retry_candidates:
        return None
    return min(retry_candidates)


def _observation_retry_at(
    *,
    observation: LlmAttemptCapacityObservation,
    now: datetime,
) -> datetime | None:
    retry_candidates: list[datetime] = []

    minute_reset_at = _minute_reset_at_from_observation(observation)
    if minute_reset_at is not None and minute_reset_at > now:
        retry_candidates.append(minute_reset_at)

    if (
        observation.daily_reset_at is not None
        and observation.daily_reset_at > now
        and (
            observation.remaining_daily_requests == 0
            or observation.remaining_daily_tokens == 0
        )
    ):
        retry_candidates.append(observation.daily_reset_at)

    if not retry_candidates:
        return None
    return min(retry_candidates)


def _resolved_provider_account_refs(
    configured: tuple[str, ...],
) -> tuple[str, ...]:
    if configured:
        return configured
    env_config = LlmRuntimeSettings.from_env_mapping(
        __import__("os").environ
    ).to_groq_env_config()
    return tuple(account.account_seed.account_ref for account in env_config.accounts)


def _resolved_model_profiles(
    configured: tuple[ModelProfile, ...],
) -> tuple[ModelProfile, ...]:
    if configured:
        return configured
    return build_groq_free_plan_model_profiles()


def _require_positive_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _affected_work_item_refs(
    records: tuple[DueWorkItemRecord, ...],
) -> tuple[str, ...]:
    return tuple(record.work_item.work_item_id for record in records)


def _source_unit_refs(records: tuple[DueWorkItemRecord, ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for record in records:
        source_unit_ref = record.schedule_payload.get("source_unit_ref")
        if not isinstance(source_unit_ref, str) or not source_unit_ref.strip():
            raise ValueError(
                "source split required schedule payload must include source_unit_ref"
            )
        refs.append(source_unit_ref)
    return tuple(refs)


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_non_empty_text_tuple(
    value: tuple[str, ...],
    *,
    field_name: str,
) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        _require_non_empty_text(item, field_name=field_name)


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
