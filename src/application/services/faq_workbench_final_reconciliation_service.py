from __future__ import annotations
from src.domain.project_plane.llm_routing import LlmJsonInvocationResult
from src.domain.project_plane.llm_routing import LlmInvocationStatus

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from src.application.ports.faq_workbench_final_reconciliation_generator import (
    FaqWorkbenchFinalReconciliationGenerationResult,
    FaqWorkbenchFinalReconciliationGenerationError,
)
from src.application.ports.knowledge_workbench import (
    KnowledgeWorkbenchRegistryApplicationRepositoryPort,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeKind,
    ProcessingNodeName,
    ProcessingNodeRun,
    ProcessingNodeStatus,
    RegistrySnapshot,
    JsonValue,
    KnowledgeDocumentStatus,
    ProcessingRunStatus,
    ResumePolicy,
)
from src.domain.project_plane.llm_routing import LlmRouteAttemptStatus


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class FinalReconciliationGenerationErrorLifecycleTransition:
    document_status: KnowledgeDocumentStatus
    processing_run_status: ProcessingRunStatus
    resume_policy: ResumePolicy
    error_kind: str
    user_message: str
    internal_error: str


@dataclass(frozen=True, slots=True)
class ProcessFinalReconciliationGenerationErrorCommand:
    node_run_id: str
    registry_snapshot: RegistrySnapshot
    error: FaqWorkbenchFinalReconciliationGenerationError
    prompt_version: str = "faq_surface_final_reconciliation.v1"


@dataclass(frozen=True, slots=True)
class ProcessFinalReconciliationGenerationErrorResult:
    node_run: ProcessingNodeRun
    error_artifact: ProcessingNodeArtifact
    lifecycle: FinalReconciliationGenerationErrorLifecycleTransition


@dataclass(frozen=True, slots=True)
class PersistFinalReconciliationNodeOutputCommand:
    node_run_id: str
    registry_snapshot: RegistrySnapshot
    generation_result: FaqWorkbenchFinalReconciliationGenerationResult
    prompt_version: str = "faq_surface_final_reconciliation.v1"


@dataclass(frozen=True, slots=True)
class PersistFinalReconciliationNodeOutputResult:
    node_run: ProcessingNodeRun
    raw_llm_artifact: ProcessingNodeArtifact
    parsed_llm_artifact: ProcessingNodeArtifact


class FaqWorkbenchFinalReconciliationService:
    def __init__(
        self,
        repository: KnowledgeWorkbenchRegistryApplicationRepositoryPort,
        *,
        id_factory: IdFactory,
        time_provider: TimeProvider | None = None,
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._time_provider = time_provider or SystemTimeProvider()

    async def persist_final_reconciliation_generation_error(
        self,
        command: ProcessFinalReconciliationGenerationErrorCommand,
    ) -> ProcessFinalReconciliationGenerationErrorResult:
        self._validate_error_command(command)

        now = self._time_provider.now()
        artifact_id = self._id_factory.new_id("artifact")
        invocation = command.error.result
        selected_attempt = self._selected_llm_attempt(invocation.attempts)
        failure = invocation.failure

        user_message = (
            failure.user_message
            if failure is not None
            else "Не удалось выполнить финальную сверку знаний через ИИ. Можно повторить позже."
        )
        internal_message = (
            failure.internal_message
            if failure is not None
            else f"final reconciliation invocation failed: {invocation.status.value}"
        )
        lifecycle = self._final_reconciliation_generation_error_lifecycle(
            invocation=invocation,
            fallback_user_message=user_message,
            fallback_internal_message=internal_message,
        )

        prompt_tokens = invocation.token_usage.prompt_tokens
        completion_tokens = invocation.token_usage.completion_tokens
        total_tokens = prompt_tokens + completion_tokens

        node_run = ProcessingNodeRun(
            node_run_id=command.node_run_id,
            processing_run_id=command.registry_snapshot.processing_run_id,
            project_id=command.registry_snapshot.project_id,
            document_id=command.registry_snapshot.document_id,
            section_id=None,
            node_name=ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION,
            node_kind=ProcessingNodeKind.LLM_PROMPT,
            status=ProcessingNodeStatus.FAILED,
            output_snapshot_id=artifact_id,
            started_at=now,
            completed_at=now,
            model_name=selected_attempt["model"],
            model_provider=selected_attempt["provider_id"],
            groq_key_slot=selected_attempt["api_key_slot"],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            error_kind=lifecycle.error_kind,
            error_message_user=lifecycle.user_message,
            error_message_internal=lifecycle.internal_error,
        )
        error_artifact = ProcessingNodeArtifact(
            artifact_id=artifact_id,
            node_run_id=command.node_run_id,
            processing_run_id=command.registry_snapshot.processing_run_id,
            project_id=command.registry_snapshot.project_id,
            document_id=command.registry_snapshot.document_id,
            section_id=None,
            artifact_type=ProcessingNodeArtifactType.ERROR_REPORT,
            payload_json=self._final_reconciliation_error_payload(
                command=command,
                invocation=invocation,
                lifecycle=lifecycle,
            ),
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION.value,
                "prompt_version": command.prompt_version,
                "invocation_status": invocation.status.value,
                "error_kind": lifecycle.error_kind,
                "snapshot_id": command.registry_snapshot.snapshot_id,
            },
        )

        await self._repository.create_processing_node_run(node_run)
        await self._repository.create_processing_node_artifact(error_artifact)
        await self._repository.sync_processing_run_llm_usage_totals(
            project_id=command.registry_snapshot.project_id,
            document_id=command.registry_snapshot.document_id,
            processing_run_id=command.registry_snapshot.processing_run_id,
        )
        await self._repository.persist_final_reconciliation_generation_error_lifecycle(
            project_id=command.registry_snapshot.project_id,
            document_id=command.registry_snapshot.document_id,
            processing_run_id=command.registry_snapshot.processing_run_id,
            node_run_id=command.node_run_id,
            document_status=lifecycle.document_status,
            processing_run_status=lifecycle.processing_run_status,
            resume_policy=lifecycle.resume_policy,
            error_kind=lifecycle.error_kind,
            user_message=lifecycle.user_message,
            internal_error=lifecycle.internal_error,
        )

        return ProcessFinalReconciliationGenerationErrorResult(
            node_run=node_run,
            error_artifact=error_artifact,
            lifecycle=lifecycle,
        )

    async def persist_final_reconciliation_output(
        self,
        command: PersistFinalReconciliationNodeOutputCommand,
    ) -> PersistFinalReconciliationNodeOutputResult:
        self._validate_command(command)

        now = self._time_provider.now()
        raw_artifact_id = self._id_factory.new_id("artifact")
        parsed_artifact_id = self._id_factory.new_id("artifact")

        invocation = command.generation_result.invocation
        selected_attempt = self._selected_llm_attempt(invocation.attempts)
        prompt_tokens = invocation.token_usage.prompt_tokens
        completion_tokens = invocation.token_usage.completion_tokens
        total_tokens = prompt_tokens + completion_tokens

        node_run = ProcessingNodeRun(
            node_run_id=command.node_run_id,
            processing_run_id=command.registry_snapshot.processing_run_id,
            project_id=command.registry_snapshot.project_id,
            document_id=command.registry_snapshot.document_id,
            section_id=None,
            node_name=ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION,
            node_kind=ProcessingNodeKind.LLM_PROMPT,
            status=ProcessingNodeStatus.COMPLETED,
            output_snapshot_id=parsed_artifact_id,
            started_at=now,
            completed_at=now,
            model_name=selected_attempt["model"],
            model_provider=selected_attempt["provider_id"],
            groq_key_slot=selected_attempt["api_key_slot"],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

        raw_llm_artifact = ProcessingNodeArtifact(
            artifact_id=raw_artifact_id,
            node_run_id=command.node_run_id,
            processing_run_id=command.registry_snapshot.processing_run_id,
            project_id=command.registry_snapshot.project_id,
            document_id=command.registry_snapshot.document_id,
            section_id=None,
            artifact_type=ProcessingNodeArtifactType.RAW_LLM_OUTPUT,
            payload_json=command.generation_result.raw_output_artifact_payload,
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION.value,
                "prompt_version": command.prompt_version,
                "invocation_status": invocation.status.value,
                "snapshot_id": command.registry_snapshot.snapshot_id,
            },
        )
        parsed_llm_artifact = ProcessingNodeArtifact(
            artifact_id=parsed_artifact_id,
            node_run_id=command.node_run_id,
            processing_run_id=command.registry_snapshot.processing_run_id,
            project_id=command.registry_snapshot.project_id,
            document_id=command.registry_snapshot.document_id,
            section_id=None,
            artifact_type=ProcessingNodeArtifactType.PARSED_LLM_OUTPUT,
            payload_json=command.generation_result.parsed_output_artifact_payload,
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION.value,
                "prompt_version": command.prompt_version,
                "snapshot_id": command.registry_snapshot.snapshot_id,
                "surface_adjustment_count": (
                    command.generation_result.surface_adjustment_count
                ),
                "relation_count": command.generation_result.relation_count,
                "merge_decision_count": command.generation_result.merge_decision_count,
                "suggestion_count": command.generation_result.suggestion_count,
            },
        )

        await self._repository.create_processing_node_run(node_run)
        await self._repository.create_processing_node_artifact(raw_llm_artifact)
        await self._repository.create_processing_node_artifact(parsed_llm_artifact)
        await self._repository.sync_processing_run_llm_usage_totals(
            project_id=command.registry_snapshot.project_id,
            document_id=command.registry_snapshot.document_id,
            processing_run_id=command.registry_snapshot.processing_run_id,
        )

        return PersistFinalReconciliationNodeOutputResult(
            node_run=node_run,
            raw_llm_artifact=raw_llm_artifact,
            parsed_llm_artifact=parsed_llm_artifact,
        )

    def _validate_error_command(
        self,
        command: ProcessFinalReconciliationGenerationErrorCommand,
    ) -> None:
        if not command.node_run_id:
            raise DomainInvariantError(
                "final reconciliation error requires node_run_id"
            )
        if not command.registry_snapshot.snapshot_id:
            raise DomainInvariantError(
                "final reconciliation error requires registry snapshot"
            )
        if not command.registry_snapshot.processing_run_id:
            raise DomainInvariantError(
                "final reconciliation error requires processing_run_id"
            )

    def _final_reconciliation_generation_error_lifecycle(
        self,
        *,
        invocation: LlmJsonInvocationResult,
        fallback_user_message: str,
        fallback_internal_message: str,
    ) -> FinalReconciliationGenerationErrorLifecycleTransition:
        failure = invocation.failure
        error_kind = (
            failure.error_kind if failure is not None else invocation.status.value
        )
        user_message = (
            failure.user_message if failure is not None else fallback_user_message
        )
        internal_error = (
            failure.internal_message
            if failure is not None
            else fallback_internal_message
        )

        if invocation.status in {
            LlmInvocationStatus.DAILY_LIMITED,
            LlmInvocationStatus.RATE_LIMITED,
        }:
            return FinalReconciliationGenerationErrorLifecycleTransition(
                document_status=KnowledgeDocumentStatus.PAUSED,
                processing_run_status=ProcessingRunStatus.PAUSED_QUOTA,
                resume_policy=ResumePolicy.AUTO_ALLOWED,
                error_kind=error_kind,
                user_message=user_message,
                internal_error=internal_error,
            )

        if invocation.status in {
            LlmInvocationStatus.PROVIDER_ERROR,
            LlmInvocationStatus.NETWORK_ERROR,
        }:
            return FinalReconciliationGenerationErrorLifecycleTransition(
                document_status=KnowledgeDocumentStatus.PAUSED,
                processing_run_status=ProcessingRunStatus.PAUSED_PROVIDER,
                resume_policy=ResumePolicy.AUTO_ALLOWED,
                error_kind=error_kind,
                user_message=user_message,
                internal_error=internal_error,
            )

        if invocation.status is LlmInvocationStatus.INVALID_JSON:
            return FinalReconciliationGenerationErrorLifecycleTransition(
                document_status=KnowledgeDocumentStatus.FAILED,
                processing_run_status=ProcessingRunStatus.FAILED_VALIDATION,
                resume_policy=ResumePolicy.FORBIDDEN,
                error_kind="failed_validation",
                user_message=user_message,
                internal_error=internal_error,
            )

        if invocation.status in {
            LlmInvocationStatus.REQUEST_TOO_LARGE,
            LlmInvocationStatus.OUTPUT_TOO_LARGE,
        }:
            return FinalReconciliationGenerationErrorLifecycleTransition(
                document_status=KnowledgeDocumentStatus.FAILED,
                processing_run_status=ProcessingRunStatus.FAILED_FATAL,
                resume_policy=ResumePolicy.FORBIDDEN,
                error_kind="failed_fatal",
                user_message=user_message,
                internal_error=internal_error,
            )

        return FinalReconciliationGenerationErrorLifecycleTransition(
            document_status=KnowledgeDocumentStatus.FAILED,
            processing_run_status=ProcessingRunStatus.FAILED_FATAL,
            resume_policy=ResumePolicy.FORBIDDEN,
            error_kind="failed_fatal",
            user_message=user_message,
            internal_error=internal_error,
        )

    def _final_reconciliation_error_payload(
        self,
        *,
        command: ProcessFinalReconciliationGenerationErrorCommand,
        invocation: LlmJsonInvocationResult,
        lifecycle: FinalReconciliationGenerationErrorLifecycleTransition,
    ) -> JsonValue:
        return {
            "node": ProcessingNodeName.FAQ_SURFACE_FINAL_RECONCILIATION.value,
            "prompt_version": command.prompt_version,
            "snapshot_id": command.registry_snapshot.snapshot_id,
            "error_kind": lifecycle.error_kind,
            "user_message": lifecycle.user_message,
            "internal_error": lifecycle.internal_error,
            "invocation_status": invocation.status.value,
            "raw_text": invocation.raw_text,
            "token_usage": {
                "prompt_tokens": invocation.token_usage.prompt_tokens,
                "completion_tokens": invocation.token_usage.completion_tokens,
                "total_tokens": (
                    invocation.token_usage.prompt_tokens
                    + invocation.token_usage.completion_tokens
                ),
            },
            "route_attempts": self._route_attempts_payload(invocation.attempts),
        }

    def _route_attempts_payload(self, attempts: tuple[object, ...]) -> JsonValue:
        return [
            {
                "provider_id": self._string_or_none(
                    getattr(attempt, "provider_id", None)
                ),
                "model": self._string_or_none(getattr(attempt, "model", None)),
                "api_key_slot": self._string_or_none(
                    getattr(attempt, "api_key_slot", None)
                ),
                "attempt_index": getattr(attempt, "attempt_index", None),
                "status": getattr(getattr(attempt, "status", None), "value", None),
                "error_kind": self._string_or_none(
                    getattr(attempt, "error_kind", None)
                ),
                "cooldown_seconds": getattr(attempt, "cooldown_seconds", None),
            }
            for attempt in attempts
        ]

    def _validate_command(
        self,
        command: PersistFinalReconciliationNodeOutputCommand,
    ) -> None:
        if not command.node_run_id:
            raise DomainInvariantError(
                "final reconciliation output requires node_run_id"
            )
        if not command.registry_snapshot.snapshot_id:
            raise DomainInvariantError(
                "final reconciliation output requires registry snapshot"
            )

    def _selected_llm_attempt(
        self,
        attempts: tuple[object, ...],
    ) -> dict[str, str | None]:
        for attempt in attempts:
            status = getattr(attempt, "status", None)
            if status is LlmRouteAttemptStatus.SUCCESS:
                return {
                    "provider_id": self._string_or_none(
                        getattr(attempt, "provider_id", None)
                    ),
                    "model": self._required_model_name(getattr(attempt, "model", None)),
                    "api_key_slot": self._string_or_none(
                        getattr(attempt, "api_key_slot", None)
                    ),
                }

        if attempts:
            attempt = attempts[-1]
            return {
                "provider_id": self._string_or_none(
                    getattr(attempt, "provider_id", None)
                ),
                "model": self._required_model_name(getattr(attempt, "model", None)),
                "api_key_slot": self._string_or_none(
                    getattr(attempt, "api_key_slot", None)
                ),
            }

        return {
            "provider_id": None,
            "model": "unknown_final_reconciliation_model",
            "api_key_slot": None,
        }

    def _string_or_none(self, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return str(value)

    def _required_model_name(self, value: object) -> str:
        normalized = self._string_or_none(value)
        return normalized or "unknown_final_reconciliation_model"
