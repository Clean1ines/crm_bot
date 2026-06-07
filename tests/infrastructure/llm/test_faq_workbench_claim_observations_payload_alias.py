from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.domain.project_plane.knowledge_workbench import (
    DocumentSectionStatus,
    DomainInvariantError,
    JsonValue,
)
from src.domain.project_plane.knowledge_workbench.documents import DocumentSection
from src.domain.project_plane.llm_routing import (
    LlmInvocationStatus,
    LlmJsonInvocationResult,
    LlmRouteAttempt,
    LlmRouteAttemptStatus,
    LlmTokenUsage,
)
from src.infrastructure.llm.faq_workbench_claim_observations_generator import (
    FaqWorkbenchClaimObservationsGenerator,
    FaqWorkbenchClaimObservationsGeneratorConfig,
)


@dataclass(slots=True)
class FakeInvocation:
    parsed_json: JsonValue

    async def invoke_json(self, request: object) -> LlmJsonInvocationResult:
        return LlmJsonInvocationResult(
            status=LlmInvocationStatus.SUCCESS,
            parsed_json=self.parsed_json,
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


def _section() -> DocumentSection:
    return DocumentSection(
        section_id="section-1",
        document_id="document-1",
        project_id="project-1",
        section_index=0,
        section_key="section-1",
        heading_path=(),
        title="Section",
        raw_text="Бот отвечает клиентам в Telegram.",
        normalized_text="Бот отвечает клиентам в Telegram.",
        source_refs=(),
        source_chunk_indexes=(),
        status=DocumentSectionStatus.PENDING,
        metadata={},
    )


def _generator(
    tmp_path: Path, parsed_json: JsonValue
) -> FaqWorkbenchClaimObservationsGenerator:
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("Return JSON.", encoding="utf-8")
    return FaqWorkbenchClaimObservationsGenerator(
        llm_invocation=FakeInvocation(parsed_json),
        config=FaqWorkbenchClaimObservationsGeneratorConfig(prompt_path=prompt_path),
    )


def _claim() -> dict[str, JsonValue]:
    return {
        "claim": "Бот отвечает клиентам в Telegram.",
        "granularity": "atomic",
        "evidence_block": "Бот отвечает клиентам в Telegram.",
        "possible_questions": ["Может ли бот отвечать клиентам?"],
        "exclusion_scope": "",
    }


def _required_payload_dict(payload: JsonValue | None) -> dict[str, JsonValue]:
    assert isinstance(payload, dict)
    return payload


def _first_raw_claim(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    raw_observations = payload.get("claim_observations")
    assert isinstance(raw_observations, list)
    assert raw_observations
    first_observation = raw_observations[0]
    assert isinstance(first_observation, dict)
    return first_observation


@pytest.mark.asyncio
async def test_prompt_a_accepts_claims_alias_and_normalizes_raw_payload(
    tmp_path: Path,
) -> None:
    generator = _generator(
        tmp_path,
        {
            "claims": [_claim()],
            "warnings": ["alias used"],
            "metrics": {"claim_count": 1},
        },
    )

    result = await generator.generate_findings(
        section=_section(),
        registry_snapshot={"contract": "fact_registry", "fact_registry": {}},
    )

    assert len(result.claim_observations) == 1
    assert result.claim_observations[0]["local_ref"] == "c1"

    raw_payload = _required_payload_dict(result.raw_payload)
    assert "claim_observations" in raw_payload
    assert "claims" not in raw_payload

    observation = result.claim_observations[0]
    assert observation["claim"] == "Бот отвечает клиентам в Telegram."
    assert observation["claim_kind"] == "other"
    assert observation["triples"] == []
    assert observation["scope"] == ""
    assert observation["local_relations"] == []
    assert observation["confidence"] == 0.9

    first_raw_claim = _first_raw_claim(raw_payload)
    assert first_raw_claim["claim"] == "Бот отвечает клиентам в Telegram."
    assert "local_ref" not in first_raw_claim
    assert "claim_kind" not in first_raw_claim
    assert "triples" not in first_raw_claim
    assert "scope" not in first_raw_claim
    assert "local_relations" not in first_raw_claim
    assert "confidence" not in first_raw_claim


def test_prompt_a_rejects_payload_with_both_claim_observations_and_claims(
    tmp_path: Path,
) -> None:
    generator = _generator(
        tmp_path,
        {
            "claim_observations": [_claim()],
            "claims": [_claim()],
        },
    )

    with pytest.raises(
        DomainInvariantError,
        match="must not contain both claim_observations and claims",
    ):
        generator.parse_claim_observations_payload(
            generator._normalize_claim_observations_payload(
                {
                    "claim_observations": [_claim()],
                    "claims": [_claim()],
                }
            )
        )


def test_prompt_a_parser_still_rejects_unknown_top_level_keys_after_normalization(
    tmp_path: Path,
) -> None:
    generator = _generator(
        tmp_path,
        {
            "claim_observations": [_claim()],
            "unexpected": [],
        },
    )

    with pytest.raises(
        DomainInvariantError,
        match="unknown claim observations payload keys: unexpected",
    ):
        generator.parse_claim_observations_payload(
            {
                "claim_observations": [_claim()],
                "unexpected": [],
            }
        )
