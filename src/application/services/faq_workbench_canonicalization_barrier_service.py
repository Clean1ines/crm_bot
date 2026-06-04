from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.application.ports.faq_workbench_registry_merge_generator import (
    FaqWorkbenchRegistryMergeGenerationCommand,
    FaqWorkbenchRegistryMergeGenerationError,
    FaqWorkbenchRegistryMergeGeneratorPort,
)
from src.application.services.faq_workbench_local_claim_retrieval_service import (
    BuildDocumentLocalClaimRetrievalCommand,
    FaqWorkbenchLocalClaimRetrievalService,
)
from src.application.services.faq_workbench_registry_application_service import (
    ApplyFactRegistrySnapshotCommand,
    FaqWorkbenchRegistryApplicationService,
)
from src.application.services.faq_workbench_registry_merge_service import (
    FaqWorkbenchRegistryMergeService,
    PersistRegistryMergeNodeOutputCommand,
    ProcessRegistryMergeGenerationErrorCommand,
)
from src.application.services.faq_workbench_registry_materialization_service import (
    FaqWorkbenchRegistryMaterializationService,
    MaterializeFactRegistrySnapshotCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    CanonicalFact,
    DomainInvariantError,
    FactRegistry,
    JsonValue,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeKind,
    ProcessingNodeName,
    ProcessingNodeRun,
    ProcessingNodeStatus,
    RegistrySnapshot,
)


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class CanonicalizationBarrierRepositoryPort(Protocol):
    async def get_fact_registry_for_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> FactRegistry: ...

    async def get_latest_registry_snapshot(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> RegistrySnapshot | None: ...

    async def list_canonical_facts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> tuple[CanonicalFact, ...]: ...

    async def create_processing_node_run(
        self,
        node_run: ProcessingNodeRun,
    ) -> None: ...

    async def create_processing_node_artifact(
        self,
        artifact: ProcessingNodeArtifact,
    ) -> None: ...

    async def has_completed_fact_registry_canonicalization(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class ProcessDocumentCanonicalizationBarrierCommand:
    project_id: str
    document_id: str
    processing_run_id: str
    worker_id: str
    lease_seconds: int = 300
    min_similarity_score: float = 0.18

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError("canonicalization barrier requires project_id")
        if not self.document_id:
            raise DomainInvariantError("canonicalization barrier requires document_id")
        if not self.processing_run_id:
            raise DomainInvariantError(
                "canonicalization barrier requires processing_run_id"
            )
        if not self.worker_id:
            raise DomainInvariantError("canonicalization barrier requires worker_id")
        if self.lease_seconds < 1:
            raise DomainInvariantError(
                "canonicalization barrier lease_seconds must be positive"
            )
        if self.min_similarity_score < 0 or self.min_similarity_score > 1:
            raise DomainInvariantError(
                "canonicalization barrier min_similarity_score must be in [0, 1]"
            )


@dataclass(frozen=True, slots=True)
class ProcessDocumentCanonicalizationBarrierResult:
    outcome: str
    claim_count: int
    canonicalization_unit_count: int
    prompt_c_success_count: int
    snapshot_apply_count: int
    latest_snapshot_id: str | None
    latest_snapshot_sequence_number: int

    @property
    def made_progress(self) -> bool:
        return self.outcome not in {"no_work", "skip_terminal", "already_canonicalized"}


class FaqWorkbenchCanonicalizationBarrierService:
    """Document-level barrier between Prompt A section extraction and Prompt C.

    This service is the active cutover point for:

    local claim artifacts -> retrieval/clustering -> Prompt C units -> snapshots

    It intentionally does not resurrect per-section registry merge.
    """

    def __init__(
        self,
        *,
        repository: CanonicalizationBarrierRepositoryPort,
        local_claim_retrieval_service: FaqWorkbenchLocalClaimRetrievalService,
        registry_merge_generator: FaqWorkbenchRegistryMergeGeneratorPort,
        registry_merge_service: FaqWorkbenchRegistryMergeService,
        registry_application_service: FaqWorkbenchRegistryApplicationService,
        registry_materialization_service: FaqWorkbenchRegistryMaterializationService,
        id_factory: IdFactory,
    ) -> None:
        self._repository = repository
        self._local_claim_retrieval_service = local_claim_retrieval_service
        self._registry_merge_generator = registry_merge_generator
        self._registry_merge_service = registry_merge_service
        self._registry_application_service = registry_application_service
        self._registry_materialization_service = registry_materialization_service
        self._id_factory = id_factory

    async def process_document_canonicalization_barrier(
        self,
        command: ProcessDocumentCanonicalizationBarrierCommand,
    ) -> ProcessDocumentCanonicalizationBarrierResult:
        already_completed = (
            await self._repository.has_completed_fact_registry_canonicalization(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
            )
        )
        if already_completed:
            latest_snapshot = await self._repository.get_latest_registry_snapshot(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
            )
            return ProcessDocumentCanonicalizationBarrierResult(
                outcome="already_canonicalized",
                claim_count=0,
                canonicalization_unit_count=0,
                prompt_c_success_count=0,
                snapshot_apply_count=0,
                latest_snapshot_id=(
                    latest_snapshot.snapshot_id if latest_snapshot is not None else None
                ),
                latest_snapshot_sequence_number=(
                    latest_snapshot.sequence_number
                    if latest_snapshot is not None
                    else 0
                ),
            )

        registry = await self._repository.get_fact_registry_for_run(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=command.processing_run_id,
        )
        latest_snapshot = await self._repository.get_latest_registry_snapshot(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=command.processing_run_id,
        )
        canonical_facts = await self._repository.list_canonical_facts(
            project_id=command.project_id,
            document_id=command.document_id,
            processing_run_id=command.processing_run_id,
        )
        retrieval_result = await self._local_claim_retrieval_service.build_document_local_claim_retrieval(
            BuildDocumentLocalClaimRetrievalCommand(
                project_id=command.project_id,
                document_id=command.document_id,
                processing_run_id=command.processing_run_id,
                min_similarity_score=command.min_similarity_score,
            )
        )

        if retrieval_result.unit_count == 0:
            return ProcessDocumentCanonicalizationBarrierResult(
                outcome="no_work",
                claim_count=retrieval_result.claim_count,
                canonicalization_unit_count=0,
                prompt_c_success_count=0,
                snapshot_apply_count=0,
                latest_snapshot_id=(
                    latest_snapshot.snapshot_id if latest_snapshot is not None else None
                ),
                latest_snapshot_sequence_number=(
                    latest_snapshot.sequence_number
                    if latest_snapshot is not None
                    else 0
                ),
            )

        previous_snapshot_id = (
            latest_snapshot.snapshot_id if latest_snapshot is not None else None
        )
        previous_snapshot_sequence_number = (
            latest_snapshot.sequence_number if latest_snapshot is not None else 0
        )
        current_registry_snapshot_payload = self._snapshot_payload(latest_snapshot)
        current_fact_registry_payload = self._fact_registry_from_snapshot_payload(
            current_registry_snapshot_payload
        )

        prompt_c_success_count = 0
        snapshot_apply_count = 0

        for index, unit in enumerate(retrieval_result.canonicalization_units, start=1):
            node_run_id = self._id_factory.new_id("node-run")
            try:
                generation_result = (
                    await self._registry_merge_generator.generate_registry_updates(
                        FaqWorkbenchRegistryMergeGenerationCommand(
                            node_run_id=node_run_id,
                            canonicalization_unit=unit,
                            registry=registry,
                            canonical_facts=canonical_facts,
                            registry_snapshot_payload=current_registry_snapshot_payload,
                            relevant_registry_state={
                                "contract": "relevant_fact_registry_state",
                                "worker_id": command.worker_id,
                                "unit_index": index,
                                "unit_count": retrieval_result.unit_count,
                                "latest_snapshot_id": previous_snapshot_id,
                                "latest_fact_registry": current_fact_registry_payload,
                            },
                        )
                    )
                )
            except FaqWorkbenchRegistryMergeGenerationError as error:
                await self._registry_merge_service.persist_registry_merge_generation_error(
                    ProcessRegistryMergeGenerationErrorCommand(
                        node_run_id=node_run_id,
                        canonicalization_unit=unit,
                        registry=registry,
                        error=error,
                    )
                )
                return ProcessDocumentCanonicalizationBarrierResult(
                    outcome="prompt_c_failed",
                    claim_count=retrieval_result.claim_count,
                    canonicalization_unit_count=retrieval_result.unit_count,
                    prompt_c_success_count=prompt_c_success_count,
                    snapshot_apply_count=snapshot_apply_count,
                    latest_snapshot_id=previous_snapshot_id,
                    latest_snapshot_sequence_number=previous_snapshot_sequence_number,
                )
            prompt_c_success_count += 1

            persisted = (
                await self._registry_merge_service.persist_registry_merge_output(
                    PersistRegistryMergeNodeOutputCommand(
                        node_run_id=node_run_id,
                        canonicalization_unit=unit,
                        registry=registry,
                        generation_result=generation_result,
                    )
                )
            )

            applied = await self._registry_application_service.apply_fact_registry_snapshot(
                ApplyFactRegistrySnapshotCommand(
                    registry=registry,
                    fact_registry=persisted.fact_registry,
                    registry_update_summary=persisted.registry_update_summary,
                    previous_snapshot_id=previous_snapshot_id,
                    previous_snapshot_sequence_number=previous_snapshot_sequence_number,
                    after_node_run_id=persisted.node_run.node_run_id,
                    after_section_id=None,
                )
            )
            snapshot_apply_count += 1

            previous_snapshot_id = applied.snapshot.snapshot_id
            previous_snapshot_sequence_number = applied.snapshot.sequence_number
            current_fact_registry_payload = applied.fact_registry
            applied_entries_payload = applied.snapshot.entries_payload
            applied_previous_snapshot_id = (
                applied_entries_payload.get("previous_snapshot_id")
                if isinstance(applied_entries_payload, dict)
                else None
            )
            current_registry_snapshot_payload = {
                "contract": "fact_registry",
                "previous_snapshot_id": applied_previous_snapshot_id,
                "fact_registry": applied.fact_registry,
                "registry_update_summary": applied.registry_update_summary,
            }

        if previous_snapshot_id is None:
            raise DomainInvariantError(
                "canonicalization barrier completed without final registry snapshot"
            )

        final_snapshot = applied.snapshot
        await self._registry_materialization_service.materialize_fact_registry_snapshot(
            MaterializeFactRegistrySnapshotCommand(snapshot=final_snapshot)
        )

        await self._persist_canonicalization_barrier_completion_marker(
            command=command,
            expected_unit_count=retrieval_result.unit_count,
            completed_unit_count=prompt_c_success_count,
            final_snapshot_id=previous_snapshot_id,
            final_snapshot_sequence_number=previous_snapshot_sequence_number,
            claim_count=retrieval_result.claim_count,
            snapshot_apply_count=snapshot_apply_count,
        )

        return ProcessDocumentCanonicalizationBarrierResult(
            outcome="canonicalized",
            claim_count=retrieval_result.claim_count,
            canonicalization_unit_count=retrieval_result.unit_count,
            prompt_c_success_count=prompt_c_success_count,
            snapshot_apply_count=snapshot_apply_count,
            latest_snapshot_id=previous_snapshot_id,
            latest_snapshot_sequence_number=previous_snapshot_sequence_number,
        )

    async def _persist_canonicalization_barrier_completion_marker(
        self,
        *,
        command: ProcessDocumentCanonicalizationBarrierCommand,
        expected_unit_count: int,
        completed_unit_count: int,
        final_snapshot_id: str,
        final_snapshot_sequence_number: int,
        claim_count: int,
        snapshot_apply_count: int,
    ) -> None:
        if expected_unit_count != completed_unit_count:
            raise DomainInvariantError(
                "canonicalization barrier marker requires all units completed"
            )
        if not final_snapshot_id:
            raise DomainInvariantError(
                "canonicalization barrier marker requires final_snapshot_id"
            )

        marker_node_run_id = self._id_factory.new_id("barrier-marker")
        marker_artifact_id = self._id_factory.new_id("artifact")

        marker_node_run = ProcessingNodeRun(
            node_run_id=marker_node_run_id,
            processing_run_id=command.processing_run_id,
            project_id=command.project_id,
            document_id=command.document_id,
            section_id=None,
            node_name=ProcessingNodeName.REGISTRY_SNAPSHOT,
            node_kind=ProcessingNodeKind.CONTROL_FLOW,
            status=ProcessingNodeStatus.COMPLETED,
            output_snapshot_id=marker_artifact_id,
        )
        marker_artifact = ProcessingNodeArtifact(
            artifact_id=marker_artifact_id,
            node_run_id=marker_node_run_id,
            processing_run_id=command.processing_run_id,
            project_id=command.project_id,
            document_id=command.document_id,
            section_id=None,
            artifact_type=ProcessingNodeArtifactType.DETERMINISTIC_RESULT,
            payload_json={
                "contract": "fact_registry_canonicalization_barrier",
                "status": "completed",
                "expected_unit_count": expected_unit_count,
                "completed_unit_count": completed_unit_count,
                "final_snapshot_id": final_snapshot_id,
                "final_snapshot_sequence_number": final_snapshot_sequence_number,
                "claim_count": claim_count,
                "snapshot_apply_count": snapshot_apply_count,
            },
            schema_version=1,
            created_at=None,
            metadata={
                "contract": "fact_registry_canonicalization_barrier",
                "status": "completed",
                "expected_unit_count": expected_unit_count,
                "completed_unit_count": completed_unit_count,
                "final_snapshot_id": final_snapshot_id,
                "final_snapshot_sequence_number": final_snapshot_sequence_number,
                "claim_count": claim_count,
                "snapshot_apply_count": snapshot_apply_count,
                "worker_id": command.worker_id,
            },
        )
        await self._repository.create_processing_node_run(marker_node_run)
        await self._repository.create_processing_node_artifact(marker_artifact)

    def _snapshot_payload(
        self,
        snapshot: RegistrySnapshot | None,
    ) -> dict[str, JsonValue]:
        if snapshot is None:
            return {
                "contract": "fact_registry",
                "previous_snapshot_id": None,
                "fact_registry": {
                    "version": 1,
                    "canonical_facts": [],
                    "fact_relations": [],
                },
                "registry_update_summary": {
                    "created_fact_count": 0,
                    "updated_fact_count": 0,
                    "created_relation_count": 0,
                    "notes": [],
                },
            }

        entries_payload = snapshot.entries_payload
        if isinstance(entries_payload, dict):
            return dict(entries_payload)

        raise DomainInvariantError(
            "latest registry snapshot entries_payload must be object"
        )

    def _fact_registry_from_snapshot_payload(
        self,
        payload: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        fact_registry = payload.get("fact_registry")
        if isinstance(fact_registry, dict):
            return fact_registry
        if isinstance(payload.get("canonical_facts"), list) and isinstance(
            payload.get("fact_relations"), list
        ):
            return payload
        return {
            "version": 1,
            "canonical_facts": [],
            "fact_relations": [],
        }


__all__ = [
    "CanonicalizationBarrierRepositoryPort",
    "FaqWorkbenchCanonicalizationBarrierService",
    "ProcessDocumentCanonicalizationBarrierCommand",
    "ProcessDocumentCanonicalizationBarrierResult",
]
