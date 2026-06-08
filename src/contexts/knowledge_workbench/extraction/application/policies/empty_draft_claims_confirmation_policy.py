from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


class EmptyDraftClaimsDecisionKind(StrEnum):
    TRY_ALTERNATE_ROUTE = "try_alternate_route"
    ACCEPT_EMPTY_CLAIMS = "accept_empty_claims"


@dataclass(frozen=True, slots=True)
class EmptyDraftClaimsConfirmationInput:
    source_unit_ref: SourceUnitRef
    prompt_id: str
    previous_empty_claims_count: int
    alternate_routes_available: bool

    def __post_init__(self) -> None:
        if not self.prompt_id or not self.prompt_id.strip():
            raise ValueError("prompt_id must be non-empty")
        if self.previous_empty_claims_count < 0:
            raise ValueError("previous_empty_claims_count must be >= 0")


@dataclass(frozen=True, slots=True)
class EmptyDraftClaimsConfirmationDecision:
    kind: EmptyDraftClaimsDecisionKind


class EmptyDraftClaimsConfirmationPolicy:
    def decide(
        self,
        input: EmptyDraftClaimsConfirmationInput,
    ) -> EmptyDraftClaimsConfirmationDecision:
        if input.previous_empty_claims_count == 0 and input.alternate_routes_available:
            return EmptyDraftClaimsConfirmationDecision(
                kind=EmptyDraftClaimsDecisionKind.TRY_ALTERNATE_ROUTE,
            )

        return EmptyDraftClaimsConfirmationDecision(
            kind=EmptyDraftClaimsDecisionKind.ACCEPT_EMPTY_CLAIMS,
        )
