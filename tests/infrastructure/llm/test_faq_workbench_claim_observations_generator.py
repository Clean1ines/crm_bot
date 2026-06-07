from __future__ import annotations

from pathlib import Path

import pytest

from src.application.ports.llm_json_invocation import LlmJsonInvocationPort
from src.domain.project_plane.knowledge_workbench import (
    DocumentSection,
    DocumentSectionStatus,
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
from src.infrastructure.llm.faq_workbench_claim_observations_generator import (
    FaqWorkbenchClaimObservationsGenerator,
    FaqWorkbenchClaimObservationsGeneratorConfig,
    FaqWorkbenchClaimObservationsInvocationError,
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
        '"claim"',
        '"granularity"',
        '"evidence_block"',
        '"possible_questions"',
        '"exclusion_scope"',
    ):
        assert token in source

    for token in (
        "local_ref",
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


def test_generator_assigns_local_refs_mechanically_in_order() -> None:
    observations = _generator().parse_claim_observations_payload(
        {"claim_observations": [_minimal_claim(), _minimal_claim(claim="Второй факт.")]}
    )

    assert [observation["local_ref"] for observation in observations] == ["c1", "c2"]


def test_generator_rejects_llm_provided_local_ref_at_prompt_a_boundary() -> None:
    with pytest.raises(DomainInvariantError, match="local_ref"):
        _generator().parse_claim_observations_payload(
            {"claim_observations": [_minimal_claim(local_ref="c1")]}
        )


def test_generator_accepts_empty_claims_payload() -> None:
    observations = _generator().parse_claim_observations_payload(
        {"claim_observations": []}
    )

    assert observations == ()


@pytest.mark.parametrize(
    "field",
    ["claim", "granularity", "evidence_block"],
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


class FakePromptAFallbackInvocation:
    fallback_models = ("qwen/qwen3-32b", "openai/gpt-oss-120b")

    def __init__(self, responses: dict[str, LlmJsonInvocationResult]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    async def invoke_json(
        self,
        request: LlmJsonInvocationRequest,
    ) -> LlmJsonInvocationResult:
        return await self.invoke_json_for_model(
            request,
            model=self.fallback_models[0],
        )

    async def invoke_json_for_model(
        self,
        request: LlmJsonInvocationRequest,
        *,
        model: str,
    ) -> LlmJsonInvocationResult:
        self.calls.append(model)
        return self.responses[model]


def _fallback_generator(
    tmp_path: Path,
    invocation: LlmJsonInvocationPort,
) -> FaqWorkbenchClaimObservationsGenerator:
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("Return JSON.", encoding="utf-8")
    return FaqWorkbenchClaimObservationsGenerator(
        llm_invocation=invocation,
        config=FaqWorkbenchClaimObservationsGeneratorConfig(prompt_path=prompt_path),
    )


def _section(raw_text: str) -> DocumentSection:
    return DocumentSection(
        section_id="section-1",
        document_id="document-1",
        project_id="project-1",
        section_index=0,
        section_key="section-1",
        heading_path=(),
        title="Section",
        raw_text=raw_text,
        normalized_text=raw_text,
        source_refs=(),
        source_chunk_indexes=(),
        status=DocumentSectionStatus.PENDING,
        metadata={},
    )


def _success_result(model: str, payload: JsonValue) -> LlmJsonInvocationResult:
    return LlmJsonInvocationResult(
        status=LlmInvocationStatus.SUCCESS,
        parsed_json=payload,
        raw_text="{}",
        token_usage=LlmTokenUsage(prompt_tokens=10, completion_tokens=5),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model=model,
                api_key_slot="4/4",
                attempt_index=0,
                status=LlmRouteAttemptStatus.SUCCESS,
            ),
        ),
    )


def _failure_result(model: str, status: LlmInvocationStatus) -> LlmJsonInvocationResult:
    return LlmJsonInvocationResult(
        status=status,
        parsed_json=None,
        raw_text="",
        token_usage=LlmTokenUsage(prompt_tokens=0, completion_tokens=0),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model=model,
                api_key_slot="4/4",
                attempt_index=0,
                status=LlmRouteAttemptStatus.FAILED,
                error_kind=status.value,
            ),
        ),
        failure=LlmInvocationFailure(
            status=status,
            error_kind=status.value,
            user_message="failed",
            internal_message="failed",
        ),
    )


@pytest.mark.asyncio
async def test_generator_fallbacks_on_english_questions_for_russian_section(
    tmp_path: Path,
) -> None:
    section = _section(
        "Первый рабочий сценарий — Telegram-ассистент, который отвечает по базе "
        "знаний и передаёт сложные обращения менеджеру."
    )
    qwen_payload = {
        "claims": [
            _minimal_claim(
                claim=(
                    "Первый рабочий сценарий — Telegram-ассистент, который отвечает "
                    "по базе знаний и передаёт сложные обращения менеджеру."
                ),
                evidence_block=section.raw_text,
                possible_questions=[
                    "What is the first working scenario?",
                    "What does the Telegram assistant do?",
                ],
            )
        ]
    }
    gpt_payload = {
        "claims": [
            _minimal_claim(
                claim=(
                    "Первый рабочий сценарий — Telegram-ассистент, который отвечает "
                    "по базе знаний и передаёт сложные обращения менеджеру."
                ),
                evidence_block=section.raw_text,
                possible_questions=[
                    "Что делает первый рабочий сценарий?",
                    "Как работает Telegram-ассистент?",
                ],
            )
        ]
    }
    invocation = FakePromptAFallbackInvocation(
        {
            "qwen/qwen3-32b": _success_result("qwen/qwen3-32b", qwen_payload),
            "openai/gpt-oss-120b": _success_result(
                "openai/gpt-oss-120b",
                gpt_payload,
            ),
        }
    )
    generator = _fallback_generator(tmp_path, invocation)

    result = await generator.generate_findings(
        section=section,
        registry_snapshot={},
    )

    assert invocation.calls == ["qwen/qwen3-32b", "openai/gpt-oss-120b"]
    assert result.claim_observations[0]["possible_questions"] == [
        "Что делает первый рабочий сценарий?",
        "Как работает Telegram-ассистент?",
    ]
    assert [attempt.model for attempt in result.invocation.attempts] == [
        "qwen/qwen3-32b",
        "openai/gpt-oss-120b",
    ]
    assert result.invocation.attempts[0].status is LlmRouteAttemptStatus.FAILED
    assert result.invocation.attempts[0].error_kind == "prompt_a_contract_validation"
    assert result.invocation.attempts[1].status is LlmRouteAttemptStatus.SUCCESS


@pytest.mark.asyncio
async def test_generator_fallbacks_on_non_exact_evidence_block(tmp_path: Path) -> None:
    section = _section("Система хранит историю диалогов для менеджера.")
    invocation = FakePromptAFallbackInvocation(
        {
            "qwen/qwen3-32b": _success_result(
                "qwen/qwen3-32b",
                {
                    "claims": [
                        _minimal_claim(
                            claim="Система хранит историю диалогов.",
                            evidence_block="Система хранит историю клиентов и диалогов.",
                            possible_questions=["Что хранит система?"],
                        )
                    ]
                },
            ),
            "openai/gpt-oss-120b": _success_result(
                "openai/gpt-oss-120b",
                {
                    "claims": [
                        _minimal_claim(
                            claim="Система хранит историю диалогов для менеджера.",
                            evidence_block=section.raw_text,
                            possible_questions=["Что хранит система?"],
                        )
                    ]
                },
            ),
        }
    )
    generator = _fallback_generator(tmp_path, invocation)

    result = await generator.generate_findings(section=section, registry_snapshot={})

    assert invocation.calls == ["qwen/qwen3-32b", "openai/gpt-oss-120b"]
    assert result.claim_observations[0]["evidence_block"] == section.raw_text
    assert result.invocation.attempts[-1].model == "openai/gpt-oss-120b"


@pytest.mark.asyncio
async def test_generator_strips_leading_markdown_heading_from_evidence_block(
    tmp_path: Path,
) -> None:
    section = _section("## История диалогов\n\nСистема хранит историю диалогов.")
    invocation = FakePromptAFallbackInvocation(
        {
            "qwen/qwen3-32b": _success_result(
                "qwen/qwen3-32b",
                {
                    "claims": [
                        _minimal_claim(
                            claim="Система хранит историю диалогов.",
                            evidence_block=section.raw_text,
                            possible_questions=["Что хранит система?"],
                        )
                    ]
                },
            ),
            "openai/gpt-oss-120b": _success_result(
                "openai/gpt-oss-120b",
                {"claims": []},
            ),
        }
    )
    generator = _fallback_generator(tmp_path, invocation)

    result = await generator.generate_findings(section=section, registry_snapshot={})

    assert invocation.calls == ["qwen/qwen3-32b"]
    assert result.claim_observations[0]["evidence_block"] == (
        "Система хранит историю диалогов."
    )


@pytest.mark.asyncio
async def test_generator_fallbacks_on_request_too_large_status(tmp_path: Path) -> None:
    section = _section("Система хранит историю диалогов.")
    invocation = FakePromptAFallbackInvocation(
        {
            "qwen/qwen3-32b": _failure_result(
                "qwen/qwen3-32b",
                LlmInvocationStatus.REQUEST_TOO_LARGE,
            ),
            "openai/gpt-oss-120b": _success_result(
                "openai/gpt-oss-120b",
                {
                    "claims": [
                        _minimal_claim(
                            claim="Система хранит историю диалогов.",
                            evidence_block=section.raw_text,
                            possible_questions=["Что хранит система?"],
                        )
                    ]
                },
            ),
        }
    )
    generator = _fallback_generator(tmp_path, invocation)

    result = await generator.generate_findings(section=section, registry_snapshot={})

    assert invocation.calls == ["qwen/qwen3-32b", "openai/gpt-oss-120b"]
    assert [attempt.model for attempt in result.invocation.attempts] == [
        "qwen/qwen3-32b",
        "openai/gpt-oss-120b",
    ]
    assert result.invocation.attempts[0].status is LlmRouteAttemptStatus.FAILED
    assert result.invocation.attempts[1].status is LlmRouteAttemptStatus.SUCCESS


@pytest.mark.asyncio
async def test_generator_reports_stable_failure_when_all_models_are_too_large(
    tmp_path: Path,
) -> None:
    invocation = FakePromptAFallbackInvocation(
        {
            "qwen/qwen3-32b": _failure_result(
                "qwen/qwen3-32b",
                LlmInvocationStatus.REQUEST_TOO_LARGE,
            ),
            "openai/gpt-oss-120b": _failure_result(
                "openai/gpt-oss-120b",
                LlmInvocationStatus.OUTPUT_TOO_LARGE,
            ),
        }
    )
    generator = _fallback_generator(tmp_path, invocation)

    with pytest.raises(
        FaqWorkbenchClaimObservationsInvocationError,
        match="prompt_a_fallback_exhausted_request_too_large",
    ) as exc_info:
        await generator.generate_findings(
            section=_section("Система хранит историю диалогов."),
            registry_snapshot={},
        )

    assert invocation.calls == ["qwen/qwen3-32b", "openai/gpt-oss-120b"]
    assert exc_info.value.error_kind == "prompt_a_fallback_exhausted_request_too_large"
    assert [attempt.model for attempt in exc_info.value.result.attempts] == [
        "qwen/qwen3-32b",
        "openai/gpt-oss-120b",
    ]
