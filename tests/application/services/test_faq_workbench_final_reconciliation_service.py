from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.application.ports.faq_workbench_final_reconciliation_generator import (
    FaqWorkbenchFinalReconciliationGenerationResult,
    FinalReconciliationAdvice,
    FaqWorkbenchFinalReconciliationGenerationError,
)
from src.application.services.faq_workbench_final_reconciliation_service import (
    FaqWorkbenchFinalReconciliationService,
    PersistFinalReconciliationNodeOutputCommand,
    ProcessFinalReconciliationGenerationErrorCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeName,
    ProcessingNodeRun,
    ProcessingNodeStatus,
    RegistrySnapshot,
    KnowledgeDocumentStatus,
    ProcessingRunStatus,
    ResumePolicy,
)
from src.domain.project_plane.llm_routing import (
    LlmInvocationStatus,
    LlmJsonInvocationResult,
    LlmRouteAttempt,
    LlmRouteAttemptStatus,
    LlmTokenUsage,
    LlmInvocationFailure,
)


@dataclass(frozen=True, slots=True)
class FixedTimeProvider:
    value: datetime

    def now(self) -> datetime:
        return self.value


@dataclass(slots=True)
class MonotonicIdFactory:
    current: int = 0

    def new_id(self, prefix: str) -> str:
        self.current += 1
        return f"{prefix}-{self.current}"


@dataclass(slots=True)
class InMemoryFinalReconciliationRepository:
    node_runs: list[ProcessingNodeRun] = field(default_factory=list)
    artifacts: list[ProcessingNodeArtifact] = field(default_factory=list)
    processing_run_usage_syncs: list[dict[str, object]] = field(default_factory=list)
    final_reconciliation_generation_error_lifecycles: list[dict[str, object]] = field(
        default_factory=list
    )
    applications: list[object] = field(default_factory=list)
    entries: list[object] = field(default_factory=list)
    proposals: list[object] = field(default_factory=list)

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
        self.processing_run_usage_syncs.append(
            {
                "project_id": project_id,
                "document_id": document_id,
                "processing_run_id": processing_run_id,
            }
        )

    async def persist_final_reconciliation_generation_error_lifecycle(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        node_run_id: str,
        document_status: KnowledgeDocumentStatus,
        processing_run_status: ProcessingRunStatus,
        resume_policy: ResumePolicy,
        error_kind: str,
        user_message: str,
        internal_error: str,
    ) -> None:
        self.final_reconciliation_generation_error_lifecycles.append(
            {
                "project_id": project_id,
                "document_id": document_id,
                "processing_run_id": processing_run_id,
                "node_run_id": node_run_id,
                "document_status": document_status,
                "processing_run_status": processing_run_status,
                "resume_policy": resume_policy,
                "error_kind": error_kind,
                "user_message": user_message,
                "internal_error": internal_error,
            }
        )

    async def create_registry_update_proposals(self, proposals):
        self.proposals.extend(proposals)

    async def create_registry_update_applications(self, applications):
        self.applications.extend(applications)

    async def upsert_question_registry_entries(self, entries):
        self.entries.extend(entries)


def _snapshot() -> RegistrySnapshot:
    return RegistrySnapshot(
        snapshot_id="snapshot-1",
        registry_id="registry-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        after_node_run_id="registry-update-application-node",
        sequence_number=2,
        entries_payload={"entries": []},
        relations_payload={"relations": []},
        entry_count=1,
        relation_count=0,
        claim_observation_count=2,
        update_count=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _generation_result() -> FaqWorkbenchFinalReconciliationGenerationResult:
    advice = FinalReconciliationAdvice(
        surface_adjustments=({"surface_key": "surface-1", "action": "tighten"},),
        relations=({"source": "surface-1", "target": "surface-2"},),
        merge_decisions=(),
        warnings=("review relation",),
        metrics={"bounded_final_reconciliation": True},
    )
    return FaqWorkbenchFinalReconciliationGenerationResult(
        advice=advice,
        invocation=LlmJsonInvocationResult(
            status=LlmInvocationStatus.SUCCESS,
            parsed_json={
                "surface_adjustments": [{"surface_key": "surface-1"}],
                "relations": [],
                "merge_decisions": [],
            },
            raw_text='{"surface_adjustments":[]}',
            token_usage=LlmTokenUsage(prompt_tokens=17, completion_tokens=9),
            attempts=(
                LlmRouteAttempt(
                    provider_id="groq",
                    model="llama-3.1-8b-instant",
                    api_key_slot="slot-final",
                    attempt_index=0,
                    status=LlmRouteAttemptStatus.SUCCESS,
                ),
            ),
        ),
        raw_output_artifact_payload={"raw_text": '{"surface_adjustments":[]}'},
        parsed_output_artifact_payload={
            "surface_adjustments": advice.surface_adjustments,
            "relations": advice.relations,
            "merge_decisions": advice.merge_decisions,
            "warnings": advice.warnings,
            "metrics": advice.metrics,
        },
    )


@pytest.mark.asyncio
async def test_persist_final_reconciliation_output_creates_node_artifacts_and_usage_sync() -> (
    None
):
    repository = InMemoryFinalReconciliationRepository()
    service = FaqWorkbenchFinalReconciliationService(
        repository=repository,
        id_factory=MonotonicIdFactory(),
        time_provider=FixedTimeProvider(datetime(2026, 6, 1, tzinfo=timezone.utc)),
    )

    result = await service.persist_final_reconciliation_output(
        PersistFinalReconciliationNodeOutputCommand(
            node_run_id="node-run-final",
            registry_snapshot=_snapshot(),
            generation_result=_generation_result(),
        )
    )

    assert result.node_run.node_run_id == "node-run-final"
    assert (
        result.node_run.node_name is ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION
    )
    assert result.node_run.status is ProcessingNodeStatus.COMPLETED
    assert result.node_run.section_id is None
    assert result.node_run.model_provider == "groq"
    assert result.node_run.model_name == "llama-3.1-8b-instant"
    assert result.node_run.groq_key_slot == "slot-final"
    assert result.node_run.prompt_tokens == 17
    assert result.node_run.completion_tokens == 9
    assert result.node_run.total_tokens == 26

    assert repository.node_runs == [result.node_run]
    assert len(repository.artifacts) == 2
    assert repository.artifacts[0] is result.raw_llm_artifact
    assert (
        repository.artifacts[0].artifact_type
        is ProcessingNodeArtifactType.RAW_LLM_OUTPUT
    )
    assert repository.artifacts[1] is result.parsed_llm_artifact
    assert (
        repository.artifacts[1].artifact_type
        is ProcessingNodeArtifactType.PARSED_LLM_OUTPUT
    )
    assert repository.artifacts[1].metadata["suggestion_count"] == 2
    assert repository.processing_run_usage_syncs == [
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "processing_run_id": "processing-run-1",
        }
    ]

    assert repository.proposals == []
    assert repository.applications == []
    assert repository.entries == []


@pytest.mark.asyncio
async def test_persist_final_reconciliation_output_rejects_missing_node_run_id() -> (
    None
):
    service = FaqWorkbenchFinalReconciliationService(
        repository=InMemoryFinalReconciliationRepository(),
        id_factory=MonotonicIdFactory(),
    )

    with pytest.raises(DomainInvariantError, match="node_run_id"):
        await service.persist_final_reconciliation_output(
            PersistFinalReconciliationNodeOutputCommand(
                node_run_id="",
                registry_snapshot=_snapshot(),
                generation_result=_generation_result(),
            )
        )


@pytest.mark.asyncio
async def test_persist_final_reconciliation_generation_error_creates_failed_node_error_report_and_lifecycle() -> (
    None
):
    repository = InMemoryFinalReconciliationRepository()
    service = FaqWorkbenchFinalReconciliationService(
        repository=repository,
        id_factory=MonotonicIdFactory(),
        time_provider=FixedTimeProvider(datetime(2026, 6, 1, tzinfo=timezone.utc)),
    )
    failed_invocation = LlmJsonInvocationResult(
        status=LlmInvocationStatus.PROVIDER_ERROR,
        parsed_json=None,
        raw_text="provider failed",
        token_usage=LlmTokenUsage(prompt_tokens=23, completion_tokens=0),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model="llama-3.1-8b-instant",
                api_key_slot="slot-final",
                attempt_index=0,
                status=LlmRouteAttemptStatus.FAILED,
                error_kind="provider_error",
            ),
        ),
        failure=LlmInvocationFailure(
            status=LlmInvocationStatus.PROVIDER_ERROR,
            error_kind="provider_error",
            user_message="ИИ временно недоступен.",
            internal_message="provider failed during final reconciliation",
        ),
    )

    result = await service.persist_final_reconciliation_generation_error(
        ProcessFinalReconciliationGenerationErrorCommand(
            node_run_id="node-run-final-failed",
            registry_snapshot=_snapshot(),
            error=FaqWorkbenchFinalReconciliationGenerationError(failed_invocation),
        )
    )

    assert result.node_run.node_run_id == "node-run-final-failed"
    assert (
        result.node_run.node_name is ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION
    )
    assert result.node_run.status is ProcessingNodeStatus.FAILED
    assert result.node_run.section_id is None
    assert result.node_run.model_provider == "groq"
    assert result.node_run.model_name == "llama-3.1-8b-instant"
    assert result.node_run.groq_key_slot == "slot-final"
    assert result.node_run.prompt_tokens == 23
    assert result.node_run.completion_tokens == 0
    assert result.node_run.total_tokens == 23
    assert result.node_run.error_kind == "provider_error"
    assert result.node_run.error_message_user == "ИИ временно недоступен."

    assert (
        result.error_artifact.artifact_type is ProcessingNodeArtifactType.ERROR_REPORT
    )
    assert result.error_artifact.payload_json["node"] == (
        "faq_surface_final_reconciliation"
    )
    assert result.error_artifact.payload_json["snapshot_id"] == "snapshot-1"
    assert result.error_artifact.payload_json["invocation_status"] == "provider_error"
    assert result.error_artifact.payload_json["route_attempts"][0]["error_kind"] == (
        "provider_error"
    )

    assert result.lifecycle.document_status is KnowledgeDocumentStatus.PAUSED
    assert result.lifecycle.processing_run_status is ProcessingRunStatus.PAUSED_PROVIDER
    assert result.lifecycle.resume_policy is ResumePolicy.AUTO_ALLOWED

    assert repository.node_runs == [result.node_run]
    assert repository.artifacts == [result.error_artifact]
    assert repository.processing_run_usage_syncs
    assert (
        repository.final_reconciliation_generation_error_lifecycles[0]["node_run_id"]
        == "node-run-final-failed"
    )
    assert repository.proposals == []
    assert repository.applications == []
    assert repository.entries == []
