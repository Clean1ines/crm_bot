from __future__ import annotations

from src.domain.project_plane.knowledge_workbench import JsonValue
from src.infrastructure.llm.faq_workbench_claim_observations_generator import (
    FaqWorkbenchClaimObservationsGenerator,
)


class FaqClaimObsContractGenerator(FaqWorkbenchClaimObservationsGenerator):
    """Compatibility subclass kept for the package-level generator alias.

    Prompt A minimal boundary is owned by the base generator. This wrapper must
    not add legacy ontology fields before calling super(), because base parsing
    now intentionally rejects LLM-facing fields outside the minimal contract.
    """

    def _parse_claim_observation(
        self,
        raw_observation: dict[str, JsonValue],
        *,
        index: int,
    ) -> dict[str, JsonValue]:
        parsed = dict(super()._parse_claim_observation(raw_observation, index=index))
        self._assert_json_value(parsed)
        return parsed
