from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import TracebackType
from typing import Self

import pytest
from structlog.testing import capture_logs

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
)
from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionStatus,
)
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    ProjectLlmCapacityToCapacityRuntime,
)
from src.contexts.llm_runtime.application.capacity.select_active_llm_model_capacity import (
    SelectActiveLlmModelCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    default_groq_llm_model_route_catalog,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_dispatch_executor import (
    GroqDispatchExecutor,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    JsonValue,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    build_groq_free_plan_model_profiles,
    model_budget_profile_for_ref,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_transport_port import (
    GroqTransportResponse,
)
from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestionAmbiguityRisk,
    WorkbenchRagEvalQuestionRole,
    WorkbenchRagEvalRetrievalClassification,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.plan_workbench_rag_eval_adjudication_work import (
    WorkbenchRagEvalAdjudicationPlanningInput,
    WorkbenchRagEvalAdjudicationRetrievedClaimSnapshot,
    WorkbenchRagEvalAdjudicationWorkPlanner,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.plan_workbench_rag_eval_question_generation_work import (
    WorkbenchRagEvalQuestionGenerationWorkPlanner,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_dispatch_preparation import (
    make_adjudication_dispatch_preparation_builder,
    make_question_generation_dispatch_preparation_builder,
    workbench_rag_eval_route_catalog,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
    PublishedWorkbenchRetrievalSourceRef,
)
from src.contexts.knowledge_workbench.application.sagas.map_claim_builder_section_plans_to_execution_schedule import (
    MapClaimBuilderSectionPlansToExecutionSchedule,
    MapClaimBuilderSectionPlansToExecutionScheduleCommand,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
    ClaimBuilderSectionWorkPlan,
    SourceDocumentRef,
    SourceUnitRef,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    DispatchPreparationBuilderRegistry,
    PrepareLlmDispatchBatch,
    PrepareLlmDispatchBatchCommand,
    _capacity_from_latest_observation,
    _observation_retry_at,
)


class DispatchInsertError(RuntimeError):
    pass


@dataclass(slots=True)
class FakeTransaction:
    connection: FakeConnection
    entered: bool = False
    exit_exc_type: type[BaseException] | None = None
    committed: bool = False
    rolled_back: bool = False
    _snapshot: dict[str, object] | None = None

    async def __aenter__(self) -> Self:
        self.entered = True
        self._snapshot = {
            "work_items": copy.deepcopy(self.connection.work_items),
            "attempts": copy.deepcopy(self.connection.attempts),
            "dispatches": copy.deepcopy(self.connection.dispatches),
            "capacity_reservations": copy.deepcopy(
                self.connection.capacity_reservations
            ),
        }
        self.connection.transactions.append(self)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        self.exit_exc_type = exc_type
        if exc_type is None:
            self.committed = True
            return None

        self.rolled_back = True
        if self._snapshot is None:
            raise RuntimeError("transaction snapshot missing")
        self.connection.work_items = copy.deepcopy(self._snapshot["work_items"])
        self.connection.attempts = copy.deepcopy(self._snapshot["attempts"])
        self.connection.dispatches = copy.deepcopy(self._snapshot["dispatches"])
        self.connection.capacity_reservations = copy.deepcopy(
            self._snapshot["capacity_reservations"]
        )
        return None


@dataclass(slots=True)
class FakeConnection:
    work_items: dict[str, dict[str, object]] = field(default_factory=dict)
    schedules: dict[str, dict[str, object]] = field(default_factory=dict)
    attempts: dict[str, dict[str, object]] = field(default_factory=dict)
    dispatches: dict[str, dict[str, object]] = field(default_factory=dict)
    transactions: list[FakeTransaction] = field(default_factory=list)
    fail_dispatch_insert: bool = False
    capacity_observations: list[dict[str, object]] = field(default_factory=list)
    capacity_reservations: list[dict[str, object]] = field(default_factory=list)
    fetch_queries: list[str] = field(default_factory=list)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(connection=self)

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.fetch_queries.append(query)
        if "FROM llm_route_capacity_reservations" in query:
            provider = str(args[0])
            account_refs = tuple(str(item) for item in args[1])
            model_ref = str(args[2])
            now = _as_datetime(args[3])
            totals: dict[str, dict[str, object]] = {}
            for reservation in self.capacity_reservations:
                if reservation["provider"] != provider:
                    continue
                if reservation["account_ref"] not in account_refs:
                    continue
                if reservation["model_ref"] != model_ref:
                    continue
                if reservation["status"] != "active":
                    continue
                if _as_datetime(reservation["expires_at"]) <= now:
                    continue
                account_ref = str(reservation["account_ref"])
                total = totals.setdefault(
                    account_ref,
                    {
                        "provider": provider,
                        "account_ref": account_ref,
                        "model_ref": model_ref,
                        "reserved_requests": 0,
                        "reserved_tokens": 0,
                    },
                )
                total["reserved_requests"] = int(total["reserved_requests"]) + 1
                total["reserved_tokens"] = int(total["reserved_tokens"]) + int(
                    reservation["reserved_tokens"]
                )
            return list(totals.values())

        if "llm_attempt_capacity_observations" in query:
            provider = str(args[0])
            model_ref = str(args[1])
            account_refs = tuple(str(item) for item in args[2])
            since = _as_datetime(args[3]) if len(args) > 3 else None
            return [
                row
                for row in self.capacity_observations
                if row.get("provider") == provider
                and row.get("account_ref") in account_refs
                and row.get("model_ref") == model_ref
                and (since is None or _as_datetime(row["observed_at"]) >= since)
            ]

        work_kind = str(args[0])
        now = _as_datetime(args[1])
        limit = int(args[2])
        candidates: list[dict[str, object]] = []

        for row in self.work_items.values():
            if row["work_kind"] != work_kind:
                continue
            if row["status"] not in {"ready", "retryable_failed"}:
                continue
            next_attempt_at = row["next_attempt_at"]
            if next_attempt_at is not None and _as_datetime(next_attempt_at) > now:
                continue
            work_item_id = str(row["work_item_id"])
            payload = self.schedules.get(work_item_id)
            if payload is None:
                continue
            candidates.append({**row, "payload": payload})

        candidates.sort(
            key=lambda row: (
                _status_priority(str(row["status"])),
                row["next_attempt_at"] is not None,
                row["next_attempt_at"] or datetime.min.replace(tzinfo=timezone.utc),
                row["updated_at"],
                row["work_item_id"],
            ),
        )
        return candidates[:limit]

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        if "FROM execution_work_item_attempt_dispatches" in query:
            attempt_id = str(args[0])
            return self.dispatches.get(attempt_id)

        if "wi.work_item_id = $2" in query:
            work_kind = str(args[0])
            work_item_id = str(args[1])
            now = _as_datetime(args[2])
            row = self.work_items.get(work_item_id)
            if row is None:
                return None
            if row["work_kind"] != work_kind:
                return None
            if row["status"] not in {"ready", "retryable_failed"}:
                return None
            next_attempt_at = row["next_attempt_at"]
            if next_attempt_at is not None and _as_datetime(next_attempt_at) > now:
                return None
            payload = self.schedules.get(work_item_id)
            if payload is None:
                return None
            return {**row, "payload": payload}

        work_kind = str(args[0])
        now = _as_datetime(args[1])
        candidates: list[dict[str, object]] = []

        for row in self.work_items.values():
            if row["work_kind"] != work_kind:
                continue
            if row["status"] not in {"ready", "retryable_failed"}:
                continue
            next_attempt_at = row["next_attempt_at"]
            if next_attempt_at is not None and _as_datetime(next_attempt_at) > now:
                continue
            work_item_id = str(row["work_item_id"])
            payload = self.schedules.get(work_item_id)
            if payload is None:
                continue
            candidates.append({**row, "payload": payload})

        candidates.sort(
            key=lambda row: (
                _status_priority(str(row["status"])),
                row["next_attempt_at"] is not None,
                row["next_attempt_at"] or datetime.min.replace(tzinfo=timezone.utc),
                row["updated_at"],
                row["work_item_id"],
            ),
        )
        return candidates[0] if candidates else None

    async def execute(self, query: str, *args: object) -> str:
        if "pg_advisory_xact_lock" in query:
            return "SELECT 1"

        if "INSERT INTO llm_route_capacity_reservations" in query:
            self.capacity_reservations.append(
                {
                    "attempt_id": args[0],
                    "provider": args[1],
                    "account_ref": args[2],
                    "model_ref": args[3],
                    "reserved_requests": args[4],
                    "reserved_tokens": args[5],
                    "status": "active",
                    "expires_at": args[6],
                    "created_at": args[7],
                }
            )
            return "INSERT 0 1"

        if "UPDATE execution_work_items" in query:
            work_item_id = str(args[0])
            row = self.work_items[work_item_id]
            row["status"] = args[1]
            row["attempt_count"] = args[2]
            row["leased_by"] = args[3]
            row["lease_token"] = args[4]
            row["lease_expires_at"] = args[5]
            row["next_attempt_at"] = None
            row["last_error_kind"] = None
            row["updated_at"] = args[6]
            return "UPDATE 1"

        if "INSERT INTO execution_work_item_attempts" in query:
            self.attempts[str(args[0])] = {
                "attempt_id": args[0],
                "work_item_id": args[1],
                "attempt_number": args[2],
                "started_at": args[3],
            }
            return "INSERT 0 1"

        if "INSERT INTO execution_work_item_attempt_dispatches" in query:
            if self.fail_dispatch_insert:
                raise DispatchInsertError("dispatch insert failed")
            self.dispatches[str(args[0])] = {
                "attempt_id": args[0],
                "work_item_id": args[1],
                "attempt_number": args[2],
                "lease_token": args[3],
                "worker_ref": args[4],
                "schedule_payload": json.loads(str(args[5])),
                "llm_allocation_payload": json.loads(str(args[6])),
                "dispatch_payload": json.loads(str(args[7])),
            }
            return "INSERT 0 1"

        raise AssertionError(f"unexpected query: {query}")


@dataclass(slots=True)
class FakePool:
    connection: FakeConnection
    released: list[FakeConnection] = field(default_factory=list)

    async def acquire(self) -> FakeConnection:
        return self.connection

    async def release(self, connection: FakeConnection) -> None:
        self.released.append(connection)


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _lease_expires_at() -> datetime:
    return datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc)


def _started_at() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _updated_at(minutes: int) -> datetime:
    return datetime(2026, 6, 10, 11, minutes, tzinfo=timezone.utc)


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.claim_builder.section_extraction")


def _worker() -> WorkerRef:
    return WorkerRef("worker-1")


def _profile() -> LlmTaskCapacityProfile:
    return LlmTaskCapacityProfile(
        profile_id="prompt-a",
        estimated_prompt_tokens=3000,
        estimated_completion_tokens=500,
    )


def _large_input_profile(prompt_tokens: int) -> LlmTaskCapacityProfile:
    return LlmTaskCapacityProfile(
        profile_id="prompt-a-large-input",
        estimated_prompt_tokens=prompt_tokens,
        estimated_completion_tokens=500,
    )


def _account(
    *,
    account_ref: str = "org-1",
    minute_requests: int = 2,
    minute_tokens: int = 7000,
    model_ref: str = "qwen/qwen3.6-27b",
    daily_requests: int = 100,
    daily_tokens: int = 50000,
) -> LlmProviderAccountCapacity:
    return LlmProviderAccountCapacity(
        provider="groq",
        account_ref=account_ref,
        model_ref=model_ref,
        remaining_minute_requests=minute_requests,
        remaining_minute_tokens=minute_tokens,
        remaining_daily_requests=daily_requests,
        remaining_daily_tokens=daily_tokens,
    )


def _work_item_row(work_item_id: str, *, ordinal: int) -> dict[str, object]:
    return {
        "work_item_id": work_item_id,
        "work_kind": _work_kind().value,
        "status": WorkItemStatus.READY.value,
        "attempt_count": 0,
        "leased_by": None,
        "lease_token": None,
        "lease_expires_at": None,
        "next_attempt_at": None,
        "last_error_kind": None,
        "created_at": _updated_at(ordinal),
        "updated_at": _updated_at(ordinal),
    }


def _schedule_payload(
    *,
    source_unit_ref: str,
    profile: LlmTaskCapacityProfile | None = None,
) -> dict[str, object]:
    capacity_profile = profile or _profile()
    return {
        "source_unit_ref": source_unit_ref,
        "llm_capacity_estimate": {
            "budget_contract_version": "v3",
            "estimator": "test_budget",
            "provider": "groq",
            "model_ref": "qwen/qwen3.6-27b",
            "model_tpm_limit": 8_000,
            "model_char_to_token_multiplier": "2.8",
            "phase": "test",
            "operation": "prepare",
            "prompt_tokens": capacity_profile.estimated_prompt_tokens,
            "artifact_tokens": 0,
            "input_tokens": capacity_profile.estimated_prompt_tokens,
            "planned_output_tokens": capacity_profile.estimated_completion_tokens,
            "safety_gap_tokens": 0,
            "required_window_tokens": capacity_profile.required_window_tokens,
        },
    }


def _claim_builder_schedule_payload(*, workflow_run_id: str) -> dict[str, object]:
    plan = ClaimBuilderSectionWorkPlan(
        workflow_run_id=workflow_run_id,
        source_document_ref=SourceDocumentRef("source-document:project-1:doc-1"),
        source_unit_ref=SourceUnitRef("source-unit:project-1:doc-1:0"),
        source_unit_ordinal=0,
        source_unit_text="Claim builder section text.",
        heading_path=("Root",),
        work_item_id="work-claim-1",
        work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
        idempotency_key="work-claim-1",
    )
    schedule_plan = (
        MapClaimBuilderSectionPlansToExecutionSchedule()
        .execute(MapClaimBuilderSectionPlansToExecutionScheduleCommand(plans=(plan,)))
        .schedule_plans[0]
    )
    return dict(schedule_plan.payload)


def _connection_with_due_items(
    count: int,
    *,
    profile: LlmTaskCapacityProfile | None = None,
) -> FakeConnection:
    connection = FakeConnection()
    for index in range(count):
        work_item_id = f"work-{index + 1}"
        connection.work_items[work_item_id] = _work_item_row(
            work_item_id,
            ordinal=index + 1,
        )
        connection.schedules[work_item_id] = _schedule_payload(
            source_unit_ref=f"unit-{index + 1}",
            profile=profile,
        )
    return connection


def _command(
    *,
    work_kind: WorkKind | None = None,
    profile: LlmTaskCapacityProfile | None = None,
    account_capacities: tuple[LlmProviderAccountCapacity, ...] = (_account(),),
    active_model_ref: str = "qwen/qwen3.6-27b",
    requested_items: int = 2,
    now: datetime | None = None,
    started_at: datetime | None = None,
    dispatch_preparation_strategy: str | None = None,
    retry_plan: WorkItemRetryPlan | None = None,
    use_local_active_model_tpm_budget: bool = False,
    correlation_context: dict[str, str] | None = None,
) -> PrepareLlmDispatchBatchCommand:
    return PrepareLlmDispatchBatchCommand(
        work_kind=work_kind or _work_kind(),
        profile=profile or _profile(),
        account_capacities=account_capacities,
        active_model_ref=active_model_ref,
        requested_items=requested_items,
        worker=_worker(),
        lease_token_prefix="lease-prefix",
        lease_expires_at=_lease_expires_at(),
        now=now or _now(),
        started_at=started_at or _started_at(),
        dispatch_preparation_strategy=dispatch_preparation_strategy,
        retry_plan=retry_plan,
        use_local_active_model_tpm_budget=use_local_active_model_tpm_budget,
        correlation_context=correlation_context or {},
    )


def _runner(pool: FakePool) -> PrepareLlmDispatchBatch:
    return PrepareLlmDispatchBatch(
        pool=pool,
        capacity_policy=CapacityAdmissionPolicy(),
        active_model_capacity_selector=SelectActiveLlmModelCapacity(
            projector=ProjectLlmCapacityToCapacityRuntime(),
        ),
        route_catalog=default_groq_llm_model_route_catalog(),
    )


def _event(logs: list[dict[str, object]], name: str) -> dict[str, object]:
    for event in logs:
        if event.get("event") == name:
            return event
    raise AssertionError(f"log event not found: {name}")


class FakeGroqTransport:
    def __init__(self) -> None:
        self.payloads: list[dict[str, JsonValue]] = []

    def post_chat_completions(
        self,
        *,
        payload: dict[str, JsonValue],
    ) -> GroqTransportResponse:
        self.payloads.append(payload)
        return GroqTransportResponse(
            status_code=200,
            headers={},
            body={
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 11},
            },
        )


def _rag_eval_runner(pool: FakePool) -> PrepareLlmDispatchBatch:
    return PrepareLlmDispatchBatch(
        pool=pool,
        capacity_policy=CapacityAdmissionPolicy(),
        active_model_capacity_selector=SelectActiveLlmModelCapacity(
            projector=ProjectLlmCapacityToCapacityRuntime(),
        ),
        route_catalog=workbench_rag_eval_route_catalog(),
        provider_account_refs=("groq_org_primary",),
        model_profiles=build_groq_free_plan_model_profiles(),
        dispatch_preparation_builder_registry=DispatchPreparationBuilderRegistry(
            builders_by_work_kind={
                WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND: (
                    make_question_generation_dispatch_preparation_builder()
                ),
                WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND: (
                    make_adjudication_dispatch_preparation_builder()
                ),
            }
        ),
    )


def _rag_eval_connection_with_plan(
    plan_work_item_id: str,
    *,
    work_kind: WorkKind,
    schedule_payload: dict[str, object],
) -> FakeConnection:
    connection = FakeConnection()
    connection.work_items[plan_work_item_id] = {
        **_work_item_row(plan_work_item_id, ordinal=1),
        "work_kind": work_kind.value,
    }
    connection.schedules[plan_work_item_id] = schedule_payload
    return connection


def _rag_eval_entry() -> PublishedWorkbenchRetrievalResult:
    return PublishedWorkbenchRetrievalResult(
        runtime_entry_id="runtime-entry-1",
        publication_id="pub-1",
        project_id="project-1",
        source_document_ref="doc-1",
        fact_id="fact-1",
        curation_item_ref=None,
        claim="Claim one",
        possible_questions=("Question one?",),
        exclusion_scope=None,
        evidence_block="Evidence one",
        source_claim_refs=("claim-1",),
        embedding_text="Embedding text one",
        score=1.0,
        rank=1,
        source_ref=PublishedWorkbenchRetrievalSourceRef(
            workflow_run_id=None,
            source_document_ref="doc-1",
            curation_item_ref=None,
            source_claim_refs=("claim-1",),
        ),
    )


def _adjudication_input() -> WorkbenchRagEvalAdjudicationPlanningInput:
    return WorkbenchRagEvalAdjudicationPlanningInput(
        run_id="run-1",
        project_id="project-1",
        question_id="question-1",
        question="Question one?",
        evaluation_role=WorkbenchRagEvalQuestionRole.PROMOTION_POOL,
        promotion_eligible=True,
        ambiguity_risk=WorkbenchRagEvalQuestionAmbiguityRisk.LOW,
        outcome_id="outcome-1",
        classification=WorkbenchRagEvalRetrievalClassification.MISS,
        expected_runtime_entry_id="runtime-entry-1",
        expected_fact_id="fact-1",
        expected_rank=None,
        expected_score=None,
        best_competitor_runtime_entry_id=None,
        best_competitor_fact_id=None,
        best_competitor_score=None,
        score_margin=None,
        target_claim="Claim one",
        target_possible_questions=("Question one?",),
        target_exclusion_scope=None,
        target_evidence_block="Evidence one",
        retrieved=(
            WorkbenchRagEvalAdjudicationRetrievedClaimSnapshot(
                rank=1,
                runtime_entry_id="runtime-entry-2",
                fact_id="fact-2",
                claim="Wrong claim",
                score=0.9,
            ),
        ),
    )


async def _assert_groq_executor_accepts_dispatch_payload(
    dispatch_payload: dict[str, object],
) -> None:
    transport = FakeGroqTransport()
    result = await GroqDispatchExecutor(
        transport=transport,
        model_profiles=build_groq_free_plan_model_profiles(),
    ).execute_dispatch(
        LlmDispatchExecutionInput(
            attempt_id="attempt-1",
            work_item_id="work-1",
            attempt_number=1,
            dispatch_payload=dispatch_payload,
            started_at=_started_at(),
        )
    )

    assert result.status is LlmDispatchExecutionStatus.SUCCEEDED
    assert transport.payloads


@dataclass(slots=True)
class RecordingDispatchPreparationBuilder:
    profile: LlmTaskCapacityProfile
    account_capacities: tuple[LlmProviderAccountCapacity, ...]
    profile_due_work_item_counts: list[int] = field(default_factory=list)
    account_model_refs: list[str] = field(default_factory=list)

    def build_profile_from_due_work_items(
        self,
        due_work_items: tuple[object, ...],
    ) -> LlmTaskCapacityProfile:
        self.profile_due_work_item_counts.append(len(due_work_items))
        return self.profile

    def build_account_capacities(
        self,
        *,
        active_model_ref: str,
        provider_account_refs: tuple[str, ...],
        model_profiles: tuple[object, ...],
    ) -> tuple[LlmProviderAccountCapacity, ...]:
        self.account_model_refs.append(active_model_ref)
        return self.account_capacities


def _status_priority(status: str) -> int:
    priority_by_status = {
        WorkItemStatus.RETRYABLE_FAILED.value: 0,
        WorkItemStatus.READY.value: 1,
    }
    return priority_by_status.get(status, 3)


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("expected datetime")
    return value


@pytest.mark.asyncio
async def test_commits_lease_and_attempt_start_in_one_transaction() -> None:
    connection = _connection_with_due_items(2)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(_command())

    assert len(connection.transactions) == 1
    assert connection.transactions[0].entered is True
    assert connection.transactions[0].committed is True
    assert connection.transactions[0].rolled_back is False
    assert pool.released == [connection]

    assert connection.work_items["work-1"]["status"] == "leased"
    assert connection.work_items["work-2"]["status"] == "ready"
    assert len(connection.attempts) == 1
    assert len(connection.dispatches) == 1
    assert len(result.lease_result.leased) == 1
    assert len(result.attempt_result.started_attempts) == 1


@pytest.mark.asyncio
async def test_prepare_logs_capacity_snapshot_and_insufficient_tpm_rejection() -> None:
    connection = _connection_with_due_items(1)
    connection.capacity_observations.append(
        {
            "provider": "groq",
            "account_ref": "org-1",
            "model_ref": "qwen/qwen3.6-27b",
            "remaining_minute_requests": 2,
            "remaining_minute_tokens": None,
            "remaining_daily_requests": 10,
            "remaining_daily_tokens": 50_000,
            "minute_reset_at": None,
            "daily_reset_at": None,
            "actual_prompt_tokens": 3008,
            "actual_completion_tokens": 4323,
            "actual_total_tokens": 7331,
            "outcome_class": "succeeded",
            "observed_at": _now() - timedelta(seconds=5),
        }
    )
    connection.capacity_reservations.append(
        {
            "attempt_id": "attempt-active",
            "provider": "groq",
            "account_ref": "org-1",
            "model_ref": "qwen/qwen3.6-27b",
            "reserved_requests": 1,
            "reserved_tokens": 6_000,
            "status": "active",
            "expires_at": _lease_expires_at(),
            "created_at": _started_at(),
        }
    )

    with capture_logs() as logs:
        result = await _runner(FakePool(connection=connection)).execute(
            _command(
                account_capacities=(
                    _account(
                        minute_requests=3,
                        minute_tokens=7_000,
                    ),
                ),
                requested_items=1,
            )
        )

    assert len(result.attempt_result.started_attempts) == 0
    snapshot = _event(logs, "llm_capacity_account_snapshot")
    assert snapshot["observed_remaining_minute_tokens"] is None
    assert snapshot["minute_tokens_source"] == "provider_observation_null_fallback"
    assert snapshot["active_reserved_tokens"] == 6_000
    assert snapshot["effective_remaining_minute_tokens"] == 1_000
    assert "latest_observation_attempt_id" not in snapshot
    assert "active_reservation_attempt_ids" not in snapshot
    assert "active_reservation_count" not in snapshot
    assert "prepare_command_id" not in snapshot
    assert "workflow_run_id" not in snapshot

    candidate = _event(logs, "llm_capacity_candidate_evaluated")
    assert candidate["admitted"] is False
    assert candidate["rejection_reason"] == "insufficient_minute_tokens"
    assert candidate["remaining_tokens_before"] == 1_000
    latest_observation_reads = [
        query
        for query in connection.fetch_queries
        if "llm_attempt_capacity_observations" in query and "DISTINCT ON" in query
    ]
    assert len(latest_observation_reads) == 1


@pytest.mark.asyncio
async def test_prepare_logs_claim_builder_correlation_when_context_is_provided() -> (
    None
):
    connection = _connection_with_due_items(1)

    with capture_logs() as logs:
        result = await _runner(FakePool(connection=connection)).execute(
            _command(
                requested_items=1,
                correlation_context={
                    "prepare_command_id": "cmd-prepare-1",
                    "workflow_run_id": "workflow-1",
                    "causation_dispatch_attempt_id": "attempt-source-1",
                },
            )
        )

    assert len(result.attempt_result.started_attempts) == 1
    snapshot = _event(logs, "llm_capacity_account_snapshot")
    assert snapshot["prepare_command_id"] == "cmd-prepare-1"
    assert snapshot["workflow_run_id"] == "workflow-1"

    candidate = _event(logs, "llm_capacity_candidate_evaluated")
    assert candidate["prepare_command_id"] == "cmd-prepare-1"
    assert candidate["workflow_run_id"] == "workflow-1"

    reservation = _event(logs, "llm_capacity_reservation_created")
    assert reservation["prepare_command_id"] == "cmd-prepare-1"
    assert reservation["workflow_run_id"] == "workflow-1"


@pytest.mark.asyncio
async def test_claim_builder_workflow_run_id_reaches_groq_executor_logs() -> None:
    schedule_payload = _claim_builder_schedule_payload(workflow_run_id="workflow-123")
    connection = FakeConnection()
    connection.work_items["work-claim-1"] = _work_item_row("work-claim-1", ordinal=1)
    connection.schedules["work-claim-1"] = schedule_payload

    prepare_result = await _runner(FakePool(connection=connection)).execute(
        _command(requested_items=1)
    )

    assert len(prepare_result.attempt_result.started_attempts) == 1
    dispatch = next(iter(connection.dispatches.values()))
    dispatch_payload = dispatch["dispatch_payload"]
    assert dispatch_payload["schedule_payload"]["workflow_run_id"] == "workflow-123"

    transport = FakeGroqTransport()
    executor = GroqDispatchExecutor(
        transport=transport,
        model_profiles=build_groq_free_plan_model_profiles(),
    )

    with capture_logs() as logs:
        await executor.execute_dispatch(
            LlmDispatchExecutionInput(
                attempt_id=str(dispatch["attempt_id"]),
                work_item_id=str(dispatch["work_item_id"]),
                attempt_number=int(dispatch["attempt_number"]),
                dispatch_payload=dispatch_payload,
                started_at=_started_at(),
            )
        )

    request_started = _event(logs, "llm_groq_request_started")
    response_received = _event(logs, "llm_groq_response_received")
    assert request_started["workflow_run_id"] == "workflow-123"
    assert response_received["workflow_run_id"] == "workflow-123"
    assert transport.payloads
    assert "workflow_run_id" not in transport.payloads[0]


@pytest.mark.asyncio
async def test_prepare_does_not_account_for_finalized_reservation_when_observation_is_absent() -> (
    None
):
    """Unit characterization of admission state, not concurrent PostgreSQL timing."""

    connection = _connection_with_due_items(1)
    connection.capacity_reservations.append(
        {
            "attempt_id": "attempt-finalized-before-observation",
            "provider": "groq",
            "account_ref": "org-1",
            "model_ref": "qwen/qwen3.6-27b",
            "reserved_requests": 1,
            "reserved_tokens": 6_500,
            "status": "committed",
            "expires_at": _lease_expires_at(),
            "created_at": _started_at(),
        }
    )

    result = await _runner(FakePool(connection=connection)).execute(
        _command(
            account_capacities=(
                _account(
                    minute_requests=1,
                    minute_tokens=7_000,
                ),
            ),
            requested_items=1,
        )
    )

    assert len(result.attempt_result.started_attempts) == 1
    assert len(connection.dispatches) == 1
    assert len(connection.capacity_observations) == 0


@pytest.mark.asyncio
async def test_prepare_uses_work_kind_specific_dispatch_preparation_builder() -> None:
    rag_eval_work_kind = WorkKind("workbench_rag_eval.question_generation")
    connection = _connection_with_due_items(1)
    connection.work_items["work-1"]["work_kind"] = rag_eval_work_kind.value
    pool = FakePool(connection=connection)
    rag_eval_builder = RecordingDispatchPreparationBuilder(
        profile=LlmTaskCapacityProfile(
            profile_id="rag-eval-qgen",
            estimated_prompt_tokens=1200,
            estimated_completion_tokens=800,
            estimated_requests=1,
        ),
        account_capacities=(
            _account(
                account_ref="rag-eval-org-1",
                minute_requests=1,
                minute_tokens=5000,
                daily_requests=10,
                daily_tokens=5000,
            ),
        ),
    )
    runner = PrepareLlmDispatchBatch(
        pool=pool,
        capacity_policy=CapacityAdmissionPolicy(),
        active_model_capacity_selector=SelectActiveLlmModelCapacity(
            projector=ProjectLlmCapacityToCapacityRuntime(),
        ),
        route_catalog=default_groq_llm_model_route_catalog(),
        dispatch_preparation_builder_registry=DispatchPreparationBuilderRegistry(
            builders_by_work_kind={rag_eval_work_kind: rag_eval_builder},
        ),
    )

    result = await runner.execute(
        _command(
            work_kind=rag_eval_work_kind,
            account_capacities=(),
            requested_items=1,
        ),
    )

    assert len(result.attempt_result.started_attempts) == 1
    assert rag_eval_builder.profile_due_work_item_counts == [1]
    assert rag_eval_builder.account_model_refs == ["qwen/qwen3.6-27b"]
    dispatch = next(iter(connection.dispatches.values()))
    assert dispatch["llm_allocation_payload"]["account_ref"] == "rag-eval-org-1"
    assert (
        dispatch["dispatch_payload"]["schedule_payload"]["llm_capacity_estimate"][
            "required_window_tokens"
        ]
        == _profile().required_window_tokens
    )


@pytest.mark.asyncio
async def test_rag_eval_question_generation_preparation_persists_groq_parseable_contract() -> (
    None
):
    plan = WorkbenchRagEvalQuestionGenerationWorkPlanner(
        prompt_version="prompt-v1",
        generation_model_profile=model_budget_profile_for_ref("qwen/qwen3.6-27b"),
    ).plan(
        workflow_run_id="run-1",
        project_id="project-1",
        entries=(_rag_eval_entry(),),
        provider_messages_by_runtime_entry_id={
            "runtime-entry-1": (
                {"role": "system", "content": "Generate eval questions."},
                {"role": "user", "content": "Claim one with evidence."},
            )
        },
    )[0]
    connection = _rag_eval_connection_with_plan(
        plan.work_item_id,
        work_kind=WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
        schedule_payload=dict(plan.payload),
    )

    result = await _rag_eval_runner(FakePool(connection=connection)).execute(
        _command(
            work_kind=WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
            account_capacities=(),
            requested_items=1,
        )
    )

    assert len(result.attempt_result.started_attempts) == 1
    dispatch = next(iter(connection.dispatches.values()))
    dispatch_payload = dispatch["dispatch_payload"]
    assert isinstance(dispatch_payload, dict)
    estimate = dispatch_payload["schedule_payload"]["llm_capacity_estimate"]
    assert estimate["budget_contract_version"] == "v3"
    assert estimate["model_tpm_limit"] == 8_000
    await _assert_groq_executor_accepts_dispatch_payload(dispatch_payload)


@pytest.mark.asyncio
async def test_rag_eval_adjudication_preparation_persists_groq_parseable_contract() -> (
    None
):
    plan = WorkbenchRagEvalAdjudicationWorkPlanner(
        adjudication_model_profile=model_budget_profile_for_ref("qwen/qwen3.6-27b"),
    ).plan(
        inputs=(_adjudication_input(),),
        provider_messages_by_question_id={
            "question-1": (
                {"role": "system", "content": "Adjudicate eval retrieval."},
                {"role": "user", "content": "Question one?"},
            )
        },
    )[0]
    connection = _rag_eval_connection_with_plan(
        plan.work_item_id,
        work_kind=WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
        schedule_payload=dict(plan.payload),
    )

    result = await _rag_eval_runner(FakePool(connection=connection)).execute(
        _command(
            work_kind=WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND,
            account_capacities=(),
            requested_items=1,
        )
    )

    assert len(result.attempt_result.started_attempts) == 1
    dispatch = next(iter(connection.dispatches.values()))
    dispatch_payload = dispatch["dispatch_payload"]
    assert isinstance(dispatch_payload, dict)
    estimate = dispatch_payload["schedule_payload"]["llm_capacity_estimate"]
    assert estimate["budget_contract_version"] == "v3"
    assert estimate["model_tpm_limit"] == 8_000
    await _assert_groq_executor_accepts_dispatch_payload(dispatch_payload)


@pytest.mark.asyncio
async def test_transactional_dispatch_batch_persists_qwen_reasoning_disabled() -> None:
    connection = _connection_with_due_items(1)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(_command(requested_items=1))

    assert len(result.attempt_result.started_attempts) == 1
    dispatch = next(iter(connection.dispatches.values()))
    assert dispatch["dispatch_payload"]["llm_execution_settings"] == {
        "reasoning_enabled": False,
    }
    assert (
        dispatch["dispatch_payload"]["llm_execution_settings"]["reasoning_enabled"]
        is False
    )


@pytest.mark.asyncio
async def test_rollback_if_attempt_dispatch_insert_fails() -> None:
    connection = _connection_with_due_items(2)
    connection.fail_dispatch_insert = True
    pool = FakePool(connection=connection)

    with pytest.raises(DispatchInsertError, match="dispatch insert failed"):
        await _runner(pool).execute(_command())

    assert len(connection.transactions) == 1
    assert connection.transactions[0].rolled_back is True
    assert connection.transactions[0].exit_exc_type is DispatchInsertError
    assert pool.released == [connection]
    assert connection.work_items["work-1"]["status"] == "ready"
    assert connection.work_items["work-2"]["status"] == "ready"
    assert connection.attempts == {}
    assert connection.dispatches == {}


@pytest.mark.asyncio
async def test_retry_too_large_for_one_window_does_not_block_fresh_item_on_same_pass() -> (
    None
):
    connection = FakeConnection()

    retry_row = _work_item_row("work-retry-large", ordinal=1)
    retry_row["status"] = WorkItemStatus.RETRYABLE_FAILED.value
    retry_row["attempt_count"] = 1
    retry_row["next_attempt_at"] = _now() - timedelta(seconds=1)
    retry_row["last_error_kind"] = "minute_capacity"

    fresh_row = _work_item_row("work-fresh-small", ordinal=2)
    fresh_row["status"] = WorkItemStatus.READY.value
    fresh_row["next_attempt_at"] = None

    connection.work_items["work-retry-large"] = retry_row
    connection.work_items["work-fresh-small"] = fresh_row
    connection.schedules["work-retry-large"] = _schedule_payload(
        source_unit_ref="unit-retry-large",
        profile=_large_input_profile(5000),
    )
    connection.schedules["work-fresh-small"] = _schedule_payload(
        source_unit_ref="unit-fresh-small",
        profile=_large_input_profile(1000),
    )

    result = await _runner(FakePool(connection=connection)).execute(
        _command(
            account_capacities=(
                _account(
                    minute_requests=1,
                    minute_tokens=4000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            requested_items=2,
        ),
    )

    assert len(result.lease_result.leased) == 1
    assert len(result.attempt_result.started_attempts) == 1
    assert connection.work_items["work-retry-large"]["status"] == (
        WorkItemStatus.RETRYABLE_FAILED.value
    )
    assert connection.work_items["work-fresh-small"]["status"] == "leased"
    assert {
        str(dispatch["work_item_id"]) for dispatch in connection.dispatches.values()
    } == {"work-fresh-small"}


@pytest.mark.asyncio
async def test_retry_strategy_prioritizes_retry_and_fills_with_fresh_work() -> None:
    connection = FakeConnection()

    retry_row = _work_item_row("work-retry", ordinal=1)
    retry_row["status"] = WorkItemStatus.RETRYABLE_FAILED.value
    retry_row["attempt_count"] = 1
    retry_row["next_attempt_at"] = _now() - timedelta(seconds=1)
    retry_row["last_error_kind"] = "validation_failed"

    fresh_row = _work_item_row("work-fresh", ordinal=2)
    fresh_row["status"] = WorkItemStatus.READY.value
    fresh_row["next_attempt_at"] = None

    connection.work_items["work-retry"] = retry_row
    connection.work_items["work-fresh"] = fresh_row
    connection.schedules["work-retry"] = _schedule_payload(
        source_unit_ref="unit-retry",
        profile=_large_input_profile(1000),
    )
    connection.schedules["work-fresh"] = _schedule_payload(
        source_unit_ref="unit-fresh",
        profile=_large_input_profile(1000),
    )

    result = await _runner(FakePool(connection=connection)).execute(
        _command(
            dispatch_preparation_strategy="SAME_MODEL",
            account_capacities=(
                _account(
                    account_ref="org-1",
                    minute_requests=2,
                    minute_tokens=4000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
                _account(
                    account_ref="org-2",
                    minute_requests=2,
                    minute_tokens=4000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            requested_items=2,
        ),
    )

    assert len(result.lease_result.leased) == 2
    assert len(result.attempt_result.started_attempts) == 2
    assert connection.work_items["work-retry"]["status"] == "leased"
    assert connection.work_items["work-fresh"]["status"] == "leased"
    assert {
        str(dispatch["work_item_id"]) for dispatch in connection.dispatches.values()
    } == {"work-retry", "work-fresh"}


@pytest.mark.asyncio
async def test_retryable_status_without_retry_strategy_does_not_block_fresh_admission() -> (
    None
):
    connection = FakeConnection()

    retry_row = _work_item_row("work-retry-large", ordinal=1)
    retry_row["status"] = WorkItemStatus.RETRYABLE_FAILED.value
    retry_row["attempt_count"] = 1
    retry_row["next_attempt_at"] = _now() - timedelta(seconds=1)
    retry_row["last_error_kind"] = "minute_capacity"

    fresh_row = _work_item_row("work-fresh-small", ordinal=2)
    fresh_row["status"] = WorkItemStatus.READY.value
    fresh_row["next_attempt_at"] = None

    connection.work_items["work-retry-large"] = retry_row
    connection.work_items["work-fresh-small"] = fresh_row
    connection.schedules["work-retry-large"] = _schedule_payload(
        source_unit_ref="unit-retry-large",
        profile=_large_input_profile(5000),
    )
    connection.schedules["work-fresh-small"] = _schedule_payload(
        source_unit_ref="unit-fresh-small",
        profile=_large_input_profile(1000),
    )

    result = await _runner(FakePool(connection=connection)).execute(
        _command(
            account_capacities=(
                _account(
                    minute_requests=1,
                    minute_tokens=4000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            requested_items=2,
        ),
    )

    assert len(result.lease_result.leased) == 1
    assert len(result.attempt_result.started_attempts) == 1
    assert connection.work_items["work-retry-large"]["status"] == (
        WorkItemStatus.RETRYABLE_FAILED.value
    )
    assert connection.work_items["work-fresh-small"]["status"] == "leased"
    assert {
        str(dispatch["work_item_id"]) for dispatch in connection.dispatches.values()
    } == {"work-fresh-small"}


@pytest.mark.asyncio
async def test_retry_plan_drives_dispatch_strategy_without_legacy_strategy() -> None:
    fallback_model_ref = "openai/gpt-oss-120b"
    connection = FakeConnection()

    retry_row = _work_item_row("work-empty-check", ordinal=1)
    retry_row["status"] = WorkItemStatus.RETRYABLE_FAILED.value
    retry_row["attempt_count"] = 2
    retry_row["next_attempt_at"] = _now() - timedelta(seconds=1)
    retry_row["last_error_kind"] = "empty_claims_retry"

    fresh_row = _work_item_row("work-fresh", ordinal=2)

    connection.work_items["work-empty-check"] = retry_row
    connection.work_items["work-fresh"] = fresh_row
    connection.schedules["work-empty-check"] = _schedule_payload(
        source_unit_ref="unit-empty-check",
    )
    connection.schedules["work-fresh"] = _schedule_payload(
        source_unit_ref="unit-fresh",
    )

    result = await _runner(FakePool(connection=connection)).execute(
        _command(
            retry_plan=WorkItemRetryPlan.RETRY_VALIDATION_CHECK_ROUTE,
            account_capacities=(
                _account(
                    account_ref="org-fallback",
                    model_ref=fallback_model_ref,
                    minute_requests=1,
                    minute_tokens=7000,
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            requested_items=2,
        ),
    )

    assert len(result.lease_result.leased) == 1
    assert len(result.attempt_result.started_attempts) == 1
    assert connection.work_items["work-empty-check"]["status"] == "leased"
    assert connection.work_items["work-fresh"]["status"] == WorkItemStatus.READY.value
    dispatch = next(iter(connection.dispatches.values()))
    assert dispatch["llm_allocation_payload"]["model_ref"] == fallback_model_ref


@pytest.mark.asyncio
async def test_legacy_deferred_item_is_not_admitted_for_prepare() -> None:
    connection = FakeConnection()

    deferred_row = _work_item_row("work-legacy-deferred", ordinal=1)
    deferred_row["status"] = WorkItemStatus.DEFERRED.value
    deferred_row["next_attempt_at"] = _now() - timedelta(seconds=1)
    deferred_row["last_error_kind"] = "legacy_capacity_wait"

    ready_row = _work_item_row("work-ready", ordinal=2)

    connection.work_items["work-legacy-deferred"] = deferred_row
    connection.work_items["work-ready"] = ready_row
    connection.schedules["work-legacy-deferred"] = _schedule_payload(
        source_unit_ref="unit-legacy-deferred",
    )
    connection.schedules["work-ready"] = _schedule_payload(
        source_unit_ref="unit-ready",
    )

    result = await _runner(FakePool(connection=connection)).execute(
        _command(requested_items=2),
    )

    assert len(result.lease_result.leased) == 1
    assert connection.work_items["work-legacy-deferred"]["status"] == (
        WorkItemStatus.DEFERRED.value
    )
    assert connection.work_items["work-ready"]["status"] == "leased"
    assert {
        str(dispatch["work_item_id"]) for dispatch in connection.dispatches.values()
    } == {"work-ready"}


@pytest.mark.asyncio
async def test_capacity_exhausted_creates_no_attempts() -> None:
    connection = _connection_with_due_items(2)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    minute_requests=0,
                    minute_tokens=0,
                    daily_requests=0,
                    daily_tokens=0,
                ),
            ),
            requested_items=2,
        ),
    )

    assert connection.transactions[0].committed is True
    assert result.lease_result.leased == ()
    assert result.attempt_result.started_attempts == ()
    assert connection.attempts == {}
    assert connection.dispatches == {}


@pytest.mark.asyncio
async def test_no_due_work_items_creates_no_attempts() -> None:
    connection = _connection_with_due_items(0)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(_command())

    assert connection.transactions[0].committed is True
    assert result.lease_result.llm_capacity_projection.max_projected_items == 0
    assert result.lease_result.leased == ()
    assert result.attempt_result.started_attempts == ()
    assert connection.attempts == {}


def test_rejects_started_at_before_now() -> None:
    with pytest.raises(ValueError, match="started_at must be >= now"):
        _command(
            now=datetime(2026, 6, 10, 12, 1, tzinfo=timezone.utc),
            started_at=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_prepare_uses_only_active_qwen_model_capacity() -> None:
    connection = _connection_with_due_items(5)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="qwen_1",
                    minute_requests=10,
                    minute_tokens=7000,
                    model_ref="qwen/qwen3.6-27b",
                ),
                _account(
                    account_ref="qwen_2",
                    minute_requests=10,
                    minute_tokens=3500,
                    model_ref="qwen/qwen3.6-27b",
                ),
                _account(
                    account_ref="fallback_openai",
                    minute_requests=10,
                    minute_tokens=35000,
                    model_ref="openai/gpt-oss-120b",
                ),
            ),
            active_model_ref="qwen/qwen3.6-27b",
            requested_items=10,
        ),
    )

    assert result.lease_result.llm_capacity_projection.max_projected_items == 2
    assert len(result.lease_result.leased) == 2
    assert len(result.attempt_result.started_attempts) == 2
    assert len(connection.dispatches) == 2
    assert {
        dispatch["llm_allocation_payload"]["model_ref"]
        for dispatch in connection.dispatches.values()
    } == {"qwen/qwen3.6-27b"}


@pytest.mark.asyncio
async def test_prepare_ignores_fallback_capacities_when_qwen_is_active() -> None:
    connection = _connection_with_due_items(10)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="qwen_1",
                    minute_requests=10,
                    minute_tokens=3500,
                    model_ref="qwen/qwen3.6-27b",
                ),
                _account(
                    account_ref="fallback_openai",
                    minute_requests=10,
                    minute_tokens=35000,
                    model_ref="openai/gpt-oss-120b",
                ),
                _account(
                    account_ref="fallback_llama",
                    minute_requests=10,
                    minute_tokens=35000,
                    model_ref="llama-3.3-70b-versatile",
                ),
            ),
            active_model_ref="qwen/qwen3.6-27b",
            requested_items=10,
        ),
    )

    assert result.lease_result.llm_capacity_projection.max_projected_items == 1
    assert len(result.attempt_result.started_attempts) == 1


@pytest.mark.asyncio
async def test_prepare_absent_active_model_starts_no_attempts() -> None:
    connection = _connection_with_due_items(5)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="qwen_1",
                    minute_requests=10,
                    minute_tokens=35000,
                    model_ref="qwen/qwen3.6-27b",
                ),
            ),
            active_model_ref="openai/gpt-oss-120b",
            requested_items=10,
        ),
    )

    assert result.lease_result.llm_capacity_projection.max_projected_items == 0
    assert result.lease_result.leased == ()
    assert result.attempt_result.started_attempts == ()
    assert connection.attempts == {}
    assert connection.dispatches == {}
    assert connection.transactions[0].committed is True


@pytest.mark.asyncio
async def test_non_primary_active_model_can_use_local_tpm_budget() -> None:
    connection = _connection_with_due_items(2)
    connection.capacity_observations.append(
        {
            "provider": "groq",
            "account_ref": "openai_1",
            "model_ref": "openai/gpt-oss-120b",
            "remaining_minute_requests": 10,
            "remaining_minute_tokens": 7000,
            "remaining_daily_requests": 100,
            "remaining_daily_tokens": 50000,
            "minute_reset_at": None,
            "daily_reset_at": None,
            "actual_prompt_tokens": 3000,
            "actual_completion_tokens": 500,
            "actual_total_tokens": 3500,
            "outcome_class": "succeeded",
            "observed_at": _now() - timedelta(seconds=30),
        }
    )
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="openai_1",
                    minute_requests=10,
                    minute_tokens=7000,
                    model_ref="openai/gpt-oss-120b",
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            active_model_ref="openai/gpt-oss-120b",
            requested_items=2,
            use_local_active_model_tpm_budget=True,
        ),
    )

    assert len(result.attempt_result.started_attempts) == 1
    assert result.lease_result.llm_capacity_projection.max_projected_items == 1
    assert {
        dispatch["llm_allocation_payload"]["model_ref"]
        for dispatch in connection.dispatches.values()
    } == {"openai/gpt-oss-120b"}


@pytest.mark.asyncio
async def test_non_primary_active_model_prefers_header_capacity_over_local_fallback() -> (
    None
):
    connection = _connection_with_due_items(1)
    connection.capacity_observations.append(
        {
            "provider": "groq",
            "account_ref": "openai_1",
            "model_ref": "openai/gpt-oss-120b",
            "remaining_minute_requests": 10,
            "remaining_minute_tokens": 7000,
            "remaining_daily_requests": 100,
            "remaining_daily_tokens": 50000,
            "minute_reset_at": None,
            "daily_reset_at": None,
            "actual_prompt_tokens": None,
            "actual_completion_tokens": None,
            "actual_total_tokens": None,
            "outcome_class": "deferred",
            "observed_at": _now() - timedelta(seconds=30),
        }
    )
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="openai_1",
                    minute_requests=10,
                    minute_tokens=7000,
                    model_ref="openai/gpt-oss-120b",
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            active_model_ref="openai/gpt-oss-120b",
            requested_items=1,
            use_local_active_model_tpm_budget=True,
        ),
    )

    assert len(result.attempt_result.started_attempts) == 1
    assert result.lease_result.llm_capacity_projection.max_projected_items == 1


@pytest.mark.asyncio
async def test_non_primary_active_model_daily_exhaustion_blocks_local_account() -> None:
    connection = _connection_with_due_items(1)
    connection.capacity_observations.append(
        {
            "provider": "groq",
            "account_ref": "openai_1",
            "model_ref": "openai/gpt-oss-120b",
            "remaining_minute_requests": 10,
            "remaining_minute_tokens": 7000,
            "remaining_daily_requests": 0,
            "remaining_daily_tokens": 50000,
            "minute_reset_at": None,
            "daily_reset_at": _now() + timedelta(hours=12),
            "actual_prompt_tokens": None,
            "actual_completion_tokens": None,
            "actual_total_tokens": None,
            "outcome_class": "deferred",
            "observed_at": _now() - timedelta(seconds=30),
        }
    )
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="openai_1",
                    minute_requests=10,
                    minute_tokens=7000,
                    model_ref="openai/gpt-oss-120b",
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            active_model_ref="openai/gpt-oss-120b",
            requested_items=1,
            use_local_active_model_tpm_budget=True,
        ),
    )

    assert result.attempt_result.started_attempts == ()
    assert result.lease_result.llm_capacity_projection.max_projected_items == 0


@pytest.mark.asyncio
async def test_prepare_resolves_fallback_strategy_to_first_automatic_fallback_model() -> (
    None
):
    catalog = default_groq_llm_model_route_catalog()
    fallback_model_ref = catalog.automatic_fallback_model_refs()[0]
    connection = _connection_with_due_items(5)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="primary",
                    model_ref=catalog.primary_model_ref(),
                    minute_requests=10,
                    minute_tokens=3500,
                ),
                _account(
                    account_ref="fallback",
                    model_ref=fallback_model_ref,
                    minute_requests=10,
                    minute_tokens=35000,
                ),
            ),
            active_model_ref=catalog.primary_model_ref(),
            dispatch_preparation_strategy="FALLBACK_MODEL_REQUIRED",
            requested_items=10,
        ),
    )

    assert len(result.attempt_result.started_attempts) == 1
    assert {
        dispatch["llm_allocation_payload"]["model_ref"]
        for dispatch in connection.dispatches.values()
    } == {fallback_model_ref}


@pytest.mark.asyncio
async def test_prepare_resolves_larger_output_strategy_to_fallback_for_now() -> None:
    catalog = default_groq_llm_model_route_catalog()
    fallback_model_ref = catalog.automatic_fallback_model_refs()[0]
    connection = _connection_with_due_items(5)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="primary",
                    model_ref=catalog.primary_model_ref(),
                    minute_requests=10,
                    minute_tokens=3500,
                ),
                _account(
                    account_ref="fallback",
                    model_ref=fallback_model_ref,
                    minute_requests=10,
                    minute_tokens=35000,
                ),
            ),
            active_model_ref=catalog.primary_model_ref(),
            dispatch_preparation_strategy="LARGER_OUTPUT_LIMIT_MODEL_REQUIRED",
            requested_items=10,
        ),
    )

    assert len(result.attempt_result.started_attempts) == 1
    assert {
        dispatch["llm_allocation_payload"]["model_ref"]
        for dispatch in connection.dispatches.values()
    } == {fallback_model_ref}


@pytest.mark.asyncio
async def test_prepare_unknown_dispatch_strategy_raises_value_error() -> None:
    connection = _connection_with_due_items(1)
    pool = FakePool(connection=connection)

    with pytest.raises(ValueError, match="unknown llm dispatch preparation strategy"):
        await _runner(pool).execute(
            _command(dispatch_preparation_strategy="NO_SUCH_STRATEGY"),
        )


@pytest.mark.asyncio
async def test_prepare_uses_input_preflight_model_ref_before_leasing() -> None:
    catalog = default_groq_llm_model_route_catalog()
    fallback_model_ref = catalog.automatic_fallback_model_refs_with_larger_input_limit(
        catalog.primary_model_ref(),
    )[0]
    large_profile = _large_input_profile(9000)
    connection = _connection_with_due_items(2, profile=large_profile)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            profile=large_profile,
            account_capacities=(
                _account(
                    account_ref="primary",
                    model_ref=catalog.primary_model_ref(),
                    minute_requests=10,
                    minute_tokens=500000,
                    daily_tokens=500000,
                ),
                _account(
                    account_ref="fallback",
                    model_ref=fallback_model_ref,
                    minute_requests=10,
                    minute_tokens=500000,
                    daily_tokens=500000,
                ),
            ),
            active_model_ref=catalog.primary_model_ref(),
            requested_items=2,
        ),
    )

    assert result.input_size_preflight_decision == "USE_LARGER_INPUT_MODEL"
    assert result.input_size_preflight_active_model_ref == fallback_model_ref
    assert len(result.attempt_result.started_attempts) == 1
    assert {
        dispatch["llm_allocation_payload"]["model_ref"]
        for dispatch in connection.dispatches.values()
    } == {fallback_model_ref}


@pytest.mark.asyncio
async def test_source_split_required_does_not_lease_normal_llm_work_item() -> None:
    catalog = default_groq_llm_model_route_catalog()
    large_profile = _large_input_profile(200000)
    connection = _connection_with_due_items(2, profile=large_profile)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            profile=large_profile,
            account_capacities=(
                _account(
                    account_ref="primary",
                    model_ref=catalog.primary_model_ref(),
                    minute_requests=10,
                    minute_tokens=1000000,
                    daily_tokens=1000000,
                ),
                _account(
                    account_ref="fallback",
                    model_ref=catalog.automatic_fallback_model_refs()[0],
                    minute_requests=10,
                    minute_tokens=1000000,
                    daily_tokens=1000000,
                ),
            ),
            active_model_ref=catalog.primary_model_ref(),
            requested_items=2,
        ),
    )

    assert result.source_split_required is True
    assert result.input_size_preflight_decision == "SOURCE_SPLIT_REQUIRED"
    assert result.affected_work_item_refs == ("work-1", "work-2")
    assert result.source_unit_refs == ("unit-1", "unit-2")
    assert result.lease_result.leased == ()
    assert result.attempt_result.started_attempts == ()
    assert connection.attempts == {}
    assert connection.dispatches == {}
    assert connection.work_items["work-1"]["status"] == "ready"
    assert connection.work_items["work-2"]["status"] == "ready"


@pytest.mark.asyncio
async def test_source_split_required_raises_when_due_payload_has_no_source_unit_ref() -> (
    None
):
    catalog = default_groq_llm_model_route_catalog()
    large_profile = _large_input_profile(200000)
    connection = _connection_with_due_items(1, profile=large_profile)
    connection.schedules["work-1"] = {
        "not_source_unit_ref": "missing",
        "llm_capacity_estimate": {
            "budget_contract_version": "v3",
            "estimator": "test_budget",
            "provider": "groq",
            "model_ref": "qwen/qwen3.6-27b",
            "model_tpm_limit": 8_000,
            "model_char_to_token_multiplier": "2.8",
            "phase": "test",
            "operation": "prepare",
            "prompt_tokens": large_profile.estimated_prompt_tokens,
            "artifact_tokens": 0,
            "input_tokens": large_profile.estimated_prompt_tokens,
            "planned_output_tokens": large_profile.estimated_completion_tokens,
            "safety_gap_tokens": 0,
            "required_window_tokens": large_profile.required_window_tokens,
        },
    }
    pool = FakePool(connection=connection)

    with pytest.raises(ValueError, match="source_unit_ref"):
        await _runner(pool).execute(
            _command(
                profile=large_profile,
                account_capacities=(
                    _account(
                        account_ref="primary",
                        model_ref=catalog.primary_model_ref(),
                        minute_requests=10,
                        minute_tokens=1000000,
                        daily_tokens=1000000,
                    ),
                    _account(
                        account_ref="fallback",
                        model_ref=catalog.automatic_fallback_model_refs()[0],
                        minute_requests=10,
                        minute_tokens=1000000,
                        daily_tokens=1000000,
                    ),
                ),
                active_model_ref=catalog.primary_model_ref(),
                requested_items=1,
            ),
        )


def test_tpm_admission_uses_required_window_tokens() -> None:
    profile = LlmTaskCapacityProfile(
        profile_id="prompt-a",
        estimated_prompt_tokens=3000,
        estimated_completion_tokens=9000,
    )
    capacity = _account(
        minute_requests=1,
        minute_tokens=3000,
        daily_requests=1,
        daily_tokens=3000,
    )

    assert capacity.max_items_for(profile) == 0


def test_groq_missing_minute_reset_uses_local_sixty_second_timer() -> None:
    observed_at = _now()
    observation = LlmAttemptCapacityObservation(
        provider="groq",
        account_ref="org-1",
        model_ref="qwen/qwen3.6-27b",
        remaining_minute_requests=60,
        remaining_minute_tokens=0,
        remaining_daily_requests=999,
        remaining_daily_tokens=50000,
        minute_reset_at=None,
        daily_reset_at=None,
        actual_prompt_tokens=3000,
        actual_completion_tokens=500,
        actual_total_tokens=3500,
        outcome_class="succeeded",
        observed_at=observed_at,
    )

    assert _observation_retry_at(
        observation=observation,
        now=observed_at + timedelta(seconds=30),
    ) == observed_at + timedelta(seconds=60)

    blocked_capacity = _capacity_from_latest_observation(
        seed_capacity=_account(
            account_ref="org-1",
            minute_requests=60,
            minute_tokens=0,
            daily_requests=999,
            daily_tokens=50000,
        ),
        observation=observation,
        profile=_profile(),
        now=observed_at + timedelta(seconds=30),
    )
    assert blocked_capacity.max_items_for(_profile()) == 0

    recovered_capacity = _capacity_from_latest_observation(
        seed_capacity=_account(
            account_ref="org-1",
            minute_requests=60,
            minute_tokens=0,
            daily_requests=999,
            daily_tokens=50000,
        ),
        observation=observation,
        profile=_profile(),
        now=observed_at + timedelta(seconds=61),
    )
    assert recovered_capacity.remaining_minute_requests == 60
    assert recovered_capacity.remaining_minute_tokens == 0
    assert recovered_capacity.max_items_for(_profile()) == 0


@pytest.mark.asyncio
async def test_prepare_skips_expensive_due_item_and_leases_later_item_that_fits_tpm() -> (
    None
):
    expensive_profile = LlmTaskCapacityProfile(
        profile_id="expensive-section",
        estimated_prompt_tokens=5000,
        estimated_completion_tokens=0,
    )
    cheap_profile = LlmTaskCapacityProfile(
        profile_id="cheap-section",
        estimated_prompt_tokens=1000,
        estimated_completion_tokens=0,
    )
    connection = _connection_with_due_items(3)
    connection.schedules["work-1"] = _schedule_payload(
        source_unit_ref="unit-1",
        profile=expensive_profile,
    )
    connection.schedules["work-2"] = _schedule_payload(
        source_unit_ref="unit-2",
        profile=cheap_profile,
    )
    connection.schedules["work-3"] = _schedule_payload(
        source_unit_ref="unit-3",
        profile=expensive_profile,
    )
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="qwen_1",
                    minute_requests=1,
                    minute_tokens=1000,
                    model_ref="qwen/qwen3.6-27b",
                    daily_requests=10,
                    daily_tokens=1000,
                ),
            ),
            active_model_ref="qwen/qwen3.6-27b",
            requested_items=3,
        ),
    )

    assert len(result.attempt_result.started_attempts) == 1
    assert result.lease_result.leased[0].leased.work_item.work_item_id == "work-2"
    assert connection.work_items["work-1"]["status"] == "ready"
    assert connection.work_items["work-2"]["status"] == "leased"
    assert connection.work_items["work-3"]["status"] == "ready"
    dispatch = next(iter(connection.dispatches.values()))
    assert dispatch["schedule_payload"]["source_unit_ref"] == "unit-2"


@pytest.mark.asyncio
async def test_prepare_allocates_retry_then_fresh_per_window() -> None:
    connection = FakeConnection()

    retry_large = _work_item_row("work-retry-large", ordinal=1)
    retry_large["status"] = WorkItemStatus.RETRYABLE_FAILED.value
    retry_large["attempt_count"] = 1
    retry_large["next_attempt_at"] = _now() - timedelta(seconds=1)

    retry_small = _work_item_row("work-retry-small", ordinal=2)
    retry_small["status"] = WorkItemStatus.RETRYABLE_FAILED.value
    retry_small["attempt_count"] = 1
    retry_small["next_attempt_at"] = _now() - timedelta(seconds=1)

    fresh_small = _work_item_row("work-fresh-small", ordinal=3)
    fresh_large = _work_item_row("work-fresh-large", ordinal=4)

    connection.work_items["work-retry-large"] = retry_large
    connection.work_items["work-retry-small"] = retry_small
    connection.work_items["work-fresh-small"] = fresh_small
    connection.work_items["work-fresh-large"] = fresh_large

    connection.schedules["work-retry-large"] = _schedule_payload(
        source_unit_ref="unit-retry-large",
        profile=_large_input_profile(5000),
    )
    connection.schedules["work-retry-small"] = _schedule_payload(
        source_unit_ref="unit-retry-small",
        profile=_large_input_profile(2500),
    )
    connection.schedules["work-fresh-small"] = _schedule_payload(
        source_unit_ref="unit-fresh-small",
        profile=_large_input_profile(1700),
    )
    connection.schedules["work-fresh-large"] = _schedule_payload(
        source_unit_ref="unit-fresh-large",
        profile=_large_input_profile(5200),
    )

    result = await _runner(FakePool(connection=connection)).execute(
        _command(
            account_capacities=(
                _account(account_ref="org-1", minute_requests=1, minute_tokens=3000),
                _account(account_ref="org-2", minute_requests=1, minute_tokens=6000),
                _account(account_ref="org-3", minute_requests=1, minute_tokens=1800),
                _account(account_ref="org-4", minute_requests=1, minute_tokens=6000),
            ),
            requested_items=4,
        ),
    )

    assert len(result.attempt_result.started_attempts) == 3
    assert {
        str(dispatch["work_item_id"]): dispatch["llm_allocation_payload"]["account_ref"]
        for dispatch in connection.dispatches.values()
    } == {
        "work-retry-small": "org-1",
        "work-retry-large": "org-2",
        "work-fresh-small": "org-4",
    }
    assert (
        connection.work_items["work-fresh-large"]["status"]
        == WorkItemStatus.READY.value
    )


@pytest.mark.asyncio
async def test_local_active_model_minute_window_uses_first_observation_reset() -> None:
    connection = _connection_with_due_items(1)
    connection.capacity_observations.extend(
        [
            {
                "provider": "groq",
                "account_ref": "openai_1",
                "model_ref": "openai/gpt-oss-120b",
                "remaining_minute_requests": None,
                "remaining_minute_tokens": None,
                "remaining_daily_requests": None,
                "remaining_daily_tokens": None,
                "minute_reset_at": None,
                "daily_reset_at": None,
                "actual_prompt_tokens": 3000,
                "actual_completion_tokens": 0,
                "actual_total_tokens": 3000,
                "outcome_class": "succeeded",
                "observed_at": _now() - timedelta(seconds=50),
            },
            {
                "provider": "groq",
                "account_ref": "openai_1",
                "model_ref": "openai/gpt-oss-120b",
                "remaining_minute_requests": None,
                "remaining_minute_tokens": None,
                "remaining_daily_requests": None,
                "remaining_daily_tokens": None,
                "minute_reset_at": None,
                "daily_reset_at": None,
                "actual_prompt_tokens": 3000,
                "actual_completion_tokens": 0,
                "actual_total_tokens": 3000,
                "outcome_class": "succeeded",
                "observed_at": _now() - timedelta(seconds=5),
            },
        ],
    )
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="openai_1",
                    minute_requests=10,
                    minute_tokens=7000,
                    model_ref="openai/gpt-oss-120b",
                    daily_requests=100,
                    daily_tokens=50000,
                ),
            ),
            active_model_ref="openai/gpt-oss-120b",
            requested_items=1,
            use_local_active_model_tpm_budget=True,
        ),
    )

    assert result.attempt_result.started_attempts == ()
    assert result.lease_result.llm_capacity_projection.max_projected_items == 0
    assert result.capacity_retry_at == _now() + timedelta(seconds=10)


@pytest.mark.asyncio
async def test_prepare_does_not_rearm_entire_batch_after_started_attempts() -> None:
    connection = _connection_with_due_items(2)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(_command())

    assert len(result.attempt_result.started_attempts) == 1
    assert result.capacity_retry_at is None


@pytest.mark.asyncio
async def test_prepare_does_not_rearm_next_batch_without_started_attempts() -> None:
    connection = _connection_with_due_items(2)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    minute_requests=0,
                    minute_tokens=0,
                    daily_requests=0,
                    daily_tokens=0,
                ),
            ),
            requested_items=2,
        ),
    )

    assert result.attempt_result.started_attempts == ()
    assert result.capacity_retry_at is None


@pytest.mark.asyncio
async def test_prepare_subtracts_active_route_reservations_before_admission() -> None:
    connection = _connection_with_due_items(2)
    connection.capacity_reservations.append(
        {
            "attempt_id": "other-work:attempt:1",
            "provider": "groq",
            "account_ref": "qwen_1",
            "model_ref": "qwen/qwen3.6-27b",
            "reserved_requests": 1,
            "reserved_tokens": 3500,
            "status": "active",
            "expires_at": _now() + timedelta(seconds=60),
            "created_at": _now() - timedelta(seconds=1),
        }
    )
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="qwen_1",
                    minute_requests=2,
                    minute_tokens=7000,
                    daily_requests=10,
                    daily_tokens=7000,
                ),
            ),
            requested_items=2,
        ),
    )

    assert len(result.attempt_result.started_attempts) == 1
    assert len(connection.capacity_reservations) == 2


@pytest.mark.asyncio
async def test_prepare_no_due_records_returns_idle_result() -> None:
    connection = _connection_with_due_items(0)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(_command())

    assert result.attempt_result.started_attempts == ()
    assert result.lease_result.leased == ()
    assert result.capacity_retry_at is None
    assert result.input_size_preflight_reason == "no due work items"
