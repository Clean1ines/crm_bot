from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    JsonValue,
    CanonicalFact,
    RegistrySnapshot,
)
from src.domain.project_plane.llm_routing import LlmJsonInvocationResult


@dataclass(frozen=True, slots=True)
class FinalReconciliationAdvice:
    surface_adjustments: tuple[JsonValue, ...]
    relations: tuple[JsonValue, ...]
    merge_decisions: tuple[JsonValue, ...]
    warnings: tuple[str, ...]
    metrics: JsonValue

    def __post_init__(self) -> None:
        if not isinstance(self.metrics, dict):
            raise DomainInvariantError("final reconciliation metrics must be an object")
        for warning in self.warnings:
            if not warning.strip():
                raise DomainInvariantError(
                    "final reconciliation warnings must not be blank"
                )

    @property
    def suggestion_count(self) -> int:
        return (
            len(self.surface_adjustments)
            + len(self.relations)
            + len(self.merge_decisions)
        )


@dataclass(frozen=True, slots=True)
class FaqWorkbenchFinalReconciliationGenerationCommand:
    node_run_id: str
    registry_snapshot: RegistrySnapshot
    canonical_facts: tuple[CanonicalFact, ...]
    proposed_final_surfaces: tuple[JsonValue, ...]
    proposed_relations: tuple[JsonValue, ...]
    proposed_merge_decisions: tuple[JsonValue, ...]
    aggregate_metrics: JsonValue

    def __post_init__(self) -> None:
        if not self.node_run_id:
            raise DomainInvariantError(
                "final reconciliation command requires node_run_id"
            )
        if not isinstance(self.aggregate_metrics, dict):
            raise DomainInvariantError(
                "final reconciliation aggregate_metrics must be an object"
            )


@dataclass(frozen=True, slots=True)
class FaqWorkbenchFinalReconciliationGenerationResult:
    advice: FinalReconciliationAdvice
    invocation: LlmJsonInvocationResult
    raw_output_artifact_payload: JsonValue
    parsed_output_artifact_payload: JsonValue

    @property
    def surface_adjustment_count(self) -> int:
        return len(self.advice.surface_adjustments)

    @property
    def relation_count(self) -> int:
        return len(self.advice.relations)

    @property
    def merge_decision_count(self) -> int:
        return len(self.advice.merge_decisions)

    @property
    def suggestion_count(self) -> int:
        return self.advice.suggestion_count


class FaqWorkbenchFinalReconciliationGenerationError(RuntimeError):
    def __init__(self, result: LlmJsonInvocationResult) -> None:
        super().__init__("FAQ Workbench final reconciliation generation failed")
        self.result = result


class FaqWorkbenchFinalReconciliationGeneratorPort(Protocol):
    async def generate_final_reconciliation(
        self,
        command: FaqWorkbenchFinalReconciliationGenerationCommand,
    ) -> FaqWorkbenchFinalReconciliationGenerationResult: ...
