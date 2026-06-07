from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_claim_observations_service import (
    ProcessClaimObservationsCommand,
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
    _split_oversized_section_text,
)


@dataclass(frozen=True, slots=True)
class FakeSnapshot:
    entries_payload: JsonValue


@dataclass(frozen=True, slots=True)
class FakeNodeRun:
    node_run_id: str


@dataclass(frozen=True, slots=True)
class FakePersistedResult:
    node_run: FakeNodeRun
    claim_observation_ids: tuple[str, ...]


@dataclass(slots=True)
class FakeRepository:
    upserted_sections: list[DocumentSection] = field(default_factory=list)
    updated_items: list[SectionBatchQueueItem] = field(default_factory=list)

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

    async def upsert_document_sections(
        self,
        sections: tuple[DocumentSection, ...],
    ) -> None:
        self.upserted_sections.extend(sections)

    async def update_section_batch_queue_item(
        self,
        item: SectionBatchQueueItem,
    ) -> None:
        self.updated_items.append(item)


@dataclass(slots=True)
class FakeGenerator:
    calls: int = 0

    async def generate_findings(
        self,
        *,
        section: DocumentSection,
        registry_snapshot: JsonValue,
    ) -> object:
        self.calls += 1
        raise FaqWorkbenchClaimObservationsInvocationError(_too_large_result())


@dataclass(slots=True)
class FakePersistenceService:
    commands: list[ProcessClaimObservationsCommand] = field(default_factory=list)

    async def persist_claim_observations(
        self,
        command: ProcessClaimObservationsCommand,
    ) -> FakePersistedResult:
        self.commands.append(command)
        return FakePersistedResult(
            node_run=FakeNodeRun(node_run_id="split-parent-node-run-1"),
            claim_observation_ids=(),
        )

    async def persist_claim_observations_generation_error(
        self,
        command: object,
    ) -> object:
        raise AssertionError(
            "oversized split must not persist a failed lifecycle error"
        )


def _utc() -> datetime:
    return datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)


def _section(raw_text: str) -> DocumentSection:
    return DocumentSection(
        section_id="section-parent",
        document_id="document-1",
        project_id="project-1",
        section_index=7,
        section_key="section-parent",
        heading_path=("Parent",),
        title="Parent",
        raw_text=raw_text,
        normalized_text=raw_text,
        source_refs=("source-ref-1",),
        source_chunk_indexes=(0,),
        status=DocumentSectionStatus.PENDING,
        parent_section_id=None,
        metadata={"source": "test"},
    )


def _queue_item() -> SectionBatchQueueItem:
    return SectionBatchQueueItem(
        queue_item_id="queue-parent",
        batch_plan_id="batch-plan-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        section_id="section-parent",
        section_key="section-parent",
        section_index=7,
        lane_id="section-lane-1",
        lane_index=3,
        observed_registry_snapshot_id="snapshot-1",
        observed_registry_snapshot_sequence=1,
        status=SectionBatchQueueItemStatus.LEASED,
        claimed_by_worker_id="workbench-parallel-section-1-4",
        lease_expires_at=_utc(),
        claim_observations_node_run_id=None,
        registry_application_queue_item_id=None,
        error_kind=None,
        attempt_count=1,
        created_at=_utc(),
        updated_at=_utc(),
    )


def _too_large_result() -> LlmJsonInvocationResult:
    status = LlmInvocationStatus.REQUEST_TOO_LARGE
    return LlmJsonInvocationResult(
        status=status,
        parsed_json=None,
        raw_text="",
        token_usage=LlmTokenUsage(prompt_tokens=10, completion_tokens=0),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model="qwen/qwen3-32b",
                api_key_slot="4/4",
                attempt_index=0,
                status=LlmRouteAttemptStatus.FAILED,
                error_kind="request_too_large",
            ),
            LlmRouteAttempt(
                provider_id="groq",
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                api_key_slot="4/4",
                attempt_index=1,
                status=LlmRouteAttemptStatus.FAILED,
                error_kind="request_too_large",
            ),
        ),
        failure=LlmInvocationFailure(
            status=status,
            error_kind="prompt_a_fallback_exhausted_request_too_large",
            user_message="Prompt A section is too large for every configured fallback model.",
            internal_message="Prompt A fallback chain exhausted; section split is required.",
        ),
    )


def test_oversized_split_preserves_text_without_loss() -> None:
    raw_text = (
        "## A\n\n"
        + ("Первый смысловой блок. " * 400)
        + "\n\n## B\n\n"
        + ("Второй смысловой блок. " * 400)
    )

    chunks = _split_oversized_section_text(raw_text, target_chars=3_000)

    assert len(chunks) >= 2
    assert "".join(chunks) == raw_text


@pytest.mark.asyncio
async def test_prompt_a_too_large_exhaustion_creates_child_sections_and_ready_queue_items() -> (
    None
):
    raw_text = (
        "## A\n\n"
        + ("Первый смысловой блок. " * 400)
        + "\n\n## B\n\n"
        + ("Второй смысловой блок. " * 400)
    )
    repository = FakeRepository()
    generator = FakeGenerator()
    persistence_service = FakePersistenceService()
    runner = DefaultClaimObservationsRunner(
        repository=repository,
        generator=generator,
        persistence_service=persistence_service,
    )

    result = await runner.process_leased_claim_observations(
        ProcessLeasedClaimObservationsCommand(
            queue_item=_queue_item(),
            section=_section(raw_text),
        )
    )

    assert generator.calls == 1
    assert result.claim_observations_node_run_id == "split-parent-node-run-1"
    assert result.claim_input_refs == ()

    assert len(repository.upserted_sections) >= 2
    assert (
        "".join(section.raw_text for section in repository.upserted_sections)
        == raw_text
    )
    assert {section.parent_section_id for section in repository.upserted_sections} == {
        "section-parent"
    }
    assert all(
        section.status is DocumentSectionStatus.PENDING
        for section in repository.upserted_sections
    )
    assert all(
        section.metadata["split_reason"]
        == "prompt_a_fallback_exhausted_request_too_large"
        for section in repository.upserted_sections
    )

    assert len(repository.updated_items) == len(repository.upserted_sections)
    assert all(
        item.status is SectionBatchQueueItemStatus.READY
        for item in repository.updated_items
    )
    assert all(item.claimed_by_worker_id is None for item in repository.updated_items)
    assert all(item.lease_expires_at is None for item in repository.updated_items)
    assert {item.section_id for item in repository.updated_items} == {
        section.section_id for section in repository.upserted_sections
    }

    assert len(persistence_service.commands) == 1
    command = persistence_service.commands[0]
    assert command.claim_observations == ()
    assert command.prompt_version == "faq_claim_observations.v1.oversized_split"
    assert command.invocation_status == "request_too_large"
    assert command.raw_payload == {
        "claim_observations": [],
        "oversized_section_split": {
            "reason": "prompt_a_fallback_exhausted_request_too_large",
            "parent_section_id": "section-parent",
            "parent_section_key": "section-parent",
            "child_section_ids": [
                section.section_id for section in repository.upserted_sections
            ],
            "child_queue_item_ids": [
                item.queue_item_id for item in repository.updated_items
            ],
        },
    }
