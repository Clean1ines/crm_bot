from __future__ import annotations
from src.domain.project_plane.llm_routing import LlmTokenUsage
from src.domain.project_plane.llm_routing import LlmRouteAttemptStatus
from src.domain.project_plane.llm_routing import LlmRouteAttempt
from src.domain.project_plane.llm_routing import LlmJsonInvocationResult
from src.domain.project_plane.llm_routing import LlmInvocationStatus
from src.domain.project_plane.llm_routing import LlmInvocationFailure

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_claim_observations_service import (
    FaqWorkbenchClaimObservationsService,
    MonotonicIdFactory,
    ParsedSectionFinding,
    ProcessClaimObservationsCommand,
    ProcessClaimObservationsGenerationErrorCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DocumentSectionStatus,
    DomainInvariantError,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeName,
    ProcessingNodeRun,
    FactRegistry,
    FactRegistryStatus,
    RegistrySnapshot,
    SectionFinding,
    SectionFindingAction,
    SectionFindingStatus,
    SourceType,
    SurfaceKind,
    ProcessingNodeStatus,
)


@dataclass(frozen=True, slots=True)
class FixedTimeProvider:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass(slots=True)
class InMemoryClaimObservationsRepository:
    node_runs: list[ProcessingNodeRun] = field(default_factory=list)
    artifacts: list[ProcessingNodeArtifact] = field(default_factory=list)
    findings: list[SectionFinding] = field(default_factory=list)
    snapshots: list[RegistrySnapshot] = field(default_factory=list)
    processing_run_usage_syncs: list[dict[str, object]] = field(default_factory=list)
    generation_error_lifecycle_updates: list[dict[str, object]] = field(
        default_factory=list
    )

    async def create_processing_node_run(self, node_run: ProcessingNodeRun) -> None:
        self.node_runs.append(node_run)

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None:
        self.artifacts.append(artifact)

    async def sync_processing_run_llm_usage_totals(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> None:
        updates = getattr(self, "processing_run_usage_syncs", None)
        if updates is None:
            return
        updates.append(
            {
                "project_id": project_id,
                "document_id": document_id,
                "processing_run_id": processing_run_id,
            }
        )

    async def persist_claim_observations_generation_error_lifecycle(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        document_status,
        processing_run_status,
        resume_policy,
        error_kind: str,
        error_report_id: str,
        user_message: str,
        internal_error: str,
    ) -> None:
        updates = getattr(self, "generation_error_lifecycle_updates", None)
        if updates is None:
            return
        updates.append(
            {
                "project_id": project_id,
                "document_id": document_id,
                "processing_run_id": processing_run_id,
                "document_status": document_status,
                "processing_run_status": processing_run_status,
                "resume_policy": resume_policy,
                "error_kind": error_kind,
                "error_report_id": error_report_id,
                "user_message": user_message,
                "internal_error": internal_error,
            }
        )

    async def create_claim_observations(
        self,
        findings: tuple[SectionFinding, ...],
    ) -> None:
        self.findings.extend(findings)

    async def create_registry_snapshot(self, snapshot: RegistrySnapshot) -> None:
        self.snapshots.append(snapshot)


def _section() -> DocumentSection:
    return DocumentSection(
        section_id="section-1",
        document_id="document-1",
        project_id="project-1",
        section_index=0,
        section_key="section-0001-product",
        heading_path=("Product",),
        title="Product",
        raw_text="# Product\nSystem turns docs into knowledge.",
        normalized_text="# Product\nSystem turns docs into knowledge.",
        source_refs=("document-1#section-0001-product",),
        source_chunk_indexes=(0,),
        status=DocumentSectionStatus.PENDING,
    )


def _registry(
    status: FactRegistryStatus = FactRegistryStatus.BUILDING,
) -> FactRegistry:
    return FactRegistry(
        registry_id="registry-1",
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        status=status,
        version=1,
        created_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 31, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_persist_claim_observations_creates_node_artifacts_findings_and_snapshot() -> (
    None
):
    repository = InMemoryClaimObservationsRepository()
    service = FaqWorkbenchClaimObservationsService(
        repository,
        id_factory=MonotonicIdFactory.create(),
        time_provider=FixedTimeProvider(datetime(2026, 5, 31, tzinfo=timezone.utc)),
    )

    result = await service.persist_claim_observations(
        ProcessClaimObservationsCommand(
            section=_section(),
            registry=_registry(),
            registry_snapshot_payload={
                "entries": [
                    {
                        "registry_entry_key": "product_definition",
                        "canonical_question": "Что такое продукт?",
                    }
                ]
            },
            parsed_findings=(
                ParsedSectionFinding(
                    action=SectionFindingAction.NEW,
                    local_surface_key="product_definition",
                    title="Описание продукта",
                    canonical_question="Что такое продукт?",
                    surface_kind=SurfaceKind.DEFINITION,
                    answer="System turns docs into knowledge.",
                    short_answer="Docs become knowledge.",
                    answer_delta="",
                    answer_scope="Product definition",
                    question_scope="Product questions",
                    exclusion_scope="Pricing",
                    variants=("what is product",),
                    evidence_quotes=("System turns docs into knowledge.",),
                    source_refs=("document-1#section-0001-product",),
                    source_chunk_indexes=(0,),
                    confidence=0.9,
                    reason="section directly defines the product",
                ),
            ),
        )
    )

    assert result.node_run.node_name is ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS
    assert result.node_run.section_id == "section-1"
    assert len(result.findings) == 1
    assert result.findings[0].status is SectionFindingStatus.PROPOSED
    assert result.findings[0].canonical_question == "Что такое продукт?"

    assert (
        result.input_artifact.artifact_type is ProcessingNodeArtifactType.INPUT_SNAPSHOT
    )
    assert (
        result.output_artifact.artifact_type
        is ProcessingNodeArtifactType.PARSED_LLM_OUTPUT
    )
    assert result.snapshot.after_section_id == "section-1"
    assert result.snapshot.finding_count == 1

    assert repository.node_runs == [result.node_run]
    assert repository.artifacts == [result.input_artifact, result.output_artifact]
    assert repository.findings == list(result.findings)
    assert repository.snapshots == [result.snapshot]


@pytest.mark.asyncio
async def test_claim_observations_rejects_project_mismatch() -> None:
    repository = InMemoryClaimObservationsRepository()
    service = FaqWorkbenchClaimObservationsService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    section = _section()
    registry = FactRegistry(
        registry_id="registry-1",
        project_id="other-project",
        document_id="document-1",
        processing_run_id="processing-run-1",
        status=FactRegistryStatus.BUILDING,
        version=1,
    )

    with pytest.raises(DomainInvariantError):
        await service.persist_claim_observations(
            ProcessClaimObservationsCommand(
                section=section,
                registry=registry,
                registry_snapshot_payload={"entries": []},
                parsed_findings=(),
            )
        )

    assert repository.node_runs == []
    assert repository.findings == []


@pytest.mark.asyncio
async def test_claim_observations_rejects_deleted_registry() -> None:
    repository = InMemoryClaimObservationsRepository()
    service = FaqWorkbenchClaimObservationsService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    with pytest.raises(DomainInvariantError):
        await service.persist_claim_observations(
            ProcessClaimObservationsCommand(
                section=_section(),
                registry=_registry(FactRegistryStatus.DELETED),
                registry_snapshot_payload={"entries": []},
                parsed_findings=(),
            )
        )

    assert repository.node_runs == []
    assert repository.snapshots == []


def test_source_type_import_does_not_pull_legacy() -> None:
    assert SourceType.MARKDOWN.value == "markdown"


@pytest.mark.asyncio
async def test_persist_claim_observations_generation_error_records_failed_node_and_artifact() -> (
    None
):
    repository = InMemoryClaimObservationsRepository()
    service = FaqWorkbenchClaimObservationsService(
        repository=repository,
        id_factory=MonotonicIdFactory.create(),
        time_provider=FixedTimeProvider(datetime(2026, 5, 31, tzinfo=timezone.utc)),
    )
    invocation = LlmJsonInvocationResult(
        status=LlmInvocationStatus.RATE_LIMITED,
        parsed_json=None,
        raw_text="",
        token_usage=LlmTokenUsage(prompt_tokens=11, completion_tokens=3),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model="llama-3.1-8b-instant",
                api_key_slot="slot-1",
                attempt_index=0,
                status=LlmRouteAttemptStatus.FAILED,
                error_kind="groq_rate_limit",
                cooldown_seconds=60,
            ),
        ),
        failure=LlmInvocationFailure(
            status=LlmInvocationStatus.RATE_LIMITED,
            error_kind="groq_rate_limit",
            user_message="ИИ временно перегружен. Обработка продолжится позже.",
            internal_message="provider returned rate limit",
            cooldown_seconds=60,
        ),
    )

    result = await service.persist_claim_observations_generation_error(
        ProcessClaimObservationsGenerationErrorCommand(
            section=_section(),
            registry=_registry(),
            registry_snapshot_payload={"entries": []},
            invocation=invocation,
        )
    )

    assert result.node_run.status is ProcessingNodeStatus.FAILED
    assert result.node_run.error_kind == "groq_rate_limit"
    assert result.node_run.error_message_user == (
        "ИИ временно перегружен. Обработка продолжится позже."
    )
    assert result.node_run.prompt_tokens == 11
    assert result.node_run.completion_tokens == 3
    assert result.node_run.total_tokens == 14

    assert (
        result.error_artifact.artifact_type is ProcessingNodeArtifactType.ERROR_REPORT
    )
    assert result.error_artifact.payload_json["invocation_status"] == "rate_limited"
    assert result.error_artifact.payload_json["error_kind"] == "groq_rate_limit"
    assert (
        result.error_artifact.payload_json["route_attempts"][0]["api_key_slot"]
        == "slot-1"
    )
    assert repository.node_runs[-1] is result.node_run
    assert repository.artifacts[-1] is result.error_artifact
    assert (
        repository.processing_run_usage_syncs[-1]["processing_run_id"]
        == "processing-run-1"
    )
