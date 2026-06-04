from __future__ import annotations
from src.domain.project_plane.llm_routing import LlmInvocationStatus

from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import count
from typing import Protocol

from src.application.ports.faq_workbench_claim_observations_generator import (
    ClaimObservation,
)
from src.application.ports.knowledge_workbench import (
    KnowledgeWorkbenchClaimObservationsRepositoryPort,
)
from src.domain.project_plane.llm_routing import LlmJsonInvocationResult

from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DomainInvariantError,
    JsonValue,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeKind,
    ProcessingNodeName,
    ProcessingNodeRun,
    ProcessingNodeStatus,
    FactRegistry,
    RegistrySnapshot,
    KnowledgeDocumentStatus,
    ProcessingRunStatus,
    ResumePolicy,
)


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(slots=True)
class MonotonicIdFactory:
    _counter: count[int]

    @classmethod
    def create(cls) -> MonotonicIdFactory:
        return cls(_counter=count(1))

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._counter)}"


@dataclass(frozen=True, slots=True)
class ProcessClaimObservationsCommand:
    section: DocumentSection
    registry: FactRegistry
    registry_snapshot_payload: JsonValue
    claim_observations: tuple[ClaimObservation, ...]
    model_name: str = "parsed_without_provider_call"
    prompt_version: str = "faq_claim_observations.v1"
    model_provider: str | None = None
    api_key_slot: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    raw_llm_output: str | None = None
    raw_payload: JsonValue | None = None
    invocation_status: str | None = None
    route_attempts: tuple[dict[str, JsonValue], ...] = ()
    llm_warnings: tuple[str, ...] = ()
    llm_metrics: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClaimObservationsGenerationErrorLifecycleTransition:
    document_status: KnowledgeDocumentStatus
    processing_run_status: ProcessingRunStatus
    resume_policy: ResumePolicy
    error_kind: str
    user_message: str
    internal_error: str


@dataclass(frozen=True, slots=True)
class ProcessClaimObservationsGenerationErrorCommand:
    section: DocumentSection
    registry: FactRegistry
    registry_snapshot_payload: JsonValue
    invocation: LlmJsonInvocationResult
    prompt_version: str = "faq_claim_observations.v1"


@dataclass(frozen=True, slots=True)
class ProcessClaimObservationsGenerationErrorResult:
    node_run: ProcessingNodeRun
    error_artifact: ProcessingNodeArtifact


@dataclass(frozen=True, slots=True)
class ProcessClaimObservationsResult:
    node_run: ProcessingNodeRun
    input_artifact: ProcessingNodeArtifact
    output_artifact: ProcessingNodeArtifact
    claim_observations: tuple[ClaimObservation, ...]
    snapshot: RegistrySnapshot
    raw_llm_artifact: ProcessingNodeArtifact | None = None

    @property
    def findings(self) -> tuple[ClaimObservation, ...]:
        return self.claim_observations

    @property
    def claim_observation_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for index, observation in enumerate(self.claim_observations):
            local_ref = observation.get("local_ref")
            ids.append(str(local_ref) if local_ref else f"c{index + 1}")
        return tuple(ids)


class FaqWorkbenchClaimObservationsService:
    def __init__(
        self,
        repository: KnowledgeWorkbenchClaimObservationsRepositoryPort,
        *,
        id_factory: IdFactory,
        time_provider: TimeProvider | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._time_provider = time_provider or SystemTimeProvider()

    def _claim_observations_generation_error_lifecycle(
        self,
        *,
        invocation: LlmJsonInvocationResult,
        fallback_user_message: str,
        fallback_internal_message: str,
    ) -> ClaimObservationsGenerationErrorLifecycleTransition:
        status = invocation.status
        failure = invocation.failure

        user_message = (
            failure.user_message
            if failure is not None and failure.user_message
            else fallback_user_message
        )
        internal_error = (
            failure.internal_message
            if failure is not None and failure.internal_message
            else fallback_internal_message
        )

        if status is LlmInvocationStatus.RATE_LIMITED:
            return ClaimObservationsGenerationErrorLifecycleTransition(
                document_status=KnowledgeDocumentStatus.PAUSED,
                processing_run_status=ProcessingRunStatus.PAUSED_QUOTA,
                resume_policy=ResumePolicy.AUTO_ALLOWED,
                error_kind="groq_rate_limit",
                user_message=user_message,
                internal_error=internal_error,
            )

        if status is LlmInvocationStatus.DAILY_LIMITED:
            return ClaimObservationsGenerationErrorLifecycleTransition(
                document_status=KnowledgeDocumentStatus.PAUSED,
                processing_run_status=ProcessingRunStatus.PAUSED_QUOTA,
                resume_policy=ResumePolicy.AUTO_ALLOWED,
                error_kind="groq_daily_limit",
                user_message=user_message,
                internal_error=internal_error,
            )

        if status in {
            LlmInvocationStatus.PROVIDER_ERROR,
            LlmInvocationStatus.NETWORK_ERROR,
        }:
            return ClaimObservationsGenerationErrorLifecycleTransition(
                document_status=KnowledgeDocumentStatus.PAUSED,
                processing_run_status=ProcessingRunStatus.PAUSED_PROVIDER,
                resume_policy=ResumePolicy.AUTO_ALLOWED,
                error_kind="provider_error",
                user_message=user_message,
                internal_error=internal_error,
            )

        if status is LlmInvocationStatus.INVALID_JSON:
            return ClaimObservationsGenerationErrorLifecycleTransition(
                document_status=KnowledgeDocumentStatus.FAILED,
                processing_run_status=ProcessingRunStatus.FAILED_VALIDATION,
                resume_policy=ResumePolicy.FORBIDDEN,
                error_kind="failed_validation",
                user_message=user_message,
                internal_error=internal_error,
            )

        if status in {
            LlmInvocationStatus.REQUEST_TOO_LARGE,
            LlmInvocationStatus.OUTPUT_TOO_LARGE,
        }:
            return ClaimObservationsGenerationErrorLifecycleTransition(
                document_status=KnowledgeDocumentStatus.FAILED,
                processing_run_status=ProcessingRunStatus.FAILED_FATAL,
                resume_policy=ResumePolicy.FORBIDDEN,
                error_kind="failed_fatal",
                user_message=user_message,
                internal_error=internal_error,
            )

        return ClaimObservationsGenerationErrorLifecycleTransition(
            document_status=KnowledgeDocumentStatus.FAILED,
            processing_run_status=ProcessingRunStatus.FAILED_FATAL,
            resume_policy=ResumePolicy.FORBIDDEN,
            error_kind="failed_fatal",
            user_message=user_message,
            internal_error=internal_error,
        )

    async def persist_claim_observations_generation_error(
        self,
        command: ProcessClaimObservationsGenerationErrorCommand,
    ) -> ProcessClaimObservationsGenerationErrorResult:
        if not command.section.section_id:
            raise DomainInvariantError("claim observations error requires section_id")
        if command.section.project_id != command.registry.project_id:
            raise DomainInvariantError("claim observations error project mismatch")
        if command.section.document_id != command.registry.document_id:
            raise DomainInvariantError("claim observations error document mismatch")

        now = self._time_provider.now()
        node_run_id = self._id_factory.new_id("node-run")
        artifact_id = self._id_factory.new_id("artifact")

        invocation = command.invocation
        failure = invocation.failure
        selected_attempt = invocation.attempts[-1]
        error_kind = (
            failure.error_kind if failure is not None else invocation.status.value
        )
        user_message = (
            failure.user_message
            if failure is not None
            else "Не удалось обработать секцию через ИИ. Можно повторить позже."
        )
        internal_message = (
            failure.internal_message
            if failure is not None
            else f"claim observations invocation failed: {invocation.status.value}"
        )

        lifecycle = self._claim_observations_generation_error_lifecycle(
            invocation=invocation,
            fallback_user_message=user_message,
            fallback_internal_message=internal_message,
        )

        node_run = ProcessingNodeRun(
            node_run_id=node_run_id,
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            section_id=command.section.section_id,
            node_name=ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS,
            node_kind=ProcessingNodeKind.LLM_PROMPT,
            status=ProcessingNodeStatus.FAILED,
            started_at=now,
            completed_at=now,
            model_name=selected_attempt.model,
            model_provider=selected_attempt.provider_id,
            groq_key_slot=selected_attempt.api_key_slot,
            prompt_tokens=invocation.token_usage.prompt_tokens,
            completion_tokens=invocation.token_usage.completion_tokens,
            total_tokens=invocation.token_usage.total_tokens,
            error_kind=error_kind,
            error_message_user=user_message,
            error_message_internal=internal_message,
        )

        route_attempts: list[JsonValue] = [
            {
                "provider_id": attempt.provider_id,
                "model": attempt.model,
                "api_key_slot": attempt.api_key_slot,
                "attempt_index": attempt.attempt_index,
                "status": attempt.status.value,
                "error_kind": attempt.error_kind,
                "cooldown_seconds": attempt.cooldown_seconds,
            }
            for attempt in invocation.attempts
        ]

        error_payload: JsonValue = {
            "node": ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS.value,
            "prompt_version": command.prompt_version,
            "invocation_status": invocation.status.value,
            "error_kind": error_kind,
            "user_message": user_message,
            "internal_message": internal_message,
            "cooldown_seconds": (
                failure.cooldown_seconds if failure is not None else None
            ),
            "raw_text": invocation.raw_text,
            "route_attempts": route_attempts,
            "section": {
                "section_id": command.section.section_id,
                "section_key": command.section.section_key,
                "section_index": command.section.section_index,
                "heading_path": list(command.section.heading_path),
                "title": command.section.title,
                "source_refs": list(command.section.source_refs),
                "source_chunk_indexes": list(command.section.source_chunk_indexes),
            },
            "registry_snapshot": command.registry_snapshot_payload,
        }

        error_artifact = ProcessingNodeArtifact(
            artifact_id=artifact_id,
            node_run_id=node_run_id,
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            section_id=command.section.section_id,
            artifact_type=ProcessingNodeArtifactType.ERROR_REPORT,
            payload_json=error_payload,
            schema_version=1,
            metadata={
                "model_name": selected_attempt.model,
                "model_provider": selected_attempt.provider_id,
                "api_key_slot": selected_attempt.api_key_slot,
                "prompt_tokens": invocation.token_usage.prompt_tokens,
                "completion_tokens": invocation.token_usage.completion_tokens,
                "total_tokens": invocation.token_usage.total_tokens,
                "invocation_status": invocation.status.value,
                "error_kind": error_kind,
            },
            created_at=now,
        )

        await self._repository.create_processing_node_run(node_run)
        await self._repository.create_processing_node_artifact(error_artifact)
        await self._repository.sync_processing_run_llm_usage_totals(
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            processing_run_id=command.registry.processing_run_id,
        )
        await self._repository.persist_claim_observations_generation_error_lifecycle(
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            processing_run_id=command.registry.processing_run_id,
            document_status=lifecycle.document_status,
            processing_run_status=lifecycle.processing_run_status,
            resume_policy=lifecycle.resume_policy,
            error_kind=lifecycle.error_kind,
            error_report_id=artifact_id,
            user_message=lifecycle.user_message,
            internal_error=lifecycle.internal_error,
        )

        return ProcessClaimObservationsGenerationErrorResult(
            node_run=node_run,
            error_artifact=error_artifact,
        )

    async def persist_claim_observations(
        self,
        command: ProcessClaimObservationsCommand,
    ) -> ProcessClaimObservationsResult:
        self._validate_command(command)

        now = self._time_provider.now()
        total_tokens = (
            command.total_tokens or command.prompt_tokens + command.completion_tokens
        )

        node_run_id = self._id_factory.new_id("node-run")
        input_artifact_id = self._id_factory.new_id("artifact")
        output_artifact_id = self._id_factory.new_id("artifact")
        raw_llm_artifact_id = (
            self._id_factory.new_id("artifact")
            if command.raw_llm_output is not None
            else None
        )
        snapshot_id = self._id_factory.new_id("registry-snapshot")

        node_run = ProcessingNodeRun(
            node_run_id=node_run_id,
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            section_id=command.section.section_id,
            node_name=ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS,
            node_kind=ProcessingNodeKind.LLM_PROMPT,
            status=ProcessingNodeStatus.COMPLETED,
            started_at=now,
            completed_at=now,
            model_name=command.model_name,
            model_provider=command.model_provider,
            groq_key_slot=command.api_key_slot,
            prompt_tokens=command.prompt_tokens,
            completion_tokens=command.completion_tokens,
            total_tokens=total_tokens,
        )

        input_payload: JsonValue = {
            "node": ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS.value,
            "prompt_version": command.prompt_version,
            "section": {
                "section_id": command.section.section_id,
                "section_key": command.section.section_key,
                "section_index": command.section.section_index,
                "heading_path": list(command.section.heading_path),
                "title": command.section.title,
                "raw_text": command.section.raw_text,
                "source_refs": list(command.section.source_refs),
                "source_chunk_indexes": list(command.section.source_chunk_indexes),
            },
            "registry_snapshot": command.registry_snapshot_payload,
        }

        input_artifact = ProcessingNodeArtifact(
            artifact_id=input_artifact_id,
            node_run_id=node_run_id,
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            section_id=command.section.section_id,
            artifact_type=ProcessingNodeArtifactType.INPUT_SNAPSHOT,
            payload_json=input_payload,
            schema_version=1,
            created_at=now,
        )

        claim_observations = command.claim_observations

        output_payload: JsonValue = {
            "node": ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS.value,
            "prompt_version": command.prompt_version,
            "claim_observations": list(claim_observations),
            "warnings": list(command.llm_warnings),
            "metrics": {
                "claim_observation_count": len(claim_observations),
                "new_count": sum(
                    1
                    for item in claim_observations
                    if item.get("suggested_registry_action") == "create_new_claim"
                ),
                "existing_update_count": sum(
                    1
                    for item in claim_observations
                    if item.get("suggested_registry_action")
                    in {
                        "merge_into_known",
                        "add_evidence_to_known",
                        "extend_known",
                        "refine_known",
                    }
                ),
                **command.llm_metrics,
            },
        }

        output_artifact = ProcessingNodeArtifact(
            artifact_id=output_artifact_id,
            node_run_id=node_run_id,
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            section_id=command.section.section_id,
            artifact_type=ProcessingNodeArtifactType.PARSED_LLM_OUTPUT,
            payload_json=output_payload,
            schema_version=1,
            created_at=now,
        )

        raw_llm_artifact = (
            ProcessingNodeArtifact(
                artifact_id=raw_llm_artifact_id,
                node_run_id=node_run_id,
                processing_run_id=command.registry.processing_run_id,
                project_id=command.registry.project_id,
                document_id=command.registry.document_id,
                section_id=command.section.section_id,
                artifact_type=ProcessingNodeArtifactType.RAW_LLM_OUTPUT,
                payload_json={
                    "node": ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS.value,
                    "invocation_status": command.invocation_status or "unknown",
                    "raw_text": command.raw_llm_output,
                    "raw_payload": command.raw_payload,
                    "route_attempts": [dict(item) for item in command.route_attempts],
                    "warnings": list(command.llm_warnings),
                    "metrics": command.llm_metrics,
                },
                schema_version=1,
                metadata={
                    "model_name": command.model_name,
                    "model_provider": command.model_provider,
                    "api_key_slot": command.api_key_slot,
                    "prompt_tokens": command.prompt_tokens,
                    "completion_tokens": command.completion_tokens,
                    "total_tokens": total_tokens,
                },
                created_at=now,
            )
            if raw_llm_artifact_id is not None
            else None
        )

        snapshot = RegistrySnapshot(
            snapshot_id=snapshot_id,
            registry_id=command.registry.registry_id,
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            after_section_id=command.section.section_id,
            after_node_run_id=node_run_id,
            sequence_number=command.registry.version + 1,
            entries_payload=command.registry_snapshot_payload,
            relations_payload={"relations": []},
            entry_count=0,
            relation_count=0,
            claim_observation_count=len(claim_observations),
            update_count=0,
            created_at=now,
        )

        await self._repository.create_processing_node_run(node_run)
        await self._repository.create_processing_node_artifact(input_artifact)
        if raw_llm_artifact is not None:
            await self._repository.create_processing_node_artifact(raw_llm_artifact)
        await self._repository.create_processing_node_artifact(output_artifact)
        await self._repository.create_registry_snapshot(snapshot)
        await self._repository.sync_processing_run_llm_usage_totals(
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            processing_run_id=command.registry.processing_run_id,
        )

        return ProcessClaimObservationsResult(
            node_run=node_run,
            input_artifact=input_artifact,
            output_artifact=output_artifact,
            claim_observations=claim_observations,
            snapshot=snapshot,
            raw_llm_artifact=raw_llm_artifact,
        )

    def _validate_command(self, command: ProcessClaimObservationsCommand) -> None:
        if command.section.project_id != command.registry.project_id:
            raise DomainInvariantError("section and registry project_id mismatch")
        if command.section.document_id != command.registry.document_id:
            raise DomainInvariantError("section and registry document_id mismatch")
        if command.registry.status.value in {"deleted", "invalidated"}:
            raise DomainInvariantError(
                "cannot process claim observations for deleted/invalidated registry"
            )
