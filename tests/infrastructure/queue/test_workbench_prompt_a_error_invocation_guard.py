from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_section_work_item_processor_service import (
    ProcessLeasedClaimObservationsCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DocumentSectionStatus,
    DomainInvariantError,
    FactRegistry,
    FactRegistryStatus,
    RegistrySnapshot,
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
from src.infrastructure.queue.handlers.workbench_parallel_processing import (
    DefaultClaimObservationsRunner,
)


@dataclass(slots=True)
class FakeRepository:
    persisted_error_count: int = 0

    async def get_fact_registry_for_run(self, **kwargs: object) -> FactRegistry | None:
        now = datetime(2026, 6, 4, tzinfo=timezone.utc)
        return FactRegistry(
            registry_id="registry-1",
            project_id="project-1",
            document_id="document-1",
            processing_run_id="run-1",
            status=FactRegistryStatus.BUILDING,
            version=1,
            created_at=now,
            updated_at=now,
        )

    async def get_latest_registry_snapshot(
        self, **kwargs: object
    ) -> RegistrySnapshot | None:
        return RegistrySnapshot(
            snapshot_id="snapshot-1",
            registry_id="registry-1",
            processing_run_id="run-1",
            project_id="project-1",
            document_id="document-1",
            after_section_id=None,
            after_node_run_id="node-run-0",
            sequence_number=1,
            entries_payload={"contract": "fact_registry", "fact_registry": {}},
            relations_payload={
                "contract": "fact_registry_relations",
                "fact_relations": [],
            },
            entry_count=0,
            relation_count=0,
            claim_observation_count=0,
            update_count=0,
            created_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
        )

    async def create_processing_node_run(self, node_run: object) -> None:
        return None

    async def create_processing_node_artifact(self, artifact: object) -> None:
        return None

    async def sync_processing_run_llm_usage_totals(self, **kwargs: object) -> None:
        return None

    async def persist_claim_observations_generation_error_lifecycle(
        self,
        **kwargs: object,
    ) -> None:
        self.persisted_error_count += 1


@dataclass(slots=True)
class RaisingGenerator:
    exc: Exception

    async def generate_findings(self, **kwargs: object) -> object:
        raise self.exc


@dataclass(slots=True)
class FakePersistenceService:
    calls: list[object] = field(default_factory=list)

    async def persist_claim_observations_generation_error(
        self, command: object
    ) -> object:
        self.calls.append(command)
        return object()

    async def persist_claim_observations(self, command: object) -> object:
        raise AssertionError("success persistence must not be called")


def _section() -> DocumentSection:
    return DocumentSection(
        section_id="section-1",
        document_id="document-1",
        project_id="project-1",
        section_index=0,
        section_key="section-1",
        heading_path=(),
        title="Section",
        raw_text="raw",
        normalized_text="normalized",
        source_refs=(),
        source_chunk_indexes=(),
        status=DocumentSectionStatus.PROCESSED,
        metadata={},
    )


def _queue_item() -> SectionBatchQueueItem:
    return SectionBatchQueueItem(
        queue_item_id="queue-1",
        batch_plan_id="plan-1",
        processing_run_id="run-1",
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        section_key="section-1",
        section_index=0,
        lane_id="lane-1",
        lane_index=0,
        observed_registry_snapshot_id="snapshot-1",
        observed_registry_snapshot_sequence=1,
        status=SectionBatchQueueItemStatus.LEASED,
        claimed_by_worker_id="worker-1",
        lease_expires_at=datetime(2026, 6, 4, 1, tzinfo=timezone.utc),
        claim_observations_node_run_id=None,
        registry_application_queue_item_id=None,
        error_kind=None,
        attempt_count=1,
        created_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
    )


def _failed_invocation() -> LlmJsonInvocationResult:
    return LlmJsonInvocationResult(
        status=LlmInvocationStatus.INVALID_JSON,
        parsed_json=None,
        raw_text="not-json",
        token_usage=LlmTokenUsage(prompt_tokens=1, completion_tokens=1),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model="llama-3.1-8b-instant",
                api_key_slot="slot-1",
                attempt_index=0,
                status=LlmRouteAttemptStatus.FAILED,
                error_kind="invalid_json",
            ),
        ),
        failure=LlmInvocationFailure(
            status=LlmInvocationStatus.INVALID_JSON,
            error_kind="invalid_json",
            user_message="LLM returned invalid JSON.",
            internal_message="bad json",
        ),
    )


@pytest.mark.asyncio
async def test_prompt_a_runner_does_not_treat_string_exception_arg_as_invocation() -> (
    None
):
    persistence = FakePersistenceService()
    runner = DefaultClaimObservationsRunner(
        repository=FakeRepository(),
        generator=RaisingGenerator(DomainInvariantError("ordinary parser failure")),
        persistence_service=persistence,
    )

    with pytest.raises(DomainInvariantError, match="ordinary parser failure"):
        await runner.process_leased_claim_observations(
            ProcessLeasedClaimObservationsCommand(
                queue_item=_queue_item(),
                section=_section(),
            )
        )

    assert persistence.calls == []


@pytest.mark.asyncio
async def test_prompt_a_runner_persists_error_only_when_exception_contains_invocation() -> (
    None
):
    invocation = _failed_invocation()
    persistence = FakePersistenceService()
    runner = DefaultClaimObservationsRunner(
        repository=FakeRepository(),
        generator=RaisingGenerator(RuntimeError(invocation)),
        persistence_service=persistence,
    )

    with pytest.raises(RuntimeError):
        await runner.process_leased_claim_observations(
            ProcessLeasedClaimObservationsCommand(
                queue_item=_queue_item(),
                section=_section(),
            )
        )

    assert len(persistence.calls) == 1
    assert persistence.calls[0].invocation is invocation
