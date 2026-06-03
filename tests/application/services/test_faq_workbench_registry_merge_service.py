from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.application.ports.faq_workbench_registry_merge_generator import (
    FaqWorkbenchRegistryMergeGenerationError,
    FaqWorkbenchRegistryMergeGenerationResult,
)
from src.application.services.faq_workbench_registry_merge_service import (
    FaqWorkbenchRegistryMergeService,
    PersistRegistryMergeNodeOutputCommand,
    ProcessRegistryMergeGenerationErrorCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    FactRegistry,
    FactRegistryStatus,
    KnowledgeDocumentStatus,
    LocalClaimCanonicalizationMember,
    LocalClaimCanonicalizationUnit,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeName,
    ProcessingNodeRun,
    ProcessingRunStatus,
    ResumePolicy,
)
from src.domain.project_plane.llm_routing import (
    LlmInvocationFailure,
    LlmInvocationStatus,
    LlmJsonInvocationResult,
    LlmRouteAttempt,
    LlmRouteAttemptStatus,
    LlmTokenUsage,
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
class InMemoryRegistryMergeRepository:
    node_runs: list[ProcessingNodeRun] = field(default_factory=list)
    artifacts: list[ProcessingNodeArtifact] = field(default_factory=list)
    processing_run_usage_syncs: list[dict[str, object]] = field(default_factory=list)
    registry_merge_generation_error_lifecycles: list[dict[str, object]] = field(
        default_factory=list
    )
    applications: list[object] = field(default_factory=list)
    entries: list[object] = field(default_factory=list)

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

    async def persist_registry_merge_generation_error_lifecycle(
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
        self.registry_merge_generation_error_lifecycles.append(
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

    async def create_registry_update_applications(self, applications):
        self.applications.extend(applications)

    async def upsert_fact_registry_entries(self, entries):
        self.entries.extend(entries)


def _canonicalization_unit() -> LocalClaimCanonicalizationUnit:
    return LocalClaimCanonicalizationUnit(
        unit_id="canonicalization-unit-1",
        group_id="group:section-1:node-run-a:c1|section-2:node-run-b:c2",
        members=(
            LocalClaimCanonicalizationMember(
                search_document_id="section-1:node-run-a:c1",
                local_ref="c1",
                section_id="section-1",
                node_run_id="node-run-a",
                claim="Продукт является платформой управления AI-базами знаний.",
                claim_kind="definition",
                granularity="atomic",
                triple_texts=(
                    "Продукт is_a платформа управления AI-базами знаний",
                ),
                possible_questions=("Что такое продукт?",),
                scope="Общее определение",
                exclusion_scope="",
                evidence_block="Продукт — это платформа управления AI-базами знаний.",
                relation_texts=(),
                search_text="claim: Продукт является платформой управления AI-базами знаний.",
            ),
            LocalClaimCanonicalizationMember(
                search_document_id="section-2:node-run-b:c2",
                local_ref="c2",
                section_id="section-2",
                node_run_id="node-run-b",
                claim="Платформа управляет AI-базами знаний.",
                claim_kind="capability",
                granularity="atomic",
                triple_texts=(
                    "Платформа has_capability управлять AI-базами знаний",
                ),
                possible_questions=("Что умеет платформа?",),
                scope="Общее определение",
                exclusion_scope="",
                evidence_block="Платформа управляет AI-базами знаний.",
                relation_texts=(),
                search_text="claim: Платформа управляет AI-базами знаний.",
            ),
        ),
        edges=(),
        max_similarity_score=0.5,
    )


def _registry(project_id: str = "project-1") -> FactRegistry:
    return FactRegistry(
        registry_id="registry-1",
        project_id=project_id,
        document_id="document-1",
        processing_run_id="processing-run-1",
        status=FactRegistryStatus.BUILDING,
        version=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _fact_registry_payload() -> dict:
    return {
        "version": 1,
        "canonical_facts": [
            {
                "fact_id": "cf_product_definition",
                "claim": "Продукт является платформой управления AI-базами знаний.",
                "claim_kind": "definition",
                "granularity": "atomic",
                "triples": [
                    {
                        "subject": "Продукт",
                        "predicate": "is_a",
                        "object": "платформа управления AI-базами знаний",
                        "qualifiers": [],
                    },
                ],
                "mentions": [
                    {
                        "source_section_ref": "document-1#section-0001-product",
                        "source_local_ref": "c1",
                        "evidence_block": "Продукт — это платформа управления AI-базами знаний.",
                        "mention_relation": "initial",
                    },
                ],
                "question_variants": ["Что такое продукт?"],
                "scope": "Общее определение",
                "exclusion_scope": "",
                "derived_fact_notes": [],
                "status": "active",
            },
        ],
        "fact_relations": [],
    }


def _registry_update_summary() -> dict:
    return {
        "created_fact_count": 1,
        "updated_fact_count": 0,
        "created_relation_count": 0,
        "notes": [],
    }


def _generation_result() -> FaqWorkbenchRegistryMergeGenerationResult:
    fact_registry = _fact_registry_payload()
    registry_update_summary = _registry_update_summary()

    return FaqWorkbenchRegistryMergeGenerationResult(
        fact_registry=fact_registry,
        registry_update_summary=registry_update_summary,
        invocation=LlmJsonInvocationResult(
            status=LlmInvocationStatus.SUCCESS,
            parsed_json={
                "fact_registry": fact_registry,
                "registry_update_summary": registry_update_summary,
            },
            raw_text='{"fact_registry":{"version":1}}',
            token_usage=LlmTokenUsage(prompt_tokens=11, completion_tokens=5),
            attempts=(
                LlmRouteAttempt(
                    provider_id="groq",
                    model="llama-3.1-8b-instant",
                    api_key_slot="slot-1",
                    attempt_index=0,
                    status=LlmRouteAttemptStatus.SUCCESS,
                ),
            ),
        ),
        raw_output_artifact_payload={"raw_text": '{"fact_registry":{"version":1}}'},
        parsed_output_artifact_payload={
            "fact_registry": fact_registry,
            "registry_update_summary": registry_update_summary,
        },
    )


@pytest.mark.asyncio
async def test_persist_registry_merge_output_creates_document_level_node_artifacts_fact_registry_and_usage_sync() -> None:
    repository = InMemoryRegistryMergeRepository()
    service = FaqWorkbenchRegistryMergeService(
        repository=repository,
        id_factory=MonotonicIdFactory(),
        time_provider=FixedTimeProvider(datetime(2026, 6, 1, tzinfo=timezone.utc)),
    )

    result = await service.persist_registry_merge_output(
        PersistRegistryMergeNodeOutputCommand(
            node_run_id="node-run-1",
            canonicalization_unit=_canonicalization_unit(),
            registry=_registry(),
            generation_result=_generation_result(),
        )
    )

    assert result.node_run.node_run_id == "node-run-1"
    assert result.node_run.node_name is ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE
    assert result.node_run.section_id is None
    assert result.node_run.model_provider == "groq"
    assert result.node_run.model_name == "llama-3.1-8b-instant"
    assert result.node_run.groq_key_slot == "slot-1"
    assert result.node_run.prompt_tokens == 11
    assert result.node_run.completion_tokens == 5
    assert result.node_run.total_tokens == 16

    assert repository.node_runs == [result.node_run]
    assert len(repository.artifacts) == 2
    assert repository.artifacts[0] is result.raw_llm_artifact
    assert repository.artifacts[0].artifact_type is ProcessingNodeArtifactType.RAW_LLM_OUTPUT
    assert repository.artifacts[0].section_id is None
    assert repository.artifacts[1] is result.parsed_llm_artifact
    assert repository.artifacts[1].artifact_type is ProcessingNodeArtifactType.PARSED_LLM_OUTPUT
    assert repository.artifacts[1].section_id is None

    assert repository.artifacts[1].payload_json["fact_registry"] == _fact_registry_payload()
    assert repository.artifacts[1].payload_json["registry_update_summary"] == _registry_update_summary()
    assert "registry_updates" not in repository.artifacts[1].payload_json

    assert result.fact_registry == _fact_registry_payload()
    assert result.registry_update_summary == _registry_update_summary()
    assert result.parsed_llm_artifact.metadata["canonical_fact_count"] == 1
    assert result.parsed_llm_artifact.metadata["fact_relation_count"] == 0
    assert result.parsed_llm_artifact.metadata["contract"] == "fact_registry_canonicalization"
    assert result.parsed_llm_artifact.metadata["canonicalization_unit_id"] == (
        "canonicalization-unit-1"
    )
    assert result.parsed_llm_artifact.metadata["canonicalization_member_section_ids"] == [
        "section-1",
        "section-2",
    ]
    assert result.parsed_llm_artifact.metadata["canonicalization_member_local_refs"] == [
        "c1",
        "c2",
    ]
    assert repository.processing_run_usage_syncs == [
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "processing_run_id": "processing-run-1",
        }
    ]


def test_registry_merge_output_rejects_missing_node_run_id() -> None:
    service = FaqWorkbenchRegistryMergeService(
        repository=InMemoryRegistryMergeRepository(),
        id_factory=MonotonicIdFactory(),
        time_provider=FixedTimeProvider(datetime(2026, 6, 1, tzinfo=timezone.utc)),
    )

    with pytest.raises(DomainInvariantError, match="node_run_id"):
        service._validate_command(
            PersistRegistryMergeNodeOutputCommand(
                node_run_id="",
                canonicalization_unit=_canonicalization_unit(),
                registry=_registry(),
                generation_result=_generation_result(),
            )
        )


@pytest.mark.asyncio
async def test_registry_merge_generation_error_persists_lifecycle_and_error_artifact() -> None:
    repository = InMemoryRegistryMergeRepository()
    service = FaqWorkbenchRegistryMergeService(
        repository=repository,
        id_factory=MonotonicIdFactory(),
        time_provider=FixedTimeProvider(datetime(2026, 6, 1, tzinfo=timezone.utc)),
    )

    invocation = LlmJsonInvocationResult(
        status=LlmInvocationStatus.PROVIDER_ERROR,
        parsed_json=None,
        raw_text="provider failed",
        token_usage=LlmTokenUsage(prompt_tokens=7, completion_tokens=0),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model="llama-3.1-8b-instant",
                api_key_slot="slot-2",
                attempt_index=0,
                status=LlmRouteAttemptStatus.FAILED,
                error_kind="provider_error",
            ),
        ),
        failure=LlmInvocationFailure(
            status=LlmInvocationStatus.PROVIDER_ERROR,
            error_kind="provider_error",
            user_message="Провайдер ИИ временно недоступен.",
            internal_message="provider failed",
        ),
    )
    error = FaqWorkbenchRegistryMergeGenerationError(invocation)

    result = await service.persist_registry_merge_generation_error(
        ProcessRegistryMergeGenerationErrorCommand(
            node_run_id="node-run-registry-merge",
            canonicalization_unit=_canonicalization_unit(),
            registry=_registry(),
            error=error,
        )
    )

    assert result.node_run.node_run_id == "node-run-registry-merge"
    assert result.node_run.status.value == "failed"
    assert result.node_run.section_id is None
    assert result.error_artifact.artifact_type is ProcessingNodeArtifactType.ERROR_REPORT
    assert result.error_artifact.section_id is None
    assert result.error_artifact.metadata["canonicalization_unit_id"] == (
        "canonicalization-unit-1"
    )
    assert result.error_artifact.payload_json["canonicalization_unit"]["unit_id"] == (
        "canonicalization-unit-1"
    )
    assert result.lifecycle.document_status is KnowledgeDocumentStatus.PAUSED
    assert result.lifecycle.processing_run_status is ProcessingRunStatus.PAUSED_PROVIDER
    assert result.lifecycle.resume_policy is ResumePolicy.AUTO_ALLOWED

    assert repository.node_runs == [result.node_run]
    assert repository.artifacts == [result.error_artifact]
    assert repository.registry_merge_generation_error_lifecycles == [
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "processing_run_id": "processing-run-1",
            "node_run_id": "node-run-registry-merge",
            "document_status": KnowledgeDocumentStatus.PAUSED,
            "processing_run_status": ProcessingRunStatus.PAUSED_PROVIDER,
            "resume_policy": ResumePolicy.AUTO_ALLOWED,
            "error_kind": "provider_error",
            "user_message": "Провайдер ИИ временно недоступен.",
            "internal_error": "provider failed",
        }
    ]


def test_registry_merge_service_test_repository_has_no_old_proposal_storage() -> None:
    repository = InMemoryRegistryMergeRepository()

    assert not hasattr(repository, "proposals")
    assert not hasattr(repository, "create_registry_update_proposals")
