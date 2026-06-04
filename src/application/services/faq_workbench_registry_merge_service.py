from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from src.application.ports.faq_workbench_registry_merge_generator import (
    FaqWorkbenchRegistryMergeGenerationError,
    FaqWorkbenchRegistryMergeGenerationResult,
)
from src.application.ports.knowledge_workbench import (
    KnowledgeWorkbenchRegistryApplicationRepositoryPort,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    FactRegistry,
    JsonValue,
    KnowledgeDocumentStatus,
    LocalClaimCanonicalizationUnit,
    ProcessingNodeArtifact,
    ProcessingNodeArtifactType,
    ProcessingNodeKind,
    ProcessingNodeName,
    ProcessingNodeRun,
    ProcessingNodeStatus,
    ProcessingRunStatus,
    ResumePolicy,
)
from src.domain.project_plane.llm_routing import (
    LlmInvocationStatus,
    LlmJsonInvocationResult,
    LlmRouteAttemptStatus,
)


class IdFactory(Protocol):
    def new_id(self, prefix: str) -> str: ...


class TimeProvider(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class SystemTimeProvider:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class RegistryMergeGenerationErrorLifecycleTransition:
    document_status: KnowledgeDocumentStatus
    processing_run_status: ProcessingRunStatus
    resume_policy: ResumePolicy
    error_kind: str
    user_message: str
    internal_error: str


@dataclass(frozen=True, slots=True)
class ProcessRegistryMergeGenerationErrorCommand:
    node_run_id: str
    canonicalization_unit: LocalClaimCanonicalizationUnit
    registry: FactRegistry
    error: FaqWorkbenchRegistryMergeGenerationError
    prompt_version: str = "faq_fact_registry_canonicalization.v1"


@dataclass(frozen=True, slots=True)
class ProcessRegistryMergeGenerationErrorResult:
    node_run: ProcessingNodeRun
    error_artifact: ProcessingNodeArtifact
    lifecycle: RegistryMergeGenerationErrorLifecycleTransition


@dataclass(frozen=True, slots=True)
class PersistRegistryMergeNodeOutputCommand:
    node_run_id: str
    canonicalization_unit: LocalClaimCanonicalizationUnit
    registry: FactRegistry
    generation_result: FaqWorkbenchRegistryMergeGenerationResult
    prompt_version: str = "faq_fact_registry_canonicalization.v1"


@dataclass(frozen=True, slots=True)
class PersistRegistryMergeNodeOutputResult:
    node_run: ProcessingNodeRun
    raw_llm_artifact: ProcessingNodeArtifact
    parsed_llm_artifact: ProcessingNodeArtifact
    fact_registry: dict[str, JsonValue]
    registry_update_summary: dict[str, JsonValue]


class FaqWorkbenchRegistryMergeService:
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

    async def persist_registry_merge_generation_error(
        self,
        command: ProcessRegistryMergeGenerationErrorCommand,
    ) -> ProcessRegistryMergeGenerationErrorResult:
        self._validate_error_command(command)

        now = self._time_provider.now()
        artifact_id = self._id_factory.new_id("artifact")
        invocation = command.error.result
        failure = invocation.failure
        selected_attempt = self._selected_llm_attempt(invocation.attempts)

        user_message = (
            failure.user_message
            if failure is not None
            else "Не удалось канонизировать группу claims через ИИ. Можно повторить позже."
        )
        internal_message = (
            failure.internal_message
            if failure is not None
            else f"registry canonicalization invocation failed: {invocation.status.value}"
        )
        lifecycle = self._registry_merge_generation_error_lifecycle(
            invocation=invocation,
            fallback_user_message=user_message,
            fallback_internal_message=internal_message,
        )

        prompt_tokens = invocation.token_usage.prompt_tokens
        completion_tokens = invocation.token_usage.completion_tokens
        total_tokens = prompt_tokens + completion_tokens

        node_run = ProcessingNodeRun(
            node_run_id=command.node_run_id,
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            section_id=None,
            node_name=ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE,
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
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            section_id=None,
            artifact_type=ProcessingNodeArtifactType.ERROR_REPORT,
            payload_json=self._registry_merge_error_payload(
                command=command,
                invocation=invocation,
                lifecycle=lifecycle,
            ),
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE.value,
                "prompt_version": command.prompt_version,
                "invocation_status": invocation.status.value,
                "error_kind": lifecycle.error_kind,
                **self._canonicalization_unit_metadata(command.canonicalization_unit),
            },
        )

        await self._repository.create_processing_node_run(node_run)
        await self._repository.create_processing_node_artifact(error_artifact)
        await self._repository.sync_processing_run_llm_usage_totals(
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            processing_run_id=command.registry.processing_run_id,
        )
        await self._repository.persist_registry_merge_generation_error_lifecycle(
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            processing_run_id=command.registry.processing_run_id,
            node_run_id=command.node_run_id,
            document_status=lifecycle.document_status,
            processing_run_status=lifecycle.processing_run_status,
            resume_policy=lifecycle.resume_policy,
            error_kind=lifecycle.error_kind,
            user_message=lifecycle.user_message,
            internal_error=lifecycle.internal_error,
        )

        return ProcessRegistryMergeGenerationErrorResult(
            node_run=node_run,
            error_artifact=error_artifact,
            lifecycle=lifecycle,
        )

    async def persist_registry_merge_output(
        self,
        command: PersistRegistryMergeNodeOutputCommand,
    ) -> PersistRegistryMergeNodeOutputResult:
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
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            section_id=None,
            node_name=ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE,
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
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            section_id=None,
            artifact_type=ProcessingNodeArtifactType.RAW_LLM_OUTPUT,
            payload_json=command.generation_result.raw_output_artifact_payload,
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE.value,
                "prompt_version": command.prompt_version,
                "invocation_status": invocation.status.value,
                **self._canonicalization_unit_metadata(command.canonicalization_unit),
            },
        )
        parsed_llm_artifact = ProcessingNodeArtifact(
            artifact_id=parsed_artifact_id,
            node_run_id=command.node_run_id,
            processing_run_id=command.registry.processing_run_id,
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            section_id=None,
            artifact_type=ProcessingNodeArtifactType.PARSED_LLM_OUTPUT,
            payload_json=command.generation_result.parsed_output_artifact_payload,
            schema_version=1,
            created_at=now,
            metadata={
                "node": ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE.value,
                "prompt_version": command.prompt_version,
                "canonical_fact_count": command.generation_result.canonical_fact_count,
                "fact_relation_count": command.generation_result.fact_relation_count,
                "contract": "fact_registry_canonicalization",
                **self._canonicalization_unit_metadata(command.canonicalization_unit),
            },
        )

        await self._repository.create_processing_node_run(node_run)
        await self._repository.create_processing_node_artifact(raw_llm_artifact)
        await self._repository.create_processing_node_artifact(parsed_llm_artifact)
        await self._repository.sync_processing_run_llm_usage_totals(
            project_id=command.registry.project_id,
            document_id=command.registry.document_id,
            processing_run_id=command.registry.processing_run_id,
        )

        return PersistRegistryMergeNodeOutputResult(
            node_run=node_run,
            raw_llm_artifact=raw_llm_artifact,
            parsed_llm_artifact=parsed_llm_artifact,
            fact_registry=command.generation_result.fact_registry,
            registry_update_summary=command.generation_result.registry_update_summary,
        )

    def _validate_error_command(
        self,
        command: ProcessRegistryMergeGenerationErrorCommand,
    ) -> None:
        if not command.node_run_id:
            raise DomainInvariantError("registry merge error requires node_run_id")
        self._validate_canonicalization_unit(command.canonicalization_unit)
        if not command.registry.processing_run_id:
            raise DomainInvariantError(
                "registry merge error requires processing_run_id"
            )

    def _validate_command(
        self,
        command: PersistRegistryMergeNodeOutputCommand,
    ) -> None:
        if not command.node_run_id:
            raise DomainInvariantError("registry merge output requires node_run_id")
        self._validate_canonicalization_unit(command.canonicalization_unit)
        if not command.registry.processing_run_id:
            raise DomainInvariantError(
                "registry merge output requires processing_run_id"
            )

    def _validate_canonicalization_unit(
        self,
        unit: LocalClaimCanonicalizationUnit,
    ) -> None:
        if not unit.unit_id:
            raise DomainInvariantError("registry merge requires canonicalization unit")
        if not unit.members:
            raise DomainInvariantError(
                "registry merge requires canonicalization members"
            )

    def _canonicalization_unit_metadata(
        self,
        unit: LocalClaimCanonicalizationUnit,
    ) -> dict[str, JsonValue]:
        section_ids = tuple(dict.fromkeys(member.section_id for member in unit.members))
        node_run_ids = tuple(
            dict.fromkeys(member.node_run_id for member in unit.members)
        )
        local_refs = tuple(member.local_ref for member in unit.members)
        return {
            "canonicalization_unit_id": unit.unit_id,
            "canonicalization_group_id": unit.group_id,
            "canonicalization_member_count": unit.member_count,
            "canonicalization_edge_count": unit.edge_count,
            "canonicalization_member_section_ids": list(section_ids),
            "canonicalization_member_node_run_ids": list(node_run_ids),
            "canonicalization_member_local_refs": list(local_refs),
        }

    def _registry_merge_generation_error_lifecycle(
        self,
        *,
        invocation: LlmJsonInvocationResult,
        fallback_user_message: str,
        fallback_internal_message: str,
    ) -> RegistryMergeGenerationErrorLifecycleTransition:
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

        if invocation.status is LlmInvocationStatus.DAILY_LIMITED:
            return RegistryMergeGenerationErrorLifecycleTransition(
                document_status=KnowledgeDocumentStatus.PAUSED,
                processing_run_status=ProcessingRunStatus.PAUSED_QUOTA,
                resume_policy=ResumePolicy.AUTO_ALLOWED,
                error_kind=error_kind,
                user_message=user_message,
                internal_error=internal_error,
            )

        if invocation.status is LlmInvocationStatus.RATE_LIMITED:
            return RegistryMergeGenerationErrorLifecycleTransition(
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
            return RegistryMergeGenerationErrorLifecycleTransition(
                document_status=KnowledgeDocumentStatus.PAUSED,
                processing_run_status=ProcessingRunStatus.PAUSED_PROVIDER,
                resume_policy=ResumePolicy.AUTO_ALLOWED,
                error_kind=error_kind,
                user_message=user_message,
                internal_error=internal_error,
            )

        if invocation.status is LlmInvocationStatus.INVALID_JSON:
            return RegistryMergeGenerationErrorLifecycleTransition(
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
            return RegistryMergeGenerationErrorLifecycleTransition(
                document_status=KnowledgeDocumentStatus.FAILED,
                processing_run_status=ProcessingRunStatus.FAILED_FATAL,
                resume_policy=ResumePolicy.FORBIDDEN,
                error_kind="failed_fatal",
                user_message=user_message,
                internal_error=internal_error,
            )

        return RegistryMergeGenerationErrorLifecycleTransition(
            document_status=KnowledgeDocumentStatus.FAILED,
            processing_run_status=ProcessingRunStatus.FAILED_FATAL,
            resume_policy=ResumePolicy.FORBIDDEN,
            error_kind="failed_fatal",
            user_message=user_message,
            internal_error=internal_error,
        )

    def _registry_merge_error_payload(
        self,
        *,
        command: ProcessRegistryMergeGenerationErrorCommand,
        invocation: LlmJsonInvocationResult,
        lifecycle: RegistryMergeGenerationErrorLifecycleTransition,
    ) -> JsonValue:
        return {
            "node": ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE.value,
            "prompt_version": command.prompt_version,
            "canonicalization_unit": command.canonicalization_unit.to_prompt_payload(),
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
            "model": "unknown_registry_merge_model",
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
        return normalized or "unknown_registry_merge_model"


__all__ = [
    "FaqWorkbenchRegistryMergeService",
    "PersistRegistryMergeNodeOutputCommand",
    "PersistRegistryMergeNodeOutputResult",
    "ProcessRegistryMergeGenerationErrorCommand",
    "ProcessRegistryMergeGenerationErrorResult",
    "RegistryMergeGenerationErrorLifecycleTransition",
]
