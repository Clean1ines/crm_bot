from __future__ import annotations

from pathlib import Path

import pytest

from src.application.ports.llm_json_invocation import LlmJsonInvocationPort
from src.domain.project_plane.knowledge_workbench import DomainInvariantError, JsonValue
from src.domain.project_plane.llm_routing import (
    LlmInvocationStatus,
    LlmJsonInvocationRequest,
    LlmJsonInvocationResult,
    LlmRouteAttempt,
    LlmRouteAttemptStatus,
    LlmTokenUsage,
)
from src.infrastructure.llm.faq_workbench_claim_observations_generator import (
    FaqWorkbenchClaimObservationsGenerator,
    FaqWorkbenchClaimObservationsGeneratorConfig,
)

GENERATOR = Path("src/infrastructure/llm/faq_workbench_claim_observations_generator.py")
PROMPT = Path("src/agent/prompts/faq_surface_claim_observations.ru.txt")


class FakeLlmJsonInvocation:
    async def invoke_json(
        self,
        request: LlmJsonInvocationRequest,
    ) -> LlmJsonInvocationResult:
        return LlmJsonInvocationResult(
            status=LlmInvocationStatus.SUCCESS,
            parsed_json={"claim_observations": []},
            raw_text="{}",
            token_usage=LlmTokenUsage(prompt_tokens=1, completion_tokens=1),
            attempts=(
                LlmRouteAttempt(
                    provider_id="fake",
                    model="fake-model",
                    api_key_slot="slot-1",
                    attempt_index=0,
                    status=LlmRouteAttemptStatus.SUCCESS,
                ),
            ),
        )


def _fake_llm_invocation() -> LlmJsonInvocationPort:
    return FakeLlmJsonInvocation()


def _generator() -> FaqWorkbenchClaimObservationsGenerator:
    return FaqWorkbenchClaimObservationsGenerator(
        llm_invocation=_fake_llm_invocation(),
        config=FaqWorkbenchClaimObservationsGeneratorConfig(prompt_path=Path("unused")),
    )


def _minimal_claim(**overrides: JsonValue) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "local_ref": "c1",
        "claim": "Сервис помогает клиенту быстро получить ответ по документам.",
        "granularity": "atomic",
        "evidence_block": "Сервис помогает клиенту быстро получить ответ по документам.",
        "possible_questions": ["Как быстро клиент получит ответ?"],
        "exclusion_scope": "",
    }
    payload.update(overrides)
    return payload


def test_generator_build_prompt_sends_only_source_unit() -> None:
    source = GENERATOR.read_text(encoding="utf-8")

    assert "def build_prompt(" in source
    assert "INPUT_SOURCE_UNIT_JSON" in source
    assert "INPUT_KNOWN_FACTS_JSON" not in source
    assert "known_facts" not in source


def test_prompt_a_contract_exposes_minimal_llm_schema_only() -> None:
    source = PROMPT.read_text(encoding="utf-8")

    for token in (
        '"claims"',
        '"local_ref"',
        '"claim"',
        '"granularity"',
        '"evidence_block"',
        '"possible_questions"',
        '"exclusion_scope"',
    ):
        assert token in source

    for token in (
        "claim_kind",
        "triples",
        "local_relations",
        "confidence",
    ):
        assert token not in source


def test_generator_normalizes_top_level_claims_and_defaults_full_shape() -> None:
    generator = _generator()

    normalized = generator._normalize_claim_observations_payload(
        {"claims": [_minimal_claim()]}
    )
    observations = generator.parse_claim_observations_payload(normalized)

    assert len(observations) == 1
    observation = observations[0]
    assert observation["local_ref"] == "c1"
    assert (
        observation["claim"]
        == "Сервис помогает клиенту быстро получить ответ по документам."
    )
    assert observation["granularity"] == "atomic"
    assert observation["evidence_block"] == (
        "Сервис помогает клиенту быстро получить ответ по документам."
    )
    assert observation["possible_questions"] == ["Как быстро клиент получит ответ?"]
    assert observation["exclusion_scope"] == ""

    assert observation["claim_kind"] == "other"
    assert observation["scope"] == ""
    assert observation["triples"] == []
    assert observation["local_relations"] == []
    assert observation["confidence"] == 0.9


def test_generator_rejects_unknown_old_ontology_keys_at_prompt_a_boundary() -> None:
    with pytest.raises(DomainInvariantError, match="triples"):
        _generator().parse_claim_observations_payload(
            {"claim_observations": [_minimal_claim(triples=[])]}
        )


@pytest.mark.parametrize(
    "field",
    ["local_ref", "claim", "granularity", "evidence_block"],
)
def test_generator_rejects_missing_required_minimal_claim_fields(field: str) -> None:
    claim = _minimal_claim()
    del claim[field]

    with pytest.raises(DomainInvariantError, match=field):
        _generator().parse_claim_observations_payload({"claim_observations": [claim]})


def test_generator_rejects_non_string_possible_questions_items() -> None:
    with pytest.raises(DomainInvariantError, match="possible_questions"):
        _generator().parse_claim_observations_payload(
            {"claim_observations": [_minimal_claim(possible_questions=["ok", 123])]}
        )


def test_generator_rejects_non_string_exclusion_scope_when_present() -> None:
    with pytest.raises(DomainInvariantError, match="exclusion_scope"):
        _generator().parse_claim_observations_payload(
            {"claim_observations": [_minimal_claim(exclusion_scope=[])]}
        )


def test_generator_still_rejects_later_stage_registry_fields() -> None:
    source = GENERATOR.read_text(encoding="utf-8")

    assert "relation_to_known_claim" not in source
    assert "suggested_registry_action" not in source


def test_contract_wrapper_does_not_inject_legacy_fields_before_base_parser() -> None:
    source = Path("src/infrastructure/llm/faq_claim_obs_contract.py").read_text(
        encoding="utf-8"
    )

    assert "super()._parse_claim_observation(raw_observation, index=index)" in source
    assert 'normalized["scope"]' not in source
    assert "__global__" not in source
    assert "local_relations" not in source
    assert "def _relations" not in source
