from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol, TypeAlias

from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    JsonValue,
)
from src.domain.project_plane.llm_routing import LlmJsonInvocationResult


ClaimObservation: TypeAlias = dict[str, JsonValue]


class FaqWorkbenchClaimObservationsGenerationError(RuntimeError):
    """Provider-agnostic claim observation generation failure.

    The class name is kept temporarily so existing application services can be
    cut over incrementally without importing infrastructure-specific exceptions.
    """

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
            else f"claim observation invocation failed: {result.status.value}"
        )

        super().__init__(f"claim observation invocation failed: {error_kind}")
        self.result = result
        self.status = result.status
        self.error_kind = error_kind
        self.user_message = user_message
        self.internal_message = internal_message
        self.cooldown_seconds = (
            failure.cooldown_seconds if failure is not None else None
        )


@dataclass(frozen=True, slots=True)
class FaqWorkbenchClaimObservationsGenerationResult:
    """Provider-agnostic result of the first section LLM node.

    Despite the temporary class name, this result is extraction-only Prompt A output:

    source_unit -> local claims/local graph

    Registry matching and canonical fact update belong to the later candidate
    retrieval / Prompt C path.
    """

    claim_observations: tuple[ClaimObservation, ...]
    invocation: LlmJsonInvocationResult
    raw_payload: JsonValue | None
    warnings: tuple[str, ...] = ()
    metrics: dict[str, JsonValue] = field(default_factory=dict)

    @property
    def findings(self) -> tuple[ClaimObservation, ...]:
        """Temporary compatibility alias for callers not yet renamed."""

        return self.claim_observations

    @property
    def claim_observation_count(self) -> int:
        return len(self.claim_observations)

    def __iter__(self) -> Iterator[ClaimObservation]:
        return iter(self.claim_observations)

    def __len__(self) -> int:
        return len(self.claim_observations)

    def __getitem__(self, index: int) -> ClaimObservation:
        return self.claim_observations[index]


class FaqWorkbenchClaimObservationsGeneratorPort(Protocol):
    async def generate_findings(
        self,
        *,
        section: DocumentSection,
        registry_snapshot: JsonValue,
    ) -> FaqWorkbenchClaimObservationsGenerationResult: ...


__all__ = [
    "ClaimObservation",
    "FaqWorkbenchClaimObservationsGenerationError",
    "FaqWorkbenchClaimObservationsGenerationResult",
    "FaqWorkbenchClaimObservationsGeneratorPort",
]
