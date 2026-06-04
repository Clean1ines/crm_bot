from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from src.application.ports.faq_workbench_claim_observations_generator import (
    ClaimObservation,
    FaqWorkbenchClaimObservationsGenerationError,
    FaqWorkbenchClaimObservationsGenerationResult,
    FaqWorkbenchClaimObservationsGeneratorPort,
)
from src.application.ports.llm_json_invocation import LlmJsonInvocationPort
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DomainInvariantError,
    JsonValue,
)
from src.domain.project_plane.llm_routing import (
    LlmInvocationStatus,
    LlmJsonInvocationRequest,
)


class FaqWorkbenchClaimObservationsInvocationError(
    FaqWorkbenchClaimObservationsGenerationError
):
    """Backward-compatible infrastructure alias for first section LLM failures."""


@dataclass(frozen=True, slots=True)
class FaqWorkbenchClaimObservationsGeneratorConfig:
    prompt_path: Path
    operation_name: str = "faq_claim_observations"
    route_purpose: str = "workbench_claim_observations"


@dataclass(frozen=True, slots=True)
class FaqWorkbenchClaimObservationsGenerator(
    FaqWorkbenchClaimObservationsGeneratorPort
):
    llm_invocation: LlmJsonInvocationPort
    config: FaqWorkbenchClaimObservationsGeneratorConfig

    async def generate_findings(
        self,
        *,
        section: DocumentSection,
        registry_snapshot: JsonValue,
    ) -> FaqWorkbenchClaimObservationsGenerationResult:
        prompt = self.build_prompt(
            section=section,
            registry_snapshot=registry_snapshot,
        )
        result = await self.llm_invocation.invoke_json(
            LlmJsonInvocationRequest(
                operation_name=self.config.operation_name,
                prompt=prompt,
                route_purpose=self.config.route_purpose,
                idempotency_key=f"{section.document_id}:{section.section_key}",
            )
        )

        if result.status is not LlmInvocationStatus.SUCCESS:
            raise FaqWorkbenchClaimObservationsInvocationError(result)

        if result.parsed_json is None:
            raise DomainInvariantError(
                "claim observation invocation returned empty JSON"
            )

        parsed_json = _workbench_json_value(result.parsed_json)
        claim_observations = self.parse_claim_observations_payload(parsed_json)
        return FaqWorkbenchClaimObservationsGenerationResult(
            claim_observations=claim_observations,
            invocation=result,
            raw_payload=parsed_json,
            warnings=self._warnings_from_payload(parsed_json),
            metrics=self._metrics_from_payload(parsed_json),
        )

    def build_prompt(
        self,
        *,
        section: DocumentSection,
        registry_snapshot: JsonValue,
    ) -> str:
        prompt_template = self._load_prompt_template()
        source_unit: JsonValue = {
            "section_id": section.section_id,
            "document_id": section.document_id,
            "project_id": section.project_id,
            "section_index": section.section_index,
            "section_key": section.section_key,
            "heading_path": list(section.heading_path),
            "title": section.title,
            "raw_text": section.raw_text,
            "normalized_text": section.normalized_text,
            "source_refs": list(section.source_refs),
            "source_chunk_indexes": list(section.source_chunk_indexes),
            "parent_section_id": section.parent_section_id,
        }

        self._assert_json_value(source_unit)

        return "\n\n".join(
            (
                prompt_template.strip(),
                "INPUT_SOURCE_UNIT_JSON:",
                self._json(source_unit),
                "Return only the strict JSON object described in the prompt.",
            )
        )

    def parse_claim_observations_payload(
        self,
        payload: JsonValue,
    ) -> tuple[ClaimObservation, ...]:
        if not isinstance(payload, dict):
            raise DomainInvariantError(
                "claim observations payload must be a JSON object"
            )

        self._reject_unknown_payload_keys(payload)

        raw_observations = payload.get("claim_observations")
        if raw_observations is None:
            raise DomainInvariantError(
                "claim observations payload must contain claim_observations"
            )
        if not isinstance(raw_observations, list):
            raise DomainInvariantError("claim_observations must be a list")

        observations: list[ClaimObservation] = []
        for index, raw_observation in enumerate(raw_observations):
            if not isinstance(raw_observation, dict):
                raise DomainInvariantError(
                    f"claim observation #{index} must be an object"
                )
            observations.append(
                self._parse_claim_observation(raw_observation, index=index)
            )

        return tuple(observations)

    def _parse_claim_observation(
        self,
        raw_observation: dict[str, JsonValue],
        *,
        index: int,
    ) -> ClaimObservation:
        allowed_keys = {
            "local_ref",
            "claim",
            "claim_kind",
            "granularity",
            "triples",
            "evidence_block",
            "possible_questions",
            "scope",
            "exclusion_scope",
            "local_relations",
            "confidence",
        }
        unknown_keys = set(raw_observation).difference(allowed_keys)
        if unknown_keys:
            names = ", ".join(sorted(unknown_keys))
            raise DomainInvariantError(
                f"unknown claim observation #{index} keys: {names}"
            )

        observation: ClaimObservation = {
            "local_ref": self._required_str(raw_observation, "local_ref", index=index),
            "claim": self._required_str(raw_observation, "claim", index=index),
            "claim_kind": self._controlled_str(
                raw_observation,
                "claim_kind",
                allowed={
                    "definition",
                    "property",
                    "capability",
                    "limitation",
                    "rule",
                    "condition",
                    "process",
                    "list",
                    "comparison",
                    "criterion",
                    "example_set",
                    "value",
                    "exception",
                    "other",
                },
                index=index,
            ),
            "granularity": self._controlled_str(
                raw_observation,
                "granularity",
                allowed={"atomic", "composite"},
                index=index,
            ),
            "triples": self._triples(raw_observation, index=index),
            "evidence_block": self._required_str(
                raw_observation,
                "evidence_block",
                index=index,
            ),
            "possible_questions": list(
                self._string_tuple(raw_observation, "possible_questions", index=index)
            ),
            "scope": self._required_str(raw_observation, "scope", index=index),
            "exclusion_scope": self._optional_str(
                raw_observation,
                "exclusion_scope",
                index=index,
            )
            or "",
            "local_relations": self._json_list(
                raw_observation,
                "local_relations",
                index=index,
                label="claim observation",
            ),
            "confidence": self._confidence(raw_observation, index=index),
        }

        self._assert_json_value(observation)
        return observation

    def _triples(
        self,
        payload: dict[str, JsonValue],
        *,
        index: int,
    ) -> list[JsonValue]:
        raw_triples = payload.get("triples")
        if not isinstance(raw_triples, list) or not raw_triples:
            raise DomainInvariantError(
                f"claim observation #{index} requires non-empty triples list"
            )

        triples: list[JsonValue] = []
        for triple_index, raw_triple in enumerate(raw_triples):
            if not isinstance(raw_triple, dict):
                raise DomainInvariantError(
                    f"claim observation #{index} triple #{triple_index} must be an object"
                )
            triples.append(
                {
                    "subject": self._required_str(
                        raw_triple,
                        "subject",
                        index=index,
                        label=f"triple #{triple_index}",
                    ),
                    "predicate": self._controlled_str(
                        raw_triple,
                        "predicate",
                        allowed={
                            "is_a",
                            "is_not",
                            "has_property",
                            "has_capability",
                            "has_limitation",
                            "requires",
                            "supports",
                            "uses",
                            "produces",
                            "includes",
                            "has_item",
                            "has_step",
                            "has_condition",
                            "has_result",
                            "has_value",
                            "has_example",
                            "differs_from",
                            "excludes",
                            "causes",
                            "enables",
                            "prevents",
                            "depends_on",
                            "applies_when",
                        },
                        index=index,
                        label=f"triple #{triple_index}",
                    ),
                    "object": self._required_str(
                        raw_triple,
                        "object",
                        index=index,
                        label=f"triple #{triple_index}",
                    ),
                    "qualifiers": self._json_list(
                        raw_triple,
                        "qualifiers",
                        index=index,
                        label=f"triple #{triple_index}",
                    ),
                }
            )

        return triples

    def _warnings_from_payload(self, payload: JsonValue) -> tuple[str, ...]:
        if not isinstance(payload, dict):
            return ()

        raw_warnings = payload.get("warnings")
        if not isinstance(raw_warnings, list):
            return ()

        warnings: list[str] = []
        for item in raw_warnings:
            if not isinstance(item, str):
                continue
            normalized = " ".join(item.split())
            if normalized:
                warnings.append(normalized)
        return tuple(warnings)

    def _metrics_from_payload(self, payload: JsonValue) -> dict[str, JsonValue]:
        if not isinstance(payload, dict):
            return {}

        raw_metrics = payload.get("metrics")
        if not isinstance(raw_metrics, dict):
            return {}

        self._assert_json_value(cast(JsonValue, raw_metrics))
        return cast(
            dict[str, JsonValue],
            {str(key): value for key, value in raw_metrics.items()},
        )

    def _load_prompt_template(self) -> str:
        if not self.config.prompt_path.exists():
            raise DomainInvariantError(
                f"claim observations prompt file does not exist: {self.config.prompt_path}"
            )
        prompt = self.config.prompt_path.read_text(encoding="utf-8").strip()
        if not prompt:
            raise DomainInvariantError("claim observations prompt file is empty")
        return prompt

    def _reject_unknown_payload_keys(self, payload: dict[str, JsonValue]) -> None:
        allowed_keys = {"claim_observations", "warnings", "metrics"}
        unknown_keys = set(payload).difference(allowed_keys)
        if unknown_keys:
            names = ", ".join(sorted(unknown_keys))
            raise DomainInvariantError(
                f"unknown claim observations payload keys: {names}"
            )

    def _required_str(
        self,
        payload: dict[str, JsonValue],
        key: str,
        *,
        index: int,
        label: str = "claim observation",
    ) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise DomainInvariantError(
                f"{label} #{index} requires non-empty string {key}"
            )
        return value.strip()

    def _optional_str(
        self,
        payload: dict[str, JsonValue],
        key: str,
        *,
        index: int,
        label: str = "claim observation",
    ) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise DomainInvariantError(
                f"{label} #{index} optional field {key} must be string"
            )
        stripped = value.strip()
        return stripped or None

    def _controlled_str(
        self,
        payload: dict[str, JsonValue],
        key: str,
        *,
        allowed: set[str],
        index: int,
        label: str = "claim observation",
    ) -> str:
        value = self._required_str(payload, key, index=index, label=label)
        if value not in allowed:
            raise DomainInvariantError(
                f"{label} #{index} has unsupported {key}: {value}"
            )
        return value

    def _string_tuple(
        self,
        payload: dict[str, JsonValue],
        key: str,
        *,
        index: int,
    ) -> tuple[str, ...]:
        value = payload.get(key)
        if value is None:
            return ()
        if not isinstance(value, list):
            raise DomainInvariantError(
                f"claim observation #{index} field {key} must be list"
            )

        result: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise DomainInvariantError(
                    f"claim observation #{index} field {key} must contain only strings"
                )
            stripped = item.strip()
            if stripped:
                result.append(stripped)
        return tuple(result)

    def _json_list(
        self,
        payload: dict[str, JsonValue],
        key: str,
        *,
        index: int,
        label: str,
    ) -> list[JsonValue]:
        value = payload.get(key)
        if value is None:
            return []
        if not isinstance(value, list):
            raise DomainInvariantError(f"{label} #{index} field {key} must be list")
        self._assert_json_value(value)
        return list(value)

    def _confidence(
        self,
        payload: dict[str, JsonValue],
        *,
        index: int,
        label: str = "claim observation",
    ) -> float:
        value = payload.get("confidence")
        if not isinstance(value, int | float):
            raise DomainInvariantError(f"{label} #{index} confidence must be numeric")
        confidence = float(value)
        if confidence < 0 or confidence > 1:
            raise DomainInvariantError(
                f"{label} #{index} confidence must be between 0 and 1"
            )
        return confidence

    def _json(self, value: JsonValue) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    def _assert_json_value(self, value: JsonValue) -> None:
        try:
            json.dumps(value, ensure_ascii=False)
        except TypeError as exc:
            raise DomainInvariantError("value is not JSON serializable") from exc


def _workbench_json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _workbench_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_workbench_json_value(item) for item in value]
    raise DomainInvariantError("LLM JSON payload contains non-JSON value")


__all__ = [
    "FaqWorkbenchClaimObservationsGenerator",
    "FaqWorkbenchClaimObservationsGeneratorConfig",
    "FaqWorkbenchClaimObservationsInvocationError",
]
