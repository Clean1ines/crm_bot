from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


@dataclass(frozen=True, slots=True)
class DraftClaimEmbeddingInput:
    observation_ref: DraftClaimObservationRef
    source_unit_ref: SourceUnitRef
    text: str

    def __post_init__(self) -> None:
        if not self.text or not self.text.strip():
            raise ValueError("DraftClaimEmbeddingInput.text must be non-empty")


class DraftClaimEmbeddingInputBuilder:
    def build(
        self,
        observations: tuple[DraftClaimObservation, ...],
    ) -> tuple[DraftClaimEmbeddingInput, ...]:
        return tuple(
            DraftClaimEmbeddingInput(
                observation_ref=observation.observation_ref,
                source_unit_ref=observation.source_unit_ref,
                text=self._build_text(observation),
            )
            for observation in observations
        )

    def _build_text(self, observation: DraftClaimObservation) -> str:
        lines = [f"claim: {observation.claim.value}"]

        if observation.possible_questions:
            lines.append("possible_questions:")
            lines.extend(
                f"- {question.value}" for question in observation.possible_questions
            )

        if observation.exclusion_scope.value:
            lines.append(f"exclusion_scope: {observation.exclusion_scope.value}")

        lines.append(f"evidence_block: {observation.evidence_block.value}")

        return "\n".join(lines)
