from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from src.application.ports.faq_workbench_registry_merge_generator import (
    FaqWorkbenchRegistryMergeGenerationResult,
)
from src.application.services.faq_workbench_canonicalization_barrier_service import (
    FaqWorkbenchCanonicalizationBarrierService,
    ProcessDocumentCanonicalizationBarrierCommand,
)
from src.application.services.faq_workbench_local_claim_retrieval_service import (
    DocumentLocalClaimRetrievalResult,
)
from src.application.services.faq_workbench_registry_application_service import (
    ApplyFactRegistrySnapshotCommand,
    ApplyFactRegistrySnapshotResult,
)
from src.application.services.faq_workbench_registry_merge_service import (
    PersistRegistryMergeNodeOutputCommand,
    PersistRegistryMergeNodeOutputResult,
)
from src.domain.project_plane.knowledge_workbench import (
    FactRegistry,
    FactRegistryStatus,
    LocalClaimCanonicalizationMember,
    LocalClaimCanonicalizationUnit,
    RegistrySnapshot,
)
from src.domain.project_plane.llm_routing import (
    LlmInvocationFailure,
    LlmInvocationStatus,
    LlmJsonInvocationResult,
    LlmRouteAttempt,
    LlmRouteAttemptStatus,
    LlmTokenUsage,
)


@dataclass(slots=True)
class MonotonicIdFactory:
    value: int = 0

    def new_id(self, prefix: str) -> str:
        self.value += 1
        return f"{prefix}-{self.value}"


@dataclass(slots=True)
class FakeRepository:
    registry: FactRegistry
    latest_snapshot: RegistrySnapshot | None = None
    canonical_facts: tuple[object, ...] = ()
    canonicalization_completed: bool = False
    completion_guard_calls: int = 0
    registry_calls: int = 0
    snapshot_calls: int = 0
    facts_calls: int = 0
    created_node_runs: list[object] = field(default_factory=list)
    created_artifacts: list[object] = field(default_factory=list)

    async def create_processing_node_run(self, node_run):
        self.created_node_runs.append(node_run)

    async def create_processing_node_artifact(self, artifact):
        self.created_artifacts.append(artifact)

    async def has_completed_fact_registry_canonicalization(self, **kwargs):
        self.completion_guard_calls += 1
        return self.canonicalization_completed

    async def get_fact_registry_for_run(self, **kwargs):
        self.registry_calls += 1
        return self.registry

    async def get_latest_registry_snapshot(self, **kwargs):
        self.snapshot_calls += 1
        return self.latest_snapshot

    async def list_canonical_facts(self, **kwargs):
        self.facts_calls += 1
        return self.canonical_facts


@dataclass(slots=True)
class FakeRetrievalService:
    result: DocumentLocalClaimRetrievalResult
    commands: list[object] = field(default_factory=list)

    async def build_document_local_claim_retrieval(self, command):
        self.commands.append(command)
        return self.result


@dataclass(slots=True)
class FakeRegistryMergeGenerator:
    commands: list[object] = field(default_factory=list)

    async def generate_registry_updates(self, command):
        self.commands.append(command)
        index = len(self.commands)
        fact_registry = {
            "version": 1,
            "canonical_facts": [
                {
                    "fact_id": f"fact-{index}",
                    "claim": f"Claim {index}",
                    "claim_kind": "definition",
                    "granularity": "atomic",
                    "triples": [],
                    "mentions": [],
                    "question_variants": [],
                    "derived_fact_notes": [],
                    "status": "active",
                }
            ],
            "fact_relations": [],
        }
        registry_update_summary = {
            "created_fact_count": 1,
            "updated_fact_count": 0,
            "created_relation_count": 0,
            "notes": [],
        }
        return FaqWorkbenchRegistryMergeGenerationResult(
            fact_registry=fact_registry,
            registry_update_summary=registry_update_summary,
            invocation=LlmJsonInvocationResult(
                status=LlmInvocationStatus.SUCCESS,
                parsed_json={
                    "fact_registry": fact_registry,
                    "registry_update_summary": registry_update_summary,
                },
                raw_text="{}",
                token_usage=LlmTokenUsage(prompt_tokens=1, completion_tokens=1),
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
            raw_output_artifact_payload={"raw": index},
            parsed_output_artifact_payload={
                "fact_registry": fact_registry,
                "registry_update_summary": registry_update_summary,
            },
        )


@dataclass(slots=True)
class FakeRegistryMergeService:
    commands: list[PersistRegistryMergeNodeOutputCommand] = field(default_factory=list)

    async def persist_registry_merge_output(
        self,
        command: PersistRegistryMergeNodeOutputCommand,
    ):
        self.commands.append(command)
        return PersistRegistryMergeNodeOutputResult(
            node_run=SimpleNamespace(node_run_id=command.node_run_id),
            raw_llm_artifact=SimpleNamespace(),
            parsed_llm_artifact=SimpleNamespace(),
            fact_registry=command.generation_result.fact_registry,
            registry_update_summary=command.generation_result.registry_update_summary,
        )


@dataclass(slots=True)
class FakeRegistryApplicationService:
    commands: list[ApplyFactRegistrySnapshotCommand] = field(default_factory=list)

    async def apply_fact_registry_snapshot(
        self,
        command: ApplyFactRegistrySnapshotCommand,
    ):
        self.commands.append(command)
        snapshot = RegistrySnapshot(
            snapshot_id=f"snapshot-{len(self.commands)}",
            registry_id=command.registry.registry_id,
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            after_section_id=command.after_section_id,
            after_node_run_id=command.after_node_run_id,
            sequence_number=command.previous_snapshot_sequence_number + 1,
            entries_payload={
                "contract": "fact_registry",
                "previous_snapshot_id": command.previous_snapshot_id,
                "fact_registry": command.fact_registry,
                "registry_update_summary": command.registry_update_summary,
            },
            relations_payload={
                "contract": "fact_registry_relations",
                "fact_relations": command.fact_registry["fact_relations"],
            },
            entry_count=len(command.fact_registry["canonical_facts"]),
            relation_count=len(command.fact_registry["fact_relations"]),
            claim_observation_count=0,
            update_count=1,
            created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        return ApplyFactRegistrySnapshotResult(
            snapshot=snapshot,
            fact_registry=command.fact_registry,
            registry_update_summary=command.registry_update_summary,
        )


def _registry() -> FactRegistry:
    return FactRegistry(
        registry_id="registry-1",
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        status=FactRegistryStatus.BUILDING,
        version=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _unit(local_ref: str) -> LocalClaimCanonicalizationUnit:
    return LocalClaimCanonicalizationUnit(
        unit_id=f"unit-{local_ref}",
        group_id=f"group-{local_ref}",
        members=(
            LocalClaimCanonicalizationMember(
                search_document_id=f"section-1:node-run-1:{local_ref}",
                project_id="project-1",
                document_id="document-1",
                local_ref=local_ref,
                section_id="section-1",
                node_run_id="node-run-1",
                claim=f"Claim {local_ref}",
                claim_kind="definition",
                granularity="atomic",
                triple_texts=(),
                possible_questions=(),
                scope="",
                exclusion_scope="",
                evidence_block=f"Evidence {local_ref}",
                relation_texts=(),
                search_text=f"Claim {local_ref}",
            ),
        ),
        edges=(),
        max_similarity_score=0.0,
    )


def _retrieval_result(
    *units: LocalClaimCanonicalizationUnit,
) -> DocumentLocalClaimRetrievalResult:
    return DocumentLocalClaimRetrievalResult(
        search_documents=(),
        similarity_edges=(),
        candidate_groups=(),
        canonicalization_units=units,
    )


def _service(
    *,
    retrieval_result: DocumentLocalClaimRetrievalResult,
    latest_snapshot: RegistrySnapshot | None = None,
    canonicalization_completed: bool = False,
):
    repository = FakeRepository(
        registry=_registry(),
        latest_snapshot=latest_snapshot,
        canonicalization_completed=canonicalization_completed,
    )
    retrieval = FakeRetrievalService(result=retrieval_result)
    generator = FakeRegistryMergeGenerator()
    merge_service = FakeRegistryMergeService()
    application_service = FakeRegistryApplicationService()
    id_factory = MonotonicIdFactory()

    service = FaqWorkbenchCanonicalizationBarrierService(
        repository=repository,
        local_claim_retrieval_service=retrieval,
        registry_merge_generator=generator,
        registry_merge_service=merge_service,
        registry_application_service=application_service,
        id_factory=id_factory,
    )
    return service, repository, retrieval, generator, merge_service, application_service


@pytest.mark.asyncio
async def test_canonicalization_barrier_returns_no_work_when_no_units() -> None:
    service, repository, retrieval, generator, merge_service, application_service = (
        _service(retrieval_result=_retrieval_result())
    )

    result = await service.process_document_canonicalization_barrier(
        ProcessDocumentCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-1",
        )
    )

    assert result.outcome == "no_work"
    assert result.canonicalization_unit_count == 0
    assert result.prompt_c_success_count == 0
    assert result.snapshot_apply_count == 0
    assert repository.registry_calls == 1
    assert repository.snapshot_calls == 1
    assert repository.facts_calls == 1
    assert len(retrieval.commands) == 1
    assert generator.commands == []
    assert merge_service.commands == []
    assert application_service.commands == []


@pytest.mark.asyncio
async def test_canonicalization_barrier_runs_prompt_c_persists_and_applies_snapshot_per_unit() -> (
    None
):
    service, _repository, _retrieval, generator, merge_service, application_service = (
        _service(retrieval_result=_retrieval_result(_unit("c1"), _unit("c2")))
    )

    result = await service.process_document_canonicalization_barrier(
        ProcessDocumentCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-1",
        )
    )

    assert result.outcome == "canonicalized"
    assert result.canonicalization_unit_count == 2
    assert result.prompt_c_success_count == 2
    assert result.snapshot_apply_count == 2
    assert result.latest_snapshot_id == "snapshot-2"
    assert result.latest_snapshot_sequence_number == 2

    assert [command.node_run_id for command in generator.commands] == [
        "node-run-1",
        "node-run-2",
    ]
    assert generator.commands[0].canonicalization_unit.unit_id == "unit-c1"
    assert generator.commands[1].canonicalization_unit.unit_id == "unit-c2"
    assert (
        generator.commands[0].registry_snapshot_payload["fact_registry"][
            "canonical_facts"
        ]
        == []
    )
    assert (
        generator.commands[1].registry_snapshot_payload["fact_registry"][
            "canonical_facts"
        ][0]["fact_id"]
        == "fact-1"
    )

    assert [command.node_run_id for command in merge_service.commands] == [
        "node-run-1",
        "node-run-2",
    ]
    assert [command.after_node_run_id for command in application_service.commands] == [
        "node-run-1",
        "node-run-2",
    ]
    assert application_service.commands[0].previous_snapshot_id is None
    assert application_service.commands[0].previous_snapshot_sequence_number == 0
    assert application_service.commands[1].previous_snapshot_id == "snapshot-1"
    assert application_service.commands[1].previous_snapshot_sequence_number == 1
    assert application_service.commands[0].after_section_id is None
    assert application_service.commands[1].after_section_id is None

    assert len(_repository.created_node_runs) == 1
    assert len(_repository.created_artifacts) == 1
    marker_node_run = _repository.created_node_runs[0]
    marker_artifact = _repository.created_artifacts[0]
    assert marker_node_run.node_run_id == marker_artifact.node_run_id
    assert (
        marker_artifact.metadata["contract"] == "fact_registry_canonicalization_barrier"
    )
    assert marker_artifact.metadata["status"] == "completed"
    assert marker_artifact.metadata["expected_unit_count"] == 2
    assert marker_artifact.metadata["completed_unit_count"] == 2
    assert marker_artifact.metadata["final_snapshot_id"] == "snapshot-2"


def test_canonicalization_barrier_command_validates_required_fields() -> None:
    with pytest.raises(Exception, match="project_id"):
        ProcessDocumentCanonicalizationBarrierCommand(
            project_id="",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-1",
        )

    with pytest.raises(Exception, match="worker_id"):
        ProcessDocumentCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="",
        )

    with pytest.raises(Exception, match="min_similarity_score"):
        ProcessDocumentCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-1",
            min_similarity_score=2.0,
        )


@pytest.mark.asyncio
async def test_canonicalization_barrier_is_document_level_idempotent_when_completion_marker_exists() -> (
    None
):
    service, repository, retrieval, generator, merge_service, application_service = (
        _service(
            retrieval_result=_retrieval_result(_unit("c1")),
            canonicalization_completed=True,
        )
    )

    result = await service.process_document_canonicalization_barrier(
        ProcessDocumentCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-1",
        )
    )

    assert result.outcome == "already_canonicalized"
    assert result.made_progress is False
    assert result.canonicalization_unit_count == 0
    assert result.prompt_c_success_count == 0
    assert result.snapshot_apply_count == 0

    assert repository.completion_guard_calls == 1
    assert repository.snapshot_calls == 1
    assert repository.registry_calls == 0
    assert repository.facts_calls == 0
    assert retrieval.commands == []
    assert generator.commands == []
    assert merge_service.commands == []
    assert application_service.commands == []


class FailingRegistryMergeGenerator:
    def __init__(self, error):
        self.error = error
        self.commands = []

    async def generate_registry_updates(self, command):
        self.commands.append(command)
        raise self.error


@dataclass(slots=True)
class RecordingRegistryMergeService(FakeRegistryMergeService):
    error_commands: list[object] = field(default_factory=list)

    async def persist_registry_merge_generation_error(self, command):
        self.error_commands.append(command)
        return SimpleNamespace(
            node_run=SimpleNamespace(node_run_id=command.node_run_id),
            error_artifact=SimpleNamespace(),
            lifecycle=SimpleNamespace(),
        )


@pytest.mark.asyncio
async def test_canonicalization_barrier_persists_prompt_c_generation_error() -> None:
    from src.application.ports.faq_workbench_registry_merge_generator import (
        FaqWorkbenchRegistryMergeGenerationError,
    )

    error_invocation = LlmJsonInvocationResult(
        status=LlmInvocationStatus.INVALID_JSON,
        parsed_json=None,
        raw_text="{broken json",
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
            user_message="Prompt C returned invalid JSON.",
            internal_message="Prompt C invocation returned invalid JSON.",
            cooldown_seconds=None,
        ),
    )
    error = FaqWorkbenchRegistryMergeGenerationError(error_invocation)

    repository = FakeRepository(registry=_registry())
    retrieval = FakeRetrievalService(result=_retrieval_result(_unit("c1"), _unit("c2")))
    generator = FailingRegistryMergeGenerator(error)
    merge_service = RecordingRegistryMergeService()
    application_service = FakeRegistryApplicationService()
    service = FaqWorkbenchCanonicalizationBarrierService(
        repository=repository,
        local_claim_retrieval_service=retrieval,
        registry_merge_generator=generator,
        registry_merge_service=merge_service,
        registry_application_service=application_service,
        id_factory=MonotonicIdFactory(),
    )

    result = await service.process_document_canonicalization_barrier(
        ProcessDocumentCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-1",
        )
    )

    assert result.outcome == "prompt_c_failed"
    assert result.made_progress is True
    assert result.canonicalization_unit_count == 2
    assert result.prompt_c_success_count == 0
    assert result.snapshot_apply_count == 0
    assert len(generator.commands) == 1
    assert len(merge_service.error_commands) == 1
    assert merge_service.error_commands[0].node_run_id == "node-run-1"
    assert merge_service.error_commands[0].canonicalization_unit.unit_id == "unit-c1"
    assert merge_service.error_commands[0].registry.registry_id == "registry-1"
    assert merge_service.error_commands[0].error is error
    assert application_service.commands == []
    assert repository.created_node_runs == []
    assert repository.created_artifacts == []
