from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.application.ports.faq_workbench_final_reconciliation_generator import (
    FaqWorkbenchFinalReconciliationGenerationCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    CanonicalFact,
    CanonicalFactStatus,
    RegistrySnapshot,
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
from src.infrastructure.llm.faq_workbench_final_reconciliation_generator import (
    FaqWorkbenchFinalReconciliationGenerator,
    FaqWorkbenchFinalReconciliationGeneratorConfig,
    FaqWorkbenchFinalReconciliationInvocationError,
)


@dataclass(slots=True)
class FakeLlmJsonInvocation:
    result: LlmJsonInvocationResult
    requests: list[LlmJsonInvocationRequest] = field(default_factory=list)

    async def invoke_json(
        self,
        request: LlmJsonInvocationRequest,
    ) -> LlmJsonInvocationResult:
        self.requests.append(request)
        return self.result


def _prompt_path(tmp_path: Path) -> Path:
    prompt_path = tmp_path / "faq_surface_final_reconciliation.ru.txt"
    prompt_path.write_text(
        "NODE: faq_surface_final_reconciliation\nReturn JSON only.",
        encoding="utf-8",
    )
    return prompt_path


def _snapshot() -> RegistrySnapshot:
    return RegistrySnapshot(
        snapshot_id="snapshot-1",
        registry_id="registry-1",
        processing_run_id="processing-run-1",
        project_id="project-1",
        document_id="document-1",
        after_node_run_id="registry-update-application-node",
        sequence_number=2,
        entries_payload={"entries": []},
        relations_payload={"relations": []},
        entry_count=1,
        relation_count=0,
        claim_observation_count=2,
        update_count=1,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def _entry() -> CanonicalFact:
    return CanonicalFact(
        fact_id="entry-1",
        registry_id="registry-1",
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        fact_key="product_definition",
        claim="Что такое продукт?",
        question_variants=("Что делает продукт?",),
        claim_kind="definition",
        answer="Продукт помогает клиентам.",
        short_answer="Помогает клиентам.",
        answer_scope="product",
        retrieval_scope="product",
        exclusion_scope="",
        evidence_quotes=("Продукт помогает клиентам.",),
        source_refs=("document-1#section-1",),
        source_section_ids=("section-1",),
        source_chunk_indexes=(0,),
        parent_fact_ids=(),
        child_fact_ids=(),
        duplicate_fact_ids=(),
        overlap_fact_ids=(),
        role_label_metadata={},
        status=CanonicalFactStatus.ACTIVE,
    )


def _command() -> FaqWorkbenchFinalReconciliationGenerationCommand:
    return FaqWorkbenchFinalReconciliationGenerationCommand(
        node_run_id="node-run-final",
        registry_snapshot=_snapshot(),
        canonical_facts=(_entry(),),
        proposed_final_surfaces=({"surface_key": "product_definition"},),
        proposed_relations=({"source": "product_definition", "target": "pricing"},),
        proposed_merge_decisions=(),
        aggregate_metrics={"entry_count": 1},
    )


def _success_result() -> LlmJsonInvocationResult:
    return LlmJsonInvocationResult(
        status=LlmInvocationStatus.SUCCESS,
        parsed_json={
            "surface_adjustments": [
                {"surface_key": "product_definition", "action": "tighten"}
            ],
            "relations": [
                {
                    "source": "product_definition",
                    "target": "pricing",
                    "relation_type": "complements",
                }
            ],
            "merge_decisions": [],
            "warnings": ["review relation"],
            "metrics": {"bounded_final_reconciliation": True},
        },
        raw_text='{"surface_adjustments":[]}',
        token_usage=LlmTokenUsage(prompt_tokens=13, completion_tokens=8),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model="llama-3.1-8b-instant",
                api_key_slot="slot-final",
                attempt_index=0,
                status=LlmRouteAttemptStatus.SUCCESS,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_generate_final_reconciliation_invokes_llm_and_parses_advice(
    tmp_path: Path,
) -> None:
    invocation = FakeLlmJsonInvocation(_success_result())
    generator = FaqWorkbenchFinalReconciliationGenerator(
        llm_invocation=invocation,
        config=FaqWorkbenchFinalReconciliationGeneratorConfig(
            prompt_path=_prompt_path(tmp_path)
        ),
    )

    result = await generator.generate_final_reconciliation(_command())

    assert len(invocation.requests) == 1
    request = invocation.requests[0]
    assert request.operation_name == "faq_surface_final_reconciliation"
    assert request.route_purpose == "workbench_final_reconciliation"
    assert request.idempotency_key == "document-1:snapshot-1:node-run-final"
    assert "NODE: faq_surface_final_reconciliation" in request.prompt
    assert "INPUT_JSON" in request.prompt
    assert "product_definition" in request.prompt

    assert result.surface_adjustment_count == 1
    assert result.relation_count == 1
    assert result.merge_decision_count == 0
    assert result.suggestion_count == 2
    assert result.advice.warnings == ("review relation",)
    assert result.advice.metrics == {"bounded_final_reconciliation": True}
    assert result.raw_output_artifact_payload["operation_name"] == (
        "faq_surface_final_reconciliation"
    )
    assert result.parsed_output_artifact_payload["surface_adjustments"] == (
        {"surface_key": "product_definition", "action": "tighten"},
    )


@pytest.mark.asyncio
async def test_generate_final_reconciliation_raises_typed_error_on_failed_invocation(
    tmp_path: Path,
) -> None:
    failed = LlmJsonInvocationResult(
        status=LlmInvocationStatus.PROVIDER_ERROR,
        parsed_json=None,
        raw_text="provider failed",
        token_usage=LlmTokenUsage(prompt_tokens=5, completion_tokens=0),
        attempts=(
            LlmRouteAttempt(
                provider_id="groq",
                model="llama-3.1-8b-instant",
                api_key_slot="slot-final",
                attempt_index=0,
                status=LlmRouteAttemptStatus.FAILED,
                error_kind="provider_error",
            ),
        ),
        failure=LlmInvocationFailure(
            status=LlmInvocationStatus.PROVIDER_ERROR,
            error_kind="provider_error",
            user_message="ИИ временно недоступен.",
            internal_message="provider failed during final reconciliation",
        ),
    )
    generator = FaqWorkbenchFinalReconciliationGenerator(
        llm_invocation=FakeLlmJsonInvocation(failed),
        config=FaqWorkbenchFinalReconciliationGeneratorConfig(
            prompt_path=_prompt_path(tmp_path)
        ),
    )

    with pytest.raises(FaqWorkbenchFinalReconciliationInvocationError) as exc_info:
        await generator.generate_final_reconciliation(_command())

    assert exc_info.value.result is failed


def test_parse_final_reconciliation_payload_requires_object_root(
    tmp_path: Path,
) -> None:
    generator = FaqWorkbenchFinalReconciliationGenerator(
        llm_invocation=FakeLlmJsonInvocation(_success_result()),
        config=FaqWorkbenchFinalReconciliationGeneratorConfig(
            prompt_path=_prompt_path(tmp_path)
        ),
    )

    with pytest.raises(DomainInvariantError, match="payload must be an object"):
        generator.parse_final_reconciliation_payload([])


def test_parse_final_reconciliation_payload_requires_list_fields(
    tmp_path: Path,
) -> None:
    generator = FaqWorkbenchFinalReconciliationGenerator(
        llm_invocation=FakeLlmJsonInvocation(_success_result()),
        config=FaqWorkbenchFinalReconciliationGeneratorConfig(
            prompt_path=_prompt_path(tmp_path)
        ),
    )

    with pytest.raises(
        DomainInvariantError, match="surface_adjustments must be a list"
    ):
        generator.parse_final_reconciliation_payload(
            {
                "surface_adjustments": {},
                "relations": [],
                "merge_decisions": [],
                "warnings": [],
                "metrics": {},
            }
        )


def test_parse_final_reconciliation_payload_defaults_optional_fields(
    tmp_path: Path,
) -> None:
    generator = FaqWorkbenchFinalReconciliationGenerator(
        llm_invocation=FakeLlmJsonInvocation(_success_result()),
        config=FaqWorkbenchFinalReconciliationGeneratorConfig(
            prompt_path=_prompt_path(tmp_path)
        ),
    )

    advice = generator.parse_final_reconciliation_payload({})

    assert advice.surface_adjustments == ()
    assert advice.relations == ()
    assert advice.merge_decisions == ()
    assert advice.warnings == ()
    assert advice.metrics == {}
    assert advice.suggestion_count == 0
