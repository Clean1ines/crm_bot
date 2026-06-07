from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

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
    LlmInvocationFailure,
    LlmInvocationStatus,
    LlmJsonInvocationRequest,
    LlmJsonInvocationResult,
    LlmRouteAttempt,
    LlmRouteAttemptStatus,
    LlmTokenUsage,
)


class FaqWorkbenchClaimObservationsInvocationError(
    FaqWorkbenchClaimObservationsGenerationError
):
    """Backward-compatible infrastructure alias for first section LLM failures."""


class PromptAFallbackLlmJsonInvocationPort(LlmJsonInvocationPort, Protocol):
    fallback_models: tuple[str, ...]

    async def invoke_json_for_model(
        self,
        request: LlmJsonInvocationRequest,
        *,
        model: str,
    ) -> LlmJsonInvocationResult: ...


_PROMPT_A_FALLBACK_STATUSES = frozenset(
    {
        LlmInvocationStatus.REQUEST_TOO_LARGE,
        LlmInvocationStatus.OUTPUT_TOO_LARGE,
        LlmInvocationStatus.INVALID_JSON,
        LlmInvocationStatus.PROVIDER_ERROR,
    }
)
_PROMPT_A_VALIDATION_ERROR_KIND = "prompt_a_contract_validation"
_PROMPT_A_EXHAUSTED_TOO_LARGE_ERROR_KIND = (
    "prompt_a_fallback_exhausted_request_too_large"
)
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+./-]*")
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")
_CYRILLIC_LETTER_RE = re.compile(r"[А-Яа-яЁё]")
_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+\S")


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
        request = LlmJsonInvocationRequest(
            operation_name=self.config.operation_name,
            prompt=prompt,
            route_purpose=self.config.route_purpose,
            idempotency_key=f"{section.document_id}:{section.section_key}",
        )

        fallback_invocation = self._fallback_invocation()
        if fallback_invocation is not None:
            return await self._generate_findings_with_fallback(
                request=request,
                section=section,
                fallback_invocation=fallback_invocation,
            )

        result = await self.llm_invocation.invoke_json(request)
        return self._generation_result_from_invocation(
            result=result,
            section=section,
        )

    def _fallback_invocation(self) -> PromptAFallbackLlmJsonInvocationPort | None:
        invoke_for_model = getattr(self.llm_invocation, "invoke_json_for_model", None)
        fallback_models = getattr(self.llm_invocation, "fallback_models", None)
        if (
            callable(invoke_for_model)
            and isinstance(fallback_models, tuple)
            and all(isinstance(model, str) and model for model in fallback_models)
        ):
            return cast(PromptAFallbackLlmJsonInvocationPort, self.llm_invocation)
        return None

    async def _generate_findings_with_fallback(
        self,
        *,
        request: LlmJsonInvocationRequest,
        section: DocumentSection,
        fallback_invocation: PromptAFallbackLlmJsonInvocationPort,
    ) -> FaqWorkbenchClaimObservationsGenerationResult:
        prompt_attempts: list[LlmRouteAttempt] = []
        failed_statuses: list[LlmInvocationStatus] = []
        last_invocation_result: LlmJsonInvocationResult | None = None
        last_validation_error: DomainInvariantError | None = None

        for model in fallback_invocation.fallback_models:
            result = await fallback_invocation.invoke_json_for_model(
                request,
                model=model,
            )
            last_invocation_result = result

            if result.status is not LlmInvocationStatus.SUCCESS:
                failed_statuses.append(result.status)
                prompt_attempts.append(
                    self._prompt_a_attempt_from_result(
                        result,
                        model=model,
                        attempt_index=len(prompt_attempts),
                        status=LlmRouteAttemptStatus.FAILED,
                        error_kind=self._failure_error_kind(result),
                    )
                )
                if result.status not in _PROMPT_A_FALLBACK_STATUSES:
                    raise FaqWorkbenchClaimObservationsInvocationError(
                        self._result_with_attempts(result, tuple(prompt_attempts))
                    )
                continue

            try:
                generation_result = self._generation_result_from_invocation(
                    result=result,
                    section=section,
                )
            except DomainInvariantError as exc:
                last_validation_error = exc
                prompt_attempts.append(
                    self._prompt_a_attempt_from_result(
                        result,
                        model=model,
                        attempt_index=len(prompt_attempts),
                        status=LlmRouteAttemptStatus.FAILED,
                        error_kind=_PROMPT_A_VALIDATION_ERROR_KIND,
                    )
                )
                continue

            prompt_attempts.append(
                self._prompt_a_attempt_from_result(
                    result,
                    model=model,
                    attempt_index=len(prompt_attempts),
                    status=LlmRouteAttemptStatus.SUCCESS,
                    error_kind=None,
                )
            )
            return FaqWorkbenchClaimObservationsGenerationResult(
                claim_observations=generation_result.claim_observations,
                invocation=self._result_with_attempts(
                    generation_result.invocation,
                    tuple(prompt_attempts),
                ),
                raw_payload=generation_result.raw_payload,
                warnings=generation_result.warnings,
                metrics=generation_result.metrics,
            )

        if last_validation_error is not None:
            raise DomainInvariantError(
                "claim observation output contract failure after fallback chain: "
                f"{last_validation_error}"
            ) from last_validation_error

        if last_invocation_result is not None:
            exhausted = self._fallback_exhausted_result(
                last_result=last_invocation_result,
                attempts=tuple(prompt_attempts),
                failed_statuses=tuple(failed_statuses),
            )
            raise FaqWorkbenchClaimObservationsInvocationError(exhausted)

        raise DomainInvariantError("claim observation fallback chain is empty")

    def _generation_result_from_invocation(
        self,
        *,
        result: LlmJsonInvocationResult,
        section: DocumentSection,
    ) -> FaqWorkbenchClaimObservationsGenerationResult:
        if result.status is not LlmInvocationStatus.SUCCESS:
            raise FaqWorkbenchClaimObservationsInvocationError(result)

        if result.parsed_json is None:
            raise DomainInvariantError(
                "claim observation invocation returned empty JSON"
            )

        parsed_json = _workbench_json_value(result.parsed_json)
        normalized_payload = self._normalize_claim_observations_payload(parsed_json)
        claim_observations = self.parse_claim_observations_payload(normalized_payload)
        claim_observations = self._validate_claim_observations_against_section(
            observations=claim_observations,
            section=section,
        )
        return FaqWorkbenchClaimObservationsGenerationResult(
            claim_observations=claim_observations,
            invocation=result,
            raw_payload=normalized_payload,
            warnings=self._warnings_from_payload(normalized_payload),
            metrics=self._metrics_from_payload(normalized_payload),
        )

    def _validate_claim_observations_against_section(
        self,
        *,
        observations: tuple[ClaimObservation, ...],
        section: DocumentSection,
    ) -> tuple[ClaimObservation, ...]:
        source_candidates = self._section_text_candidates(section)
        source_text = "\n".join(source_candidates)
        source_latin_terms = frozenset(self._latin_terms(source_text))
        source_is_russian = self._is_cyrillic_dominant(source_text)

        validated: list[ClaimObservation] = []
        for index, observation in enumerate(observations):
            current: ClaimObservation = dict(observation)
            current["evidence_block"] = self._normalized_evidence_block(
                current,
                section=section,
                index=index,
            )

            if source_is_russian:
                claim = current.get("claim")
                if isinstance(claim, str):
                    self._validate_russian_text_field(
                        claim,
                        field_name="claim",
                        index=index,
                        source_latin_terms=source_latin_terms,
                    )

                exclusion_scope = current.get("exclusion_scope")
                if isinstance(exclusion_scope, str):
                    self._validate_russian_text_field(
                        exclusion_scope,
                        field_name="exclusion_scope",
                        index=index,
                        source_latin_terms=source_latin_terms,
                    )

                possible_questions = current.get("possible_questions")
                if isinstance(possible_questions, list):
                    for question in possible_questions:
                        if isinstance(question, str):
                            self._validate_russian_text_field(
                                question,
                                field_name="possible_questions",
                                index=index,
                                source_latin_terms=source_latin_terms,
                            )

            validated.append(current)

        return tuple(validated)

    def _normalized_evidence_block(
        self,
        observation: ClaimObservation,
        *,
        section: DocumentSection,
        index: int,
    ) -> str:
        value = observation.get("evidence_block")
        if not isinstance(value, str) or not value.strip():
            raise DomainInvariantError(
                f"claim observation #{index} requires non-empty string evidence_block"
            )

        evidence = value.strip()
        evidence_without_heading = self._strip_leading_markdown_heading(evidence)
        if (
            evidence_without_heading != evidence
            and evidence_without_heading
            and self._source_contains_text(section, evidence_without_heading)
        ):
            return evidence_without_heading

        if self._source_contains_text(section, evidence):
            return evidence

        raise DomainInvariantError(
            f"claim observation #{index} evidence_block must exactly match section text"
        )

    def _source_contains_text(self, section: DocumentSection, text: str) -> bool:
        return any(
            text in candidate for candidate in self._section_text_candidates(section)
        )

    def _section_text_candidates(self, section: DocumentSection) -> tuple[str, ...]:
        candidates: list[str] = []
        for value in (section.raw_text, section.normalized_text):
            if isinstance(value, str) and value.strip() and value not in candidates:
                candidates.append(value)
        if section.title and section.raw_text:
            titled = f"{section.title}\n\n{section.raw_text}"
            if titled not in candidates:
                candidates.append(titled)
        return tuple(candidates)

    def _strip_leading_markdown_heading(self, text: str) -> str:
        lines = text.splitlines()
        while lines and _MARKDOWN_HEADING_RE.match(lines[0]):
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines = lines[1:]
        return "\n".join(lines).strip()

    def _validate_russian_text_field(
        self,
        value: str,
        *,
        field_name: str,
        index: int,
        source_latin_terms: frozenset[str],
    ) -> None:
        text = value.strip()
        if not text:
            return

        latin_count = len(_LATIN_LETTER_RE.findall(text))
        cyrillic_count = len(_CYRILLIC_LETTER_RE.findall(text))
        if latin_count >= 4 and latin_count > cyrillic_count:
            raise DomainInvariantError(
                f"claim observation #{index} {field_name} must match source language"
            )

        unknown_terms = tuple(
            term
            for term in self._latin_terms(text)
            if len(term) > 1 and term not in source_latin_terms
        )
        if unknown_terms:
            preview = ", ".join(unknown_terms[:5])
            raise DomainInvariantError(
                f"claim observation #{index} {field_name} contains foreign terms "
                f"not present in source section: {preview}"
            )

    def _latin_terms(self, text: str) -> tuple[str, ...]:
        return tuple(
            match.group(0).casefold() for match in _LATIN_TOKEN_RE.finditer(text)
        )

    def _is_cyrillic_dominant(self, text: str) -> bool:
        cyrillic_count = len(_CYRILLIC_LETTER_RE.findall(text))
        latin_count = len(_LATIN_LETTER_RE.findall(text))
        return cyrillic_count >= 20 and cyrillic_count > latin_count

    def _prompt_a_attempt_from_result(
        self,
        result: LlmJsonInvocationResult,
        *,
        model: str,
        attempt_index: int,
        status: LlmRouteAttemptStatus,
        error_kind: str | None,
    ) -> LlmRouteAttempt:
        base = result.attempts[-1]
        return LlmRouteAttempt(
            provider_id=base.provider_id,
            model=model or base.model,
            api_key_slot=base.api_key_slot,
            attempt_index=attempt_index,
            status=status,
            error_kind=error_kind,
            cooldown_seconds=base.cooldown_seconds,
        )

    def _failure_error_kind(self, result: LlmJsonInvocationResult) -> str:
        if result.failure is not None:
            return result.failure.error_kind
        return result.status.value

    def _result_with_attempts(
        self,
        result: LlmJsonInvocationResult,
        attempts: tuple[LlmRouteAttempt, ...],
    ) -> LlmJsonInvocationResult:
        return LlmJsonInvocationResult(
            status=result.status,
            parsed_json=result.parsed_json,
            raw_text=result.raw_text,
            token_usage=result.token_usage,
            attempts=attempts,
            failure=result.failure,
            started_at=result.started_at,
            completed_at=result.completed_at,
        )

    def _fallback_exhausted_result(
        self,
        *,
        last_result: LlmJsonInvocationResult,
        attempts: tuple[LlmRouteAttempt, ...],
        failed_statuses: tuple[LlmInvocationStatus, ...],
    ) -> LlmJsonInvocationResult:
        too_large_statuses = {
            LlmInvocationStatus.REQUEST_TOO_LARGE,
            LlmInvocationStatus.OUTPUT_TOO_LARGE,
        }
        if failed_statuses and all(
            status in too_large_statuses for status in failed_statuses
        ):
            status = LlmInvocationStatus.REQUEST_TOO_LARGE
            return LlmJsonInvocationResult(
                status=status,
                parsed_json=None,
                raw_text=last_result.raw_text,
                token_usage=last_result.token_usage
                or LlmTokenUsage(prompt_tokens=0, completion_tokens=0),
                attempts=attempts,
                failure=LlmInvocationFailure(
                    status=status,
                    error_kind=_PROMPT_A_EXHAUSTED_TOO_LARGE_ERROR_KIND,
                    user_message=(
                        "Prompt A section is too large for every configured fallback model."
                    ),
                    internal_message=(
                        "Prompt A fallback chain exhausted with request/output too large; "
                        "section split is required."
                    ),
                    cooldown_seconds=None,
                ),
                started_at=last_result.started_at,
                completed_at=last_result.completed_at,
            )

        return self._result_with_attempts(last_result, attempts)

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

    def _normalize_claim_observations_payload(self, payload: JsonValue) -> JsonValue:
        if not isinstance(payload, dict):
            return payload

        has_canonical = "claim_observations" in payload
        has_alias = "claims" in payload

        if not has_alias:
            return payload
        if has_canonical:
            raise DomainInvariantError(
                "claim observations payload must not contain both claim_observations and claims"
            )

        normalized = dict(payload)
        normalized["claim_observations"] = normalized.pop("claims")
        return cast(JsonValue, normalized)

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
            "claim",
            "granularity",
            "evidence_block",
            "possible_questions",
            "exclusion_scope",
        }
        unknown_keys = set(raw_observation).difference(allowed_keys)
        if unknown_keys:
            names = ", ".join(sorted(unknown_keys))
            raise DomainInvariantError(
                f"unknown claim observation #{index} keys: {names}"
            )

        observation: ClaimObservation = {
            "local_ref": f"c{index + 1}",
            "claim": self._required_str(raw_observation, "claim", index=index),
            "claim_kind": "other",
            "granularity": self._controlled_str(
                raw_observation,
                "granularity",
                allowed={"atomic", "composite"},
                index=index,
            ),
            "triples": [],
            "evidence_block": self._required_str(
                raw_observation,
                "evidence_block",
                index=index,
            ),
            "possible_questions": list(
                self._string_tuple(raw_observation, "possible_questions", index=index)
            ),
            "scope": "",
            "exclusion_scope": self._optional_str(
                raw_observation,
                "exclusion_scope",
                index=index,
            )
            or "",
            "local_relations": [],
            "confidence": 0.9,
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
        if raw_triples is None:
            return []
        if not isinstance(raw_triples, list):
            raise DomainInvariantError(
                f"claim observation #{index} field triples must be list"
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
