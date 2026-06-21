from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import TracebackType
from typing import Protocol, cast

import asyncpg
import structlog

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
)
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
from src.contexts.capacity_runtime.infrastructure.postgres.postgres_llm_attempt_capacity_observation_repository import (
    PostgresLlmAttemptCapacityObservationRepository,
)
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    DueWorkItemRecord,
    WorkItemLeaseRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.lease_admitted_work_items import (
    LeaseAdmittedWorkItemsResult,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_attempt_dispatch_repository import (
    PostgresWorkItemAttemptDispatchRepository,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_lease_repository import (
    PostgresWorkItemLeaseRepository,
)
from src.contexts.knowledge_workbench.application.sagas.capacity_window_workflow_events import (
    CapacityWindowExhaustionSnapshot,
)
from src.contexts.knowledge_workbench.application.sagas.claim_builder_dispatch_preparation import (
    ClaimBuilderDispatchPreparationBuilder,
)
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    LlmCapacityAllocationSlot,
    LlmCapacityProjectionResult,
    zero_llm_capacity_projection,
)
from src.contexts.llm_runtime.application.capacity.resolve_llm_dispatch_input_size_preflight import (
    LlmDispatchInputSizePreflightDecision,
    ResolveLlmDispatchInputSizePreflight,
    ResolveLlmDispatchInputSizePreflightCommand,
    ResolveLlmDispatchInputSizePreflightResult,
)
from src.contexts.llm_runtime.application.capacity.resolve_llm_dispatch_preparation_strategy import (
    ResolveLlmDispatchPreparationStrategy,
    ResolveLlmDispatchPreparationStrategyCommand,
)
from src.contexts.llm_runtime.application.capacity.select_active_llm_model_capacity import (
    SelectActiveLlmModelCapacity,
    SelectActiveLlmModelCapacityResult,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelRouteCatalog,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.contexts.llm_runtime.infrastructure.postgres.postgres_llm_route_capacity_reservation_repository import (
    LlmRouteCapacityReservation,
    LlmRouteCapacityReservationTotal,
    PostgresLlmRouteCapacityReservationRepository,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    build_groq_free_plan_model_profiles,
)
from src.interfaces.composition.lease_llm_admitted_work_items import (
    LeaseLlmAdmittedWorkItemsResult,
    LlmAdmittedLeasedWorkItem,
    llm_admitted_leased_work_item_from_pre_lease_status,
)
from src.interfaces.composition.start_llm_admitted_work_item_attempts import (
    StartLlmAdmittedWorkItemAttempts,
    StartLlmAdmittedWorkItemAttemptsCommand,
    StartLlmAdmittedWorkItemAttemptsResult,
    StartedLlmAdmittedAttempt,
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
    retry_plan: WorkItemRetryPlan | None = None
    use_local_active_model_tpm_budget: bool = False
    allow_automatic_fallbacks: bool = True
    provider_account_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.work_kind, WorkKind):
            raise TypeError("work_kind must be WorkKind")
        _require_positive_int(self.requested_items, field_name="requested_items")
        if not isinstance(self.worker, WorkerRef):
            raise TypeError("worker must be WorkerRef")
        _require_non_empty_text(
            self.lease_token_prefix,
            field_name="lease_token_prefix",
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
        if self.retry_plan is not None and not isinstance(
            self.retry_plan,
            WorkItemRetryPlan,
        ):
            raise TypeError("retry_plan must be WorkItemRetryPlan when provided")
        if not isinstance(self.use_local_active_model_tpm_budget, bool):
            raise TypeError("use_local_active_model_tpm_budget must be bool")
        if not isinstance(self.allow_automatic_fallbacks, bool):
            raise TypeError("allow_automatic_fallbacks must be bool")
        if not isinstance(self.provider_account_refs, tuple):
            raise TypeError("provider_account_refs must be tuple")
        for account_ref in self.provider_account_refs:
            _require_non_empty_text(account_ref, field_name="provider_account_refs")
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
    capacity_window_exhaustion: CapacityWindowExhaustionSnapshot | None = None

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
        if self.capacity_window_exhaustion is not None and not isinstance(
            self.capacity_window_exhaustion,
            CapacityWindowExhaustionSnapshot,
        ):
            raise TypeError(
                "capacity_window_exhaustion must be CapacityWindowExhaustionSnapshot"
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
                capacity_reservation_repository = (
                    PostgresLlmRouteCapacityReservationRepository(asyncpg_connection)
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

                dispatch_preparation_strategy = command.dispatch_preparation_strategy
                admission_due_records = _admission_lane_due_records(
                    due_records,
                    dispatch_preparation_strategy=dispatch_preparation_strategy,
                    retry_plan=command.retry_plan,
                )
                initial_model_ref = command.active_model_ref
                if initial_model_ref is None:
                    initial_model_ref = self.route_catalog.primary_model_ref()

                if not admission_due_records:
                    LOGGER.info(
                        "knowledge_llm_prepare_no_due_records",
                        work_kind=command.work_kind.value,
                        requested_items=command.requested_items,
                        active_model_ref=initial_model_ref,
                        now=command.now.isoformat(),
                    )
                    return _no_due_work_items_result(
                        command=command,
                        active_model_ref=initial_model_ref,
                    )

                preparation_profile = _preparation_profile(
                    command=command,
                    due_records=admission_due_records,
                    builder=self.dispatch_preparation_builder,
                )

                strategy_result = ResolveLlmDispatchPreparationStrategy().execute(
                    ResolveLlmDispatchPreparationStrategyCommand(
                        current_active_model_ref=initial_model_ref,
                        route_catalog=self.route_catalog,
                        retry_plan=command.retry_plan,
                        strategy=dispatch_preparation_strategy,
                    )
                )
                preflight_result = ResolveLlmDispatchInputSizePreflight().execute(
                    ResolveLlmDispatchInputSizePreflightCommand(
                        active_model_ref=strategy_result.active_model_ref,
                        profile=preparation_profile,
                        route_catalog=self.route_catalog,
                        allow_automatic_fallbacks=command.allow_automatic_fallbacks,
                    )
                )
                LOGGER.info(
                    "knowledge_llm_prepare_preflight",
                    work_kind=command.work_kind.value,
                    profile_id=preparation_profile.profile_id,
                    estimated_prompt_tokens=(
                        preparation_profile.estimated_prompt_tokens
                    ),
                    estimated_completion_tokens=(
                        preparation_profile.estimated_completion_tokens
                    ),
                    estimated_total_tokens=preparation_profile.estimated_total_tokens,
                    estimated_tpm_input_tokens=(
                        preparation_profile.estimated_prompt_tokens
                    ),
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
                    command.provider_account_refs or self.provider_account_refs,
                )
                reservation_account_refs = _reservation_account_refs(
                    provider_account_refs=provider_account_refs,
                    configured_capacities=command.account_capacities,
                    active_model_ref=resolved_active_model_ref,
                )
                for account_ref in reservation_account_refs:
                    await capacity_reservation_repository.lock_route(
                        provider="groq",
                        account_ref=account_ref,
                        model_ref=resolved_active_model_ref,
                    )
                account_capacities = await _preparation_account_capacities(
                    command=command,
                    due_records=admission_due_records,
                    builder=self.dispatch_preparation_builder,
                    active_model_ref=resolved_active_model_ref,
                    provider_account_refs=provider_account_refs,
                    model_profiles=_resolved_model_profiles(self.model_profiles),
                    capacity_observation_repository=capacity_observation_repository,
                    profile=preparation_profile,
                    now=command.now,
                    use_local_active_model_tpm_budget=use_local_active_model_tpm_budget,
                )
                reservation_totals = (
                    await capacity_reservation_repository.active_totals(
                        provider="groq",
                        account_refs=reservation_account_refs,
                        model_ref=resolved_active_model_ref,
                        now=command.now,
                    )
                )
                account_capacities = _subtract_active_reservations(
                    account_capacities=account_capacities,
                    reservation_totals=reservation_totals,
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
                            "remaining_minute_requests": (
                                capacity.remaining_minute_requests
                            ),
                            "remaining_minute_tokens": capacity.remaining_minute_tokens,
                            "remaining_daily_requests": (
                                capacity.remaining_daily_requests
                            ),
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
                    due_records=admission_due_records,
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
                    capacity_decision_status=(
                        lease_result.lease_result.capacity_decision.status.value
                    ),
                    capacity_decision_reason=(
                        lease_result.lease_result.capacity_decision.reason
                    ),
                    max_admissible_items=(
                        lease_result.lease_result.capacity_decision.max_admissible_items
                    ),
                    leased_count=len(lease_result.leased),
                    selected_accounts=[
                        {
                            "provider": account.provider,
                            "account_ref": account.account_ref,
                            "model_ref": account.model_ref,
                            "slot_index": getattr(account, "slot_index", None),
                        }
                        for account in (
                            lease_result.active_model_capacity_selection.selected_accounts
                        )
                    ],
                    capacity_retry_at=(
                        capacity_retry_at.isoformat()
                        if capacity_retry_at is not None
                        else None
                    ),
                )

                attempt_result = await StartLlmAdmittedWorkItemAttempts(
                    repository=attempt_repository,
                ).execute(
                    StartLlmAdmittedWorkItemAttemptsCommand(
                        leased_items=lease_result.leased,
                        started_at=command.started_at,
                    ),
                )
                for started_attempt in attempt_result.started_attempts:
                    await capacity_reservation_repository.reserve(
                        _capacity_reservation_from_started_attempt(
                            attempt=started_attempt,
                            expires_at=command.lease_expires_at,
                            created_at=command.started_at,
                        )
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
                    and admission_due_records
                    and not lease_result.leased
                ):
                    next_capacity_retry_at = await _local_active_model_capacity_retry_at(
                        capacity_observation_repository=capacity_observation_repository,
                        provider_account_refs=provider_account_refs,
                        account_capacities=account_capacities,
                        active_model_ref=resolved_active_model_ref,
                        profile=preparation_profile,
                        now=command.now,
                    )
                capacity_window_exhaustion = None
                if (
                    next_capacity_retry_at is not None
                    and admission_due_records
                    and not lease_result.leased
                ):
                    capacity_window_exhaustion = _prepare_capacity_window_exhaustion(
                        account_capacities=account_capacities,
                        active_model_ref=resolved_active_model_ref,
                        reset_at=next_capacity_retry_at,
                    )
                return PrepareLlmDispatchBatchResult(
                    lease_result=lease_result,
                    attempt_result=attempt_result,
                    input_size_preflight_decision=preflight_result.decision.value,
                    input_size_preflight_reason=preflight_result.reason,
                    input_size_preflight_active_model_ref=preflight_result.active_model_ref,
                    source_split_required=False,
                    capacity_retry_at=next_capacity_retry_at,
                    capacity_window_exhaustion=capacity_window_exhaustion,
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
    reserved_output_tokens: int


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

    def admitted_output_tokens(self, *, estimated_input_tokens: int) -> int:
        return max(0, self.remaining_minute_tokens - estimated_input_tokens)

    def can_admit(
        self,
        *,
        estimated_input_tokens: int,
        minimum_output_tokens: int,
    ) -> bool:
        admitted_output_tokens = self.admitted_output_tokens(
            estimated_input_tokens=estimated_input_tokens,
        )
        reserved_total_tokens = estimated_input_tokens + admitted_output_tokens
        minimum_total_tokens = estimated_input_tokens + minimum_output_tokens
        return (
            self.remaining_minute_requests > 0
            and self.remaining_daily_requests > 0
            and admitted_output_tokens >= minimum_output_tokens
            and self.remaining_minute_tokens >= minimum_total_tokens
            and self.remaining_daily_tokens >= minimum_total_tokens
            and self.remaining_daily_tokens >= reserved_total_tokens
        )

    def consume(
        self,
        *,
        estimated_input_tokens: int,
        reserved_output_tokens: int,
    ) -> None:
        minimum_output_tokens = reserved_output_tokens
        if not self.can_admit(
            estimated_input_tokens=estimated_input_tokens,
            minimum_output_tokens=minimum_output_tokens,
        ):
            raise ValueError("input capacity cannot admit work item")
        reserved_total_tokens = estimated_input_tokens + reserved_output_tokens
        self.remaining_minute_requests -= 1
        self.remaining_daily_requests -= 1
        self.remaining_minute_tokens -= reserved_total_tokens
        self.remaining_daily_tokens -= reserved_total_tokens


def _dispatch_preparation_strategy_from_retry_plan(
    *,
    retry_plan: WorkItemRetryPlan | None,
    legacy_strategy: str | None,
) -> str | None:
    if retry_plan is None:
        return legacy_strategy

    strategy_by_retry_plan = {
        WorkItemRetryPlan.RETRY_SAME_ROUTE: "RETRY_SAME_ROUTE",
        WorkItemRetryPlan.RETRY_ALTERNATE_ROUTE: "RETRY_SAME_ROUTE",
        WorkItemRetryPlan.WAIT_NEAREST_ADMISSION_WINDOW: "RETRY_SAME_ROUTE",
        WorkItemRetryPlan.RETRY_VALIDATION_CHECK_ROUTE: (
            "RETRY_EMPTY_CLAIMS_CHECK_MODEL"
        ),
        WorkItemRetryPlan.RETRY_LARGER_INPUT_LIMIT_ROUTE: (
            "RETRY_LARGER_INPUT_LIMIT_MODEL"
        ),
        WorkItemRetryPlan.RETRY_LARGER_OUTPUT_LIMIT_ROUTE: (
            "RETRY_LARGER_OUTPUT_LIMIT_MODEL"
        ),
        WorkItemRetryPlan.RETRY_DAILY_FALLBACK_ROUTE: (
            "RETRY_DAILY_LIMIT_FALLBACK_MODEL"
        ),
    }

    strategy = strategy_by_retry_plan.get(retry_plan)
    if strategy is None:
        raise ValueError(f"retry_plan cannot be prepared for dispatch: {retry_plan}")

    if legacy_strategy is not None and legacy_strategy != strategy:
        raise ValueError("retry_plan conflicts with dispatch_preparation_strategy")

    return strategy


def _admission_lane_due_records(
    due_records: tuple[DueWorkItemRecord, ...],
    *,
    dispatch_preparation_strategy: str | None = None,
    retry_plan: WorkItemRetryPlan | None = None,
) -> tuple[DueWorkItemRecord, ...]:
    if retry_plan is not None or dispatch_preparation_strategy is not None:
        return _retry_first_due_records(due_records)

    return due_records


def _retry_first_due_records(
    due_records: tuple[DueWorkItemRecord, ...],
) -> tuple[DueWorkItemRecord, ...]:
    retry_records = tuple(
        record
        for record in due_records
        if record.work_item.status is WorkItemStatus.RETRYABLE_FAILED
    )
    non_retry_records = tuple(
        record
        for record in due_records
        if record.work_item.status is not WorkItemStatus.RETRYABLE_FAILED
    )
    return retry_records + non_retry_records


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
    candidates = _input_admitted_candidates(
        due_records=due_records,
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
            llm_admitted_leased_work_item_from_pre_lease_status(
                leased=leased_record,
                allocation=allocation,
                execution_settings=execution_settings,
                pre_lease_status=candidate.record.work_item.status,
                schedule_payload_override=_admitted_schedule_payload(
                    schedule_payload=leased_record.schedule_payload,
                    reserved_output_tokens=candidate.reserved_output_tokens,
                ),
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
    pending_retry_records = [
        record
        for record in due_records
        if record.work_item.status is WorkItemStatus.RETRYABLE_FAILED
    ]
    pending_fresh_records = [
        record
        for record in due_records
        if record.work_item.status is WorkItemStatus.READY
    ]

    for account in mutable_accounts:
        if len(candidates) >= requested_items:
            break

        selected_record = _pop_first_record_that_fits(
            records=pending_retry_records,
            account=account,
        )
        if selected_record is None:
            selected_record = _pop_first_record_that_fits(
                records=pending_fresh_records,
                account=account,
            )
        if selected_record is None:
            continue

        candidates.append(selected_record)

    return tuple(candidates)


def _pop_first_record_that_fits(
    *,
    records: list[DueWorkItemRecord],
    account: _MutableInputCapacity,
) -> _InputAdmittedCandidate | None:
    for index, record in enumerate(records):
        estimated_input_tokens = _estimated_input_tokens_from_due_record(record)
        minimum_output_tokens = _reserved_output_tokens_from_due_record(record)
        if not account.can_admit(
            estimated_input_tokens=estimated_input_tokens,
            minimum_output_tokens=minimum_output_tokens,
        ):
            continue

        admitted_output_tokens = account.admitted_output_tokens(
            estimated_input_tokens=estimated_input_tokens,
        )
        account.consume(
            estimated_input_tokens=estimated_input_tokens,
            reserved_output_tokens=admitted_output_tokens,
        )
        records.pop(index)
        return _InputAdmittedCandidate(
            record=record,
            provider=account.provider,
            account_ref=account.account_ref,
            model_ref=account.model_ref,
            estimated_input_tokens=estimated_input_tokens,
            reserved_output_tokens=admitted_output_tokens,
        )
    return None


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


def _reserved_output_tokens_from_due_record(record: DueWorkItemRecord) -> int:
    estimate_payload = record.schedule_payload.get("llm_capacity_estimate")
    if not isinstance(estimate_payload, Mapping):
        raise ValueError("schedule_payload.llm_capacity_estimate is required")

    value = estimate_payload.get("reserved_output_tokens")
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("llm_capacity_estimate.reserved_output_tokens must be int")
    if value < 0:
        raise ValueError("llm_capacity_estimate.reserved_output_tokens must be >= 0")
    return value


def _admitted_schedule_payload(
    *,
    schedule_payload: Mapping[str, object],
    reserved_output_tokens: int,
) -> dict[str, object]:
    estimate_payload = schedule_payload.get("llm_capacity_estimate")
    if not isinstance(estimate_payload, Mapping):
        raise ValueError("schedule_payload.llm_capacity_estimate is required")
    updated_estimate = dict(estimate_payload)
    updated_estimate["reserved_output_tokens"] = reserved_output_tokens
    updated_estimate["estimated_total_tokens"] = (
        _require_int_value(
            updated_estimate.get("estimated_input_tokens"),
            field_name="llm_capacity_estimate.estimated_input_tokens",
        )
        + reserved_output_tokens
    )

    updated_payload = dict(schedule_payload)
    updated_payload["llm_capacity_estimate"] = updated_estimate
    return updated_payload


def _require_int_value(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    return value


def _reservation_account_refs(
    *,
    provider_account_refs: tuple[str, ...],
    configured_capacities: tuple[LlmProviderAccountCapacity, ...],
    active_model_ref: str,
) -> tuple[str, ...]:
    refs = {
        capacity.account_ref
        for capacity in configured_capacities
        if capacity.provider == "groq" and capacity.model_ref == active_model_ref
    }
    if refs:
        return tuple(sorted(refs))
    return tuple(sorted(provider_account_refs))


def _subtract_active_reservations(
    *,
    account_capacities: tuple[LlmProviderAccountCapacity, ...],
    reservation_totals: tuple[LlmRouteCapacityReservationTotal, ...],
) -> tuple[LlmProviderAccountCapacity, ...]:
    totals_by_route = {
        (total.provider, total.account_ref, total.model_ref): total
        for total in reservation_totals
    }
    adjusted: list[LlmProviderAccountCapacity] = []
    for capacity in account_capacities:
        total = totals_by_route.get(
            (capacity.provider, capacity.account_ref, capacity.model_ref)
        )
        if total is None:
            adjusted.append(capacity)
            continue
        adjusted.append(
            LlmProviderAccountCapacity(
                provider=capacity.provider,
                account_ref=capacity.account_ref,
                model_ref=capacity.model_ref,
                remaining_minute_requests=max(
                    capacity.remaining_minute_requests - total.reserved_requests,
                    0,
                ),
                remaining_minute_tokens=max(
                    capacity.remaining_minute_tokens - total.reserved_tokens,
                    0,
                ),
                remaining_daily_requests=max(
                    capacity.remaining_daily_requests - total.reserved_requests,
                    0,
                ),
                remaining_daily_tokens=max(
                    capacity.remaining_daily_tokens - total.reserved_tokens,
                    0,
                ),
            )
        )
    return tuple(adjusted)


def _capacity_reservation_from_started_attempt(
    *,
    attempt: StartedLlmAdmittedAttempt,
    expires_at: datetime,
    created_at: datetime,
) -> LlmRouteCapacityReservation:
    allocation = attempt.dispatch_payload.get("llm_allocation")
    schedule_payload = attempt.dispatch_payload.get("schedule_payload")
    if not isinstance(allocation, Mapping):
        raise TypeError("dispatch llm_allocation must be Mapping")
    if not isinstance(schedule_payload, Mapping):
        raise TypeError("dispatch schedule_payload must be Mapping")
    estimate = schedule_payload.get("llm_capacity_estimate")
    if not isinstance(estimate, Mapping):
        raise TypeError("dispatch llm_capacity_estimate must be Mapping")

    return LlmRouteCapacityReservation(
        attempt_id=attempt.attempt_id,
        provider=_mapping_text(allocation, "provider"),
        account_ref=_mapping_text(allocation, "account_ref"),
        model_ref=_mapping_text(allocation, "model_ref"),
        reserved_requests=1,
        reserved_tokens=_mapping_positive_int(estimate, "estimated_total_tokens"),
        expires_at=expires_at,
        created_at=created_at,
    )


def _mapping_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _mapping_positive_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be positive int")
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


def _prepare_capacity_window_exhaustion(
    *,
    account_capacities: tuple[LlmProviderAccountCapacity, ...],
    active_model_ref: str,
    reset_at: datetime,
) -> CapacityWindowExhaustionSnapshot | None:
    matching_accounts = tuple(
        account
        for account in account_capacities
        if account.model_ref == active_model_ref
    )
    if not matching_accounts:
        return None

    exhausted_account = next(
        (
            account
            for account in matching_accounts
            if _exhausted_dimensions_from_account_capacity(account)
        ),
        matching_accounts[0],
    )
    exhausted_dimensions = _exhausted_dimensions_from_account_capacity(
        exhausted_account,
    )
    if not exhausted_dimensions:
        exhausted_dimensions = ("capacity_window",)

    return CapacityWindowExhaustionSnapshot(
        provider=exhausted_account.provider,
        account_ref=exhausted_account.account_ref,
        model_ref=exhausted_account.model_ref,
        exhausted_reason="prepare_capacity_window_unavailable",
        exhausted_dimensions=exhausted_dimensions,
        reset_at=reset_at,
    )


def _exhausted_dimensions_from_account_capacity(
    account: LlmProviderAccountCapacity,
) -> tuple[str, ...]:
    dimensions: list[str] = []
    if account.remaining_minute_requests == 0:
        dimensions.append("minute_requests")
    if account.remaining_minute_tokens == 0:
        dimensions.append("minute_tokens")
    if account.remaining_daily_requests == 0:
        dimensions.append("daily_requests")
    if account.remaining_daily_tokens == 0:
        dimensions.append("daily_tokens")
    return tuple(dimensions)


def _no_due_work_items_result(
    *,
    command: PrepareLlmDispatchBatchCommand,
    active_model_ref: str,
) -> PrepareLlmDispatchBatchResult:
    projection = zero_llm_capacity_projection(
        requested_items=command.requested_items,
    )
    return PrepareLlmDispatchBatchResult(
        lease_result=LeaseLlmAdmittedWorkItemsResult(
            active_model_capacity_selection=SelectActiveLlmModelCapacityResult(
                active_model_ref=active_model_ref,
                selected_accounts=(),
                projection=projection,
            ),
            lease_result=LeaseAdmittedWorkItemsResult(
                capacity_decision=CapacityDecision(
                    status=CapacityDecisionStatus.REJECT,
                    work_class=CapacityWorkClass.LLM_BOUND,
                    max_admissible_items=0,
                    blocking_resources=(CapacityResourceKind.EXTERNAL_IO,),
                    reason="no due work items",
                ),
                leased=(),
            ),
            leased=(),
        ),
        attempt_result=StartLlmAdmittedWorkItemAttemptsResult(
            started_attempts=(),
        ),
        input_size_preflight_decision=(
            LlmDispatchInputSizePreflightDecision.USE_ACTIVE_MODEL.value
        ),
        input_size_preflight_reason="no due work items",
        input_size_preflight_active_model_ref=active_model_ref,
        capacity_retry_at=None,
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
    latest_observations = (
        await capacity_observation_repository.latest_observations_for_accounts(
            provider="groq",
            account_refs=observation_account_refs,
            model_ref=active_model_ref,
        )
    )
    latest_observations_by_account_ref = {
        observation.account_ref: observation for observation in latest_observations
    }

    if use_local_active_model_tpm_budget:
        recent_observations = (
            await capacity_observation_repository.observations_for_accounts_since(
                provider="groq",
                account_refs=observation_account_refs,
                model_ref=active_model_ref,
                since=now - timedelta(seconds=60),
            )
        )
        local_fallback_capacities = {
            capacity.account_ref: capacity
            for capacity in _local_active_model_tpm_account_capacities(
                seed_capacities=seed_capacities,
                observations=recent_observations,
                now=now,
            )
        }
        return tuple(
            _capacity_from_latest_observation(
                seed_capacity=seed_capacity,
                observation=latest_observations_by_account_ref.get(
                    seed_capacity.account_ref
                ),
                profile=profile,
                now=now,
            )
            if _observation_has_header_capacity_state(
                latest_observations_by_account_ref.get(seed_capacity.account_ref),
            )
            else local_fallback_capacities[seed_capacity.account_ref]
            for seed_capacity in seed_capacities
        )

    return tuple(
        _capacity_from_latest_observation(
            seed_capacity=seed_capacity,
            observation=latest_observations_by_account_ref.get(
                seed_capacity.account_ref
            ),
            profile=profile,
            now=now,
        )
        for seed_capacity in seed_capacities
    )


def _observation_has_header_capacity_state(
    observation: LlmAttemptCapacityObservation | None,
) -> bool:
    if observation is None:
        return False
    return (
        observation.remaining_minute_requests is not None
        or observation.remaining_minute_tokens is not None
        or observation.remaining_daily_requests is not None
        or observation.remaining_daily_tokens is not None
        or observation.minute_reset_at is not None
        or observation.daily_reset_at is not None
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


@dataclass(frozen=True, slots=True)
class _LocalActiveModelMinuteWindow:
    observations: tuple[LlmAttemptCapacityObservation, ...]
    reset_at: datetime


def _local_active_model_tpm_account_capacities(
    *,
    seed_capacities: tuple[LlmProviderAccountCapacity, ...],
    observations: tuple[LlmAttemptCapacityObservation, ...],
    now: datetime,
) -> tuple[LlmProviderAccountCapacity, ...]:
    observations_by_account_ref: dict[str, list[LlmAttemptCapacityObservation]] = {
        seed_capacity.account_ref: [] for seed_capacity in seed_capacities
    }

    for observation in sorted(observations, key=lambda item: item.observed_at):
        account_bucket = observations_by_account_ref.get(observation.account_ref)
        if account_bucket is None:
            continue
        account_bucket.append(observation)

    capacities: list[LlmProviderAccountCapacity] = []
    for seed_capacity in seed_capacities:
        seed_observations = tuple(
            observations_by_account_ref[seed_capacity.account_ref],
        )
        active_window = _active_local_model_minute_window(
            observations=seed_observations,
            now=now,
        )

        minute_exhausted = False
        minute_request_count = 0
        minute_token_count = 0

        if active_window is not None:
            for observation in active_window.observations:
                actual_token_usage = _actual_token_usage(observation)
                if (
                    observation.outcome_class in {"deferred", "retryable_failed"}
                    and actual_token_usage is None
                ):
                    minute_exhausted = True
                    continue
                if actual_token_usage is None:
                    continue
                minute_request_count += 1
                minute_token_count += actual_token_usage

        if minute_exhausted:
            remaining_minute_requests = 0
            remaining_minute_tokens = 0
        else:
            remaining_minute_requests = max(
                seed_capacity.remaining_minute_requests - minute_request_count,
                0,
            )
            remaining_minute_tokens = max(
                seed_capacity.remaining_minute_tokens - minute_token_count,
                0,
            )

        daily_exhausted = any(
            _daily_capacity_exhausted(observation)
            and (observation.daily_reset_at is None or observation.daily_reset_at > now)
            for observation in seed_observations
        )
        if daily_exhausted:
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


def _active_local_model_minute_window(
    *,
    observations: tuple[LlmAttemptCapacityObservation, ...],
    now: datetime,
) -> _LocalActiveModelMinuteWindow | None:
    current_observations: list[LlmAttemptCapacityObservation] = []
    current_reset_at: datetime | None = None

    for observation in sorted(observations, key=lambda item: item.observed_at):
        if current_reset_at is None or observation.observed_at >= current_reset_at:
            current_observations = [observation]
            current_reset_at = _local_model_minute_reset_at(observation)
            continue

        current_observations.append(observation)

        if observation.minute_reset_at is not None:
            current_reset_at = observation.minute_reset_at

    if current_reset_at is None or current_reset_at <= now:
        return None

    return _LocalActiveModelMinuteWindow(
        observations=tuple(current_observations),
        reset_at=current_reset_at,
    )


def _local_model_minute_reset_at(
    observation: LlmAttemptCapacityObservation,
) -> datetime:
    if observation.minute_reset_at is not None:
        return observation.minute_reset_at
    return observation.observed_at + timedelta(seconds=60)


def _daily_capacity_exhausted(observation: LlmAttemptCapacityObservation) -> bool:
    return (
        observation.remaining_daily_requests == 0
        or observation.remaining_daily_tokens == 0
    )


async def _local_active_model_capacity_retry_at(
    *,
    capacity_observation_repository: PostgresLlmAttemptCapacityObservationRepository,
    provider_account_refs: tuple[str, ...],
    account_capacities: tuple[LlmProviderAccountCapacity, ...],
    active_model_ref: str,
    profile: LlmTaskCapacityProfile,
    now: datetime,
) -> datetime | None:
    blocked_accounts = tuple(
        capacity.account_ref
        for capacity in account_capacities
        if capacity.model_ref == active_model_ref
        and capacity.remaining_daily_requests > 0
        and capacity.remaining_daily_tokens > 0
        and (
            capacity.remaining_minute_requests == 0
            or capacity.remaining_minute_tokens < profile.estimated_total_tokens
        )
    )
    if not blocked_accounts:
        return None

    observations = (
        await capacity_observation_repository.observations_for_accounts_since(
            provider="groq",
            account_refs=blocked_accounts,
            model_ref=active_model_ref,
            since=now - timedelta(seconds=60),
        )
    )

    retry_candidates: list[datetime] = []
    for account_ref in blocked_accounts:
        active_window = _active_local_model_minute_window(
            observations=tuple(
                observation
                for observation in observations
                if observation.account_ref == account_ref
            ),
            now=now,
        )
        if active_window is not None:
            retry_candidates.append(active_window.reset_at)

    if not retry_candidates:
        return None
    return min(retry_candidates)


async def _next_capacity_retry_at(
    *,
    capacity_observation_repository: PostgresLlmAttemptCapacityObservationRepository,
    provider_account_refs: tuple[str, ...],
    model_ref: str,
    now: datetime,
) -> datetime | None:
    if not provider_account_refs:
        return None

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
        if (retry_at := _observation_retry_at(observation=observation, now=now))
        is not None
    )
    if retry_candidates:
        return min(retry_candidates)
    return None


def _observation_retry_at(
    *,
    observation: LlmAttemptCapacityObservation,
    now: datetime,
) -> datetime | None:
    retry_candidates: list[datetime] = []
    if (
        observation.remaining_minute_requests == 0
        or observation.remaining_minute_tokens == 0
    ):
        if observation.minute_reset_at is not None:
            retry_candidates.append(observation.minute_reset_at)
        else:
            retry_candidates.append(_local_model_minute_reset_at(observation))

    if (
        observation.remaining_daily_requests == 0
        or observation.remaining_daily_tokens == 0
    ):
        if observation.daily_reset_at is not None:
            retry_candidates.append(observation.daily_reset_at)

    future_candidates = tuple(item for item in retry_candidates if item > now)
    if future_candidates:
        return min(future_candidates)
    return None


def _capacity_from_latest_observation(
    *,
    seed_capacity: LlmProviderAccountCapacity,
    observation: LlmAttemptCapacityObservation | None,
    profile: LlmTaskCapacityProfile,
    now: datetime,
) -> LlmProviderAccountCapacity:
    if observation is None:
        return seed_capacity

    if observation.daily_reset_at is not None and observation.daily_reset_at <= now:
        daily_requests = seed_capacity.remaining_daily_requests
        daily_tokens = seed_capacity.remaining_daily_tokens
    else:
        daily_requests = min(
            seed_capacity.remaining_daily_requests,
            _observed_capacity_value(
                observation.remaining_daily_requests,
                seed_capacity.remaining_daily_requests,
            ),
        )
        daily_tokens = min(
            seed_capacity.remaining_daily_tokens,
            _observed_capacity_value(
                observation.remaining_daily_tokens,
                seed_capacity.remaining_daily_tokens,
            ),
        )

    minute_reset_at = observation.minute_reset_at
    if minute_reset_at is None and _minute_window_exhausted(observation):
        minute_reset_at = _local_model_minute_reset_at(observation)

    minute_reset_passed = minute_reset_at is not None and minute_reset_at <= now
    if minute_reset_passed:
        minute_requests = seed_capacity.remaining_minute_requests
        minute_tokens = seed_capacity.remaining_minute_tokens
    elif _minute_window_exhausted(observation):
        minute_requests = 0
        minute_tokens = 0
    else:
        minute_requests = min(
            seed_capacity.remaining_minute_requests,
            _observed_capacity_value(
                observation.remaining_minute_requests,
                seed_capacity.remaining_minute_requests,
            ),
        )
        minute_tokens = min(
            seed_capacity.remaining_minute_tokens,
            _observed_capacity_value(
                observation.remaining_minute_tokens,
                seed_capacity.remaining_minute_tokens,
            ),
        )

    return LlmProviderAccountCapacity(
        provider=seed_capacity.provider,
        account_ref=seed_capacity.account_ref,
        model_ref=seed_capacity.model_ref,
        remaining_minute_requests=minute_requests,
        remaining_minute_tokens=minute_tokens,
        remaining_daily_requests=daily_requests,
        remaining_daily_tokens=daily_tokens,
    )


def _observed_capacity_value(observed: int | None, seed: int) -> int:
    if observed is None:
        return seed
    return observed


def _minute_window_exhausted(observation: LlmAttemptCapacityObservation) -> bool:
    if observation.remaining_minute_requests == 0:
        return True
    if observation.remaining_minute_tokens == 0:
        return True
    return False


def _actual_token_usage(observation: LlmAttemptCapacityObservation) -> int | None:
    if observation.actual_total_tokens is not None:
        return observation.actual_total_tokens
    if (
        observation.actual_prompt_tokens is not None
        and observation.actual_completion_tokens is not None
    ):
        return observation.actual_prompt_tokens + observation.actual_completion_tokens
    return observation.actual_prompt_tokens


def _affected_work_item_refs(records: tuple[DueWorkItemRecord, ...]) -> tuple[str, ...]:
    return tuple(record.work_item.work_item_id for record in records)


def _source_unit_refs(records: tuple[DueWorkItemRecord, ...]) -> tuple[str, ...]:
    refs: list[str] = []
    for record in records:
        source_unit_ref = record.schedule_payload.get("source_unit_ref")
        if not isinstance(source_unit_ref, str) or not source_unit_ref.strip():
            raise ValueError("source_unit_ref is required for source split")
        refs.append(source_unit_ref)
    return tuple(refs)


def _resolved_provider_account_refs(
    configured_refs: tuple[str, ...],
) -> tuple[str, ...]:
    if configured_refs:
        return configured_refs
    return ()


def _resolved_model_profiles(
    configured_profiles: tuple[ModelProfile, ...],
) -> tuple[ModelProfile, ...]:
    if configured_profiles:
        return configured_profiles
    return build_groq_free_plan_model_profiles()


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_empty_text_tuple(value: tuple[str, ...], *, field_name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        _require_non_empty_text(item, field_name=f"{field_name} item")


def _require_positive_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
