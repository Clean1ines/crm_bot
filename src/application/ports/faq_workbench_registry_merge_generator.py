from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from src.domain.project_plane.knowledge_workbench.local_claim_canonicalization import (
    LocalClaimCanonicalizationUnit,
)
from src.domain.project_plane.knowledge_workbench.registry import (
    CanonicalFact,
    FactRegistry,
)
from src.domain.project_plane.knowledge_workbench.shared import (
    DomainInvariantError,
    JsonValue,
    NodeRunId,
    require_node_run_id,
)
from src.domain.project_plane.llm_routing import LlmJsonInvocationResult


@dataclass(frozen=True, slots=True)
class FaqWorkbenchRegistryMergeGenerationCommand:
    """Prompt C input contract.

    Prompt C no longer receives one section, free-form local claim lists, or retired candidate payloads from the retired incremental merge path.

    It receives one document-level canonicalization unit produced after local
    claim retrieval/clustering plus the current relevant registry state.
    """

    node_run_id: NodeRunId
    canonicalization_unit: LocalClaimCanonicalizationUnit
    registry: FactRegistry
    canonical_facts: tuple[CanonicalFact, ...]
    registry_snapshot_payload: JsonValue
    relevant_registry_state: JsonValue
    prompt_version: str = "faq_fact_registry_canonicalization.v1"

    def __post_init__(self) -> None:
        require_node_run_id(self.node_run_id)

        if not self.canonicalization_unit.members:
            raise DomainInvariantError(
                "Prompt C command requires canonicalization unit members"
            )

        if not isinstance(self.registry_snapshot_payload, dict):
            raise DomainInvariantError(
                "Prompt C registry_snapshot_payload must be object"
            )
        if not isinstance(self.relevant_registry_state, dict):
            raise DomainInvariantError(
                "Prompt C relevant_registry_state must be object"
            )

        for fact in self.canonical_facts:
            if fact.project_id != self.registry.project_id:
                raise DomainInvariantError("Prompt C fact project mismatch")
            if fact.document_id != self.registry.document_id:
                raise DomainInvariantError("Prompt C fact document mismatch")
            if fact.processing_run_id != self.registry.processing_run_id:
                raise DomainInvariantError("Prompt C fact processing_run mismatch")


@dataclass(frozen=True, slots=True)
class FaqWorkbenchRegistryMergeGenerationResult:
    """Validated canonical fact registry update produced by Prompt C."""

    fact_registry: dict[str, JsonValue]
    registry_update_summary: dict[str, JsonValue]
    invocation: LlmJsonInvocationResult
    raw_output_artifact_payload: JsonValue
    parsed_output_artifact_payload: JsonValue
    warnings: tuple[str, ...] = ()
    metrics: dict[str, JsonValue] = field(default_factory=dict)

    @property
    def canonical_fact_count(self) -> int:
        facts = self.fact_registry.get("canonical_facts", ())
        return len(facts) if isinstance(facts, list) else 0

    @property
    def fact_relation_count(self) -> int:
        relations = self.fact_registry.get("fact_relations", ())
        return len(relations) if isinstance(relations, list) else 0


class FaqWorkbenchRegistryMergeGenerationError(RuntimeError):
    """Provider-agnostic Prompt C generation failure."""

    def __init__(self, result: LlmJsonInvocationResult) -> None:
        failure = result.failure
        error_kind = failure.error_kind if failure is not None else result.status.value
        user_message = (
            failure.user_message
            if failure is not None
            else "LLM provider request failed."
        )
        internal_message = (
            failure.internal_message
            if failure is not None
            else f"Prompt C invocation failed: {result.status.value}"
        )

        super().__init__(f"Prompt C invocation failed: {error_kind}")
        self.result = result
        self.status = result.status
        self.error_kind = error_kind
        self.user_message = user_message
        self.internal_message = internal_message
        self.cooldown_seconds = (
            failure.cooldown_seconds if failure is not None else None
        )


class FaqWorkbenchRegistryMergeGeneratorPort(Protocol):
    async def generate_registry_updates(
        self,
        command: FaqWorkbenchRegistryMergeGenerationCommand,
    ) -> FaqWorkbenchRegistryMergeGenerationResult: ...


__all__ = [
    "FaqWorkbenchRegistryMergeGenerationCommand",
    "FaqWorkbenchRegistryMergeGenerationError",
    "FaqWorkbenchRegistryMergeGenerationResult",
    "FaqWorkbenchRegistryMergeGeneratorPort",
]
