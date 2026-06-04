from __future__ import annotations

from typing import cast

from src.domain.project_plane.knowledge_workbench import DomainInvariantError, JsonValue
from src.infrastructure.llm.faq_workbench_claim_observations_generator import FaqWorkbenchClaimObservationsGenerator


_ALLOWED = {
    "part_of",
    "has_part",
    "narrows",
    "broadens",
    "refines",
    "extends",
    "overlaps",
    "contradicts",
    "same_meaning",
    "supports",
    "sets_boundary_for",
}


class FaqClaimObsContractGenerator(FaqWorkbenchClaimObservationsGenerator):
    def _parse_claim_observation(self, raw_observation: dict[str, JsonValue], *, index: int) -> dict[str, JsonValue]:
        parsed = dict(super()._parse_claim_observation(raw_observation, index=index))
        parsed["scope"] = self._optional_str(raw_observation, "scope", index=index) or ""
        parsed["local_relations"] = self._relations(raw_observation, index=index)
        self._assert_json_value(cast(JsonValue, parsed))
        return cast(dict[str, JsonValue], parsed)

    def _relations(self, payload: dict[str, JsonValue], *, index: int) -> list[JsonValue]:
        raw = payload.get("local_relations")
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise DomainInvariantError("local_relations must be list")
        out: list[JsonValue] = []
        for pos, item in enumerate(raw):
            if not isinstance(item, dict):
                raise DomainInvariantError("local relation must be object")
            out.append(
                {
                    "target_ref": self._required_str(item, "target_ref", index=index, label=f"relation {pos}"),
                    "relation": self._controlled_str(item, "relation", allowed=_ALLOWED, index=index, label=f"relation {pos}"),
                    "reason": self._required_str(item, "reason", index=index, label=f"relation {pos}"),
                }
            )
        return out
