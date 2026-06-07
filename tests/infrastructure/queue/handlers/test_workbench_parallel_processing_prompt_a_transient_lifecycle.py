from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_claim_observations_service import (
    ProcessClaimObservationsCommand,
    ProcessClaimObservationsGenerationErrorCommand,
)
from src.application.services.faq_workbench_section_work_item_processor_service import (
    ProcessLeasedClaimObservationsCommand,
)
from src.domain.project_plane.knowledge_workbench import JsonValue
from src.domain.project_plane.knowledge_workbench.documents import (
    DocumentSection,
    DocumentSectionStatus,
)
from src.domain.project_plane.knowledge_workbench.section_batch_queue import (
    SectionBatchQueueItem,
    SectionBatchQueueItemStatus,
)
from src.domain.project_plane.llm_routing import (
    LlmInvocationFailure,
    LlmInvocationStatus,
    LlmJsonInvocationResult,
    LlmRouteAttempt,
    LlmRouteAttemptStatus,
    LlmTokenUsage,
)
from src.infrastructure.llm.faq_workbench_claim_observations_generator import (
    FaqWorkbenchClaimObservationsInvocationError,
)
from src.infrastructure.queue.handlers.workbench_parallel_processing import (
    DefaultClaimObservationsRunner,
)


@dataclass(frozen=True, slots=True)
class FakeSnapshot:
    entries_payload: JsonValue


@dataclass(slots=True)
class FakeRepository:
    async def get_fact_registry_for_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> object:
        return object()

    async def get_latest_registry_snapshot(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> FakeSnapshot:
        return FakeSnapshot(entries_payload={"fact_registry": {}})


@dataclass(slots=True)
class FakePromptAGenerator:
    async def generate_findings(
        self,
        *,
        section: DocumentSection,
        registry_snapshot: JsonValue,
    ) -> object:
        raise _PromptAGenerationErrorWithInvocation(_rate_limited_result())


@dataclass(slots=True)
class FakePersistenceService:
    generation_error_calls: int = 0

    async def persist_claim_observations(
        self,
        command: ProcessClaimObservationsCommand,
    ) -> object:
        raise AssertionError("transient Prompt A failure must not persist success")

    async def persist_claim_observations_generation_error(
        self,
        command: ProcessClaimObservationsGenerationErrorCommand,
    ) -> object:
        self.generation_error_calls += 1
        raise AssertionError(
            "transient Prompt A failure must not write Workbench lifecycle pause"
        )


class _PromptAGenerationErrorWithInvocation(
    FaqWorkbenchClaimObservationsInvocationError
):
    def __init__(self, result: LlmJsonInvocationResult) -> None:
        super().__init__(result)
        self.args = (result,)


def _utc() -> datetime:
    return datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)


def _section() -> DocumentSection:
    return DocumentSection(
        section_id="section-1",
        document_id="document-1",
        project_id="project-1",
        section_index=1,
        section_key="section-1",
        heading_path=("Section",),
        title="Section",
        raw_text="Система хранит историю диалогов.",
        normalized_text="Система хранит историю диалогов.",
        source_refs=("source-ref-1",),
        source_chunk_indexes=(0,),
        status=DocumentSectionStatus.PENDING,
        parent_section_id=None,
        metadata={},
    )


def _queue_item() -> SectionBatchQueueItem:
    return SectionBatchQueueItem(
        queue_item_id="queue-item-1",
        batch_plan_id="batch-plan-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        section_key="section-1",
        section_index=1,
        lane_id="section-lane-1",
        lane_index=0,
        observed_registry_snapshot_id="snapshot-1",
        observed_registry_snapshot_sequence=1,
        status=SectionBatchQueueItemStatus.LEASED,
        claimed_by_worker_id="workbench-parallel-section-1-1",
        lease_expires_at=_utc(),
        claim_observations_node_run_id=None,
        registry_application_queue_item_id=None,
        error_kind=None,
        attempt_count=1,
        created_at=_utc(),
        updated_at=_utc(),
    )


def _rate_limited_result() -> LlmJsonInvocationResult:
    status = LlmInvocationStatus.RATE_LIMITED
    return LlmJsonInvocationResult(
        status=status,
        parsed_json=None,
        raw_text="",
        token_usage=LlmTokenUsage(prompt_tokens=10, completion_tokens=0),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model="qwen/qwen3-32b",
                api_key_slot="1/4",
                attempt_index=0,
                status=LlmRouteAttemptStatus.FAILED,
                error_kind="rate_limited",
                cooldown_seconds=7,
            ),
        ),
        failure=LlmInvocationFailure(
            status=status,
            error_kind="rate_limited",
            user_message="LLM provider is temporarily rate limited.",
            internal_message="rate limit",
            cooldown_seconds=7,
        ),
    )


@pytest.mark.asyncio
async def test_prompt_a_transient_invocation_does_not_write_workbench_pause_lifecycle() -> (
    None
):
    persistence = FakePersistenceService()
    runner = DefaultClaimObservationsRunner(
        repository=FakeRepository(),
        generator=FakePromptAGenerator(),
        persistence_service=persistence,
    )

    with pytest.raises(FaqWorkbenchClaimObservationsInvocationError):
        await runner.process_leased_claim_observations(
            ProcessLeasedClaimObservationsCommand(
                queue_item=_queue_item(),
                section=_section(),
            )
        )

    assert persistence.generation_error_calls == 0
