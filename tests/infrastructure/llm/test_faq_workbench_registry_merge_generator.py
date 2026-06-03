from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.application.ports.faq_workbench_registry_merge_generator import (
    FaqWorkbenchRegistryMergeGenerationCommand,
    FaqWorkbenchRegistryMergeGenerationError,
)
from src.application.ports.llm_json_invocation import LlmJsonInvocationPort
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    FactRegistry,
    FactRegistryStatus,
    LocalClaimCanonicalizationMember,
    LocalClaimCanonicalizationUnit,
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
from src.infrastructure.llm.faq_workbench_registry_merge_generator import (
    FaqWorkbenchRegistryMergeGenerator,
    FaqWorkbenchRegistryMergeGeneratorConfig,
)


class MonotonicIdFactory:
    def __init__(self) -> None:
        self._value = 0

    def new_id(self, prefix: str) -> str:
        self._value += 1
        return f"{prefix}-{self._value}"


@dataclass(slots=True)
class FakeLlmJsonInvocation(LlmJsonInvocationPort):
    response: LlmJsonInvocationResult
    requests: list[LlmJsonInvocationRequest]

    async def invoke_json(
        self,
        request: LlmJsonInvocationRequest,
    ) -> LlmJsonInvocationResult:
        self.requests.append(request)
        return self.response


def _unit() -> LocalClaimCanonicalizationUnit:
    return LocalClaimCanonicalizationUnit(
        unit_id="canonicalization-unit-1",
        group_id="group:section-1:node-run-1:c1",
        members=(
            LocalClaimCanonicalizationMember(
                search_document_id="section-1:node-run-1:c1",
                project_id="project-1",
                document_id="document-1",
                local_ref="c1",
                section_id="section-1",
                node_run_id="node-run-1",
                claim="Продукт является платформой управления AI-базами знаний.",
                claim_kind="definition",
                granularity="atomic",
                triple_texts=(
                    "Продукт is_a платформа управления AI-базами знаний",
                ),
                possible_questions=("Что такое продукт?",),
                scope="Общее определение",
                exclusion_scope="",
                evidence_block="Продукт — это платформа управления AI-базами знаний.",
                relation_texts=(),
                search_text="claim: Продукт является платформой управления AI-базами знаний.",
            ),
        ),
        edges=(),
        max_similarity_score=0.0,
    )


def _registry() -> FactRegistry:
    return FactRegistry(
        registry_id="registry-1",
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        status=FactRegistryStatus.BUILDING,
        version=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _command() -> FaqWorkbenchRegistryMergeGenerationCommand:
    return FaqWorkbenchRegistryMergeGenerationCommand(
        node_run_id="node-run-1",
        canonicalization_unit=_unit(),
        registry=_registry(),
        canonical_facts=(),
        registry_snapshot_payload={
            "version": 1,
            "canonical_facts": [],
            "fact_relations": [],
        },
        relevant_registry_state={
            "candidate_facts": [],
            "candidate_relations": [],
        },
    )


def _fact_registry_payload() -> dict:
    return {
        "fact_registry": {
            "version": 1,
            "canonical_facts": [
                {
                    "fact_id": "cf_product_definition",
                    "claim": "Продукт является платформой управления AI-базами знаний.",
                    "claim_kind": "definition",
                    "granularity": "atomic",
                    "triples": [
                        {
                            "subject": "Продукт",
                            "predicate": "is_a",
                            "object": "платформа управления AI-базами знаний",
                            "qualifiers": [],
                        },
                    ],
                    "mentions": [
                        {
                            "source_section_ref": "doc.md#intro",
                            "source_local_ref": "c1",
                            "evidence_block": "Продукт — это платформа управления AI-базами знаний.",
                            "mention_relation": "initial",
                        },
                    ],
                    "question_variants": ["Что такое продукт?"],
                    "scope": "Общее определение",
                    "exclusion_scope": "",
                    "derived_fact_notes": [],
                    "status": "active",
                },
            ],
            "fact_relations": [],
        },
        "registry_update_summary": {
            "created_fact_count": 1,
            "updated_fact_count": 0,
            "created_relation_count": 0,
            "notes": [],
        },
        "warnings": [],
        "metrics": {"canonical_fact_count": 1},
    }


def _success_invocation(payload: dict | None = None) -> LlmJsonInvocationResult:
    parsed_json = payload or _fact_registry_payload()
    return LlmJsonInvocationResult(
        status=LlmInvocationStatus.SUCCESS,
        parsed_json=parsed_json,
        raw_text="{}",
        token_usage=LlmTokenUsage(prompt_tokens=10, completion_tokens=20),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model="llama-3.1-8b-instant",
                api_key_slot="slot-1",
                attempt_index=0,
                status=LlmRouteAttemptStatus.SUCCESS,
            ),
        ),
    )


def _generator(
    tmp_path: Path,
    invocation: FakeLlmJsonInvocation,
) -> FaqWorkbenchRegistryMergeGenerator:
    prompt_path = tmp_path / "faq_surface_registry_merge.ru.txt"
    prompt_path.write_text("PROMPT C", encoding="utf-8")
    return FaqWorkbenchRegistryMergeGenerator(
        llm_invocation=invocation,
        config=FaqWorkbenchRegistryMergeGeneratorConfig(prompt_path=prompt_path),
        id_factory=MonotonicIdFactory(),
    )


@pytest.mark.asyncio
async def test_registry_merge_generator_now_returns_fact_registry_snapshot(
    tmp_path: Path,
) -> None:
    invocation = FakeLlmJsonInvocation(
        response=_success_invocation(),
        requests=[],
    )
    generator = _generator(tmp_path, invocation)

    result = await generator.generate_registry_updates(_command())

    assert result.fact_registry["version"] == 1
    assert result.fact_registry["canonical_facts"][0]["fact_id"] == "cf_product_definition"
    assert result.registry_update_summary["created_fact_count"] == 1
    assert result.canonical_fact_count == 1
    assert result.parsed_output_artifact_payload["fact_registry"] == result.fact_registry
    assert "registry_updates" not in result.parsed_output_artifact_payload

    assert len(invocation.requests) == 1
    assert invocation.requests[0].operation_name == "faq_fact_registry_canonicalization"
    assert invocation.requests[0].route_purpose == "workbench_fact_registry_canonicalization"
    assert "canonicalization_unit" in invocation.requests[0].prompt
    assert "registry_snapshot_payload" in invocation.requests[0].prompt
    assert "relevant_registry_state" in invocation.requests[0].prompt
    assert ("claim" + "_inputs") not in invocation.requests[0].prompt
    assert ("candidate" + "_fact_sets") not in invocation.requests[0].prompt
    assert ("source" + "_unit") not in invocation.requests[0].prompt
    assert ("match" + "_context") not in invocation.requests[0].prompt
    assert "canonicalization-unit-1" in invocation.requests[0].idempotency_key


def test_parse_fact_registry_payload_rejects_old_registry_updates_shape(
    tmp_path: Path,
) -> None:
    invocation = FakeLlmJsonInvocation(response=_success_invocation(), requests=[])
    generator = _generator(tmp_path, invocation)

    with pytest.raises(DomainInvariantError, match="unsupported keys"):
        generator.parse_fact_registry_payload(
            {
                "registry_updates": [],
                "warnings": [],
                "metrics": {},
            }
        )


def test_parse_fact_registry_payload_validates_relation_endpoints(
    tmp_path: Path,
) -> None:
    invocation = FakeLlmJsonInvocation(response=_success_invocation(), requests=[])
    generator = _generator(tmp_path, invocation)

    payload = _fact_registry_payload()
    payload["fact_registry"]["fact_relations"] = [
        {
            "source_fact_id": "cf_product_definition",
            "target_fact_id": "missing",
            "relation": "extends",
            "reason": "bad",
        },
    ]

    with pytest.raises(DomainInvariantError, match="unknown target_fact_id"):
        generator.parse_fact_registry_payload(payload)


@pytest.mark.asyncio
async def test_registry_merge_generator_wraps_provider_failure(tmp_path: Path) -> None:
    invocation = FakeLlmJsonInvocation(
        response=LlmJsonInvocationResult(
            status=LlmInvocationStatus.PROVIDER_ERROR,
            parsed_json=None,
            raw_text="failed",
            token_usage=LlmTokenUsage(prompt_tokens=10, completion_tokens=0),
            attempts=(
                LlmRouteAttempt(
                    provider_id="groq",
                    model="llama-3.1-8b-instant",
                    api_key_slot="slot-1",
                    attempt_index=0,
                    status=LlmRouteAttemptStatus.FAILED,
                    error_kind="provider_error",
                ),
            ),
            failure=LlmInvocationFailure(
                status=LlmInvocationStatus.PROVIDER_ERROR,
                error_kind="provider_error",
                user_message="Провайдер ИИ временно недоступен.",
                internal_message="provider failed",
            ),
        ),
        requests=[],
    )
    generator = _generator(tmp_path, invocation)

    with pytest.raises(FaqWorkbenchRegistryMergeGenerationError):
        await generator.generate_registry_updates(_command())
