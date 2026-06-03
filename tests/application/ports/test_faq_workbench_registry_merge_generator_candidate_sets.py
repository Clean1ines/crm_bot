from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.application.ports.faq_workbench_registry_merge_generator import (
    FaqWorkbenchRegistryMergeGenerationCommand,
    FaqWorkbenchRegistryMergeGenerationResult,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    LocalClaimCanonicalizationMember,
    LocalClaimCanonicalizationUnit,
)


def _unit() -> LocalClaimCanonicalizationUnit:
    return LocalClaimCanonicalizationUnit(
        unit_id="canonicalization-unit-1",
        group_id="group:section-1:node-run-1:c1",
        members=(
            LocalClaimCanonicalizationMember(
                search_document_id="section-1:node-run-1:c1",
                local_ref="c1",
                section_id="section-1",
                node_run_id="node-run-1",
                claim="Бот автоматически отвечает клиентам в Telegram.",
                claim_kind="capability",
                granularity="atomic",
                triple_texts=(
                    "бот has_capability автоматически отвечать клиентам telegram",
                ),
                possible_questions=(
                    "Может ли бот отвечать клиентам в Telegram?",
                ),
                scope="автоматические ответы telegram",
                exclusion_scope="не ручные ответы менеджера",
                evidence_block="Бот автоматически отвечает клиентам в Telegram.",
                relation_texts=(),
                search_text="claim: Бот автоматически отвечает клиентам в Telegram.",
            ),
        ),
        edges=(),
        max_similarity_score=0.0,
    )


def _registry() -> SimpleNamespace:
    return SimpleNamespace(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )


def _canonical_fact(**overrides: str) -> SimpleNamespace:
    values = {
        "project_id": "project-1",
        "document_id": "document-1",
        "processing_run_id": "processing-run-1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_prompt_c_command_accepts_canonicalization_unit_without_old_section_payload() -> None:
    command = FaqWorkbenchRegistryMergeGenerationCommand(
        node_run_id="node-run-prompt-c-1",
        canonicalization_unit=_unit(),
        registry=_registry(),
        canonical_facts=(_canonical_fact(),),
        registry_snapshot_payload={"canonical_facts": []},
        relevant_registry_state={"candidate_facts": []},
    )

    assert command.canonicalization_unit.unit_id == "canonicalization-unit-1"
    assert command.prompt_version == "faq_fact_registry_canonicalization.v1"

    assert not hasattr(command, "section")
    assert not hasattr(command, "claim_inputs")
    assert not hasattr(command, "candidate_fact_sets")
    assert not hasattr(command, "match_context")


def test_prompt_c_command_rejects_non_object_registry_state() -> None:
    with pytest.raises(DomainInvariantError, match="registry_snapshot_payload"):
        FaqWorkbenchRegistryMergeGenerationCommand(
            node_run_id="node-run-prompt-c-1",
            canonicalization_unit=_unit(),
            registry=_registry(),
            canonical_facts=(),
            registry_snapshot_payload=[],
            relevant_registry_state={},
        )

    with pytest.raises(DomainInvariantError, match="relevant_registry_state"):
        FaqWorkbenchRegistryMergeGenerationCommand(
            node_run_id="node-run-prompt-c-1",
            canonicalization_unit=_unit(),
            registry=_registry(),
            canonical_facts=(),
            registry_snapshot_payload={},
            relevant_registry_state=[],
        )


def test_prompt_c_command_validates_existing_canonical_fact_scope() -> None:
    with pytest.raises(DomainInvariantError, match="project mismatch"):
        FaqWorkbenchRegistryMergeGenerationCommand(
            node_run_id="node-run-prompt-c-1",
            canonicalization_unit=_unit(),
            registry=_registry(),
            canonical_facts=(_canonical_fact(project_id="other-project"),),
            registry_snapshot_payload={},
            relevant_registry_state={},
        )

    with pytest.raises(DomainInvariantError, match="document mismatch"):
        FaqWorkbenchRegistryMergeGenerationCommand(
            node_run_id="node-run-prompt-c-1",
            canonicalization_unit=_unit(),
            registry=_registry(),
            canonical_facts=(_canonical_fact(document_id="other-document"),),
            registry_snapshot_payload={},
            relevant_registry_state={},
        )

    with pytest.raises(DomainInvariantError, match="processing_run mismatch"):
        FaqWorkbenchRegistryMergeGenerationCommand(
            node_run_id="node-run-prompt-c-1",
            canonicalization_unit=_unit(),
            registry=_registry(),
            canonical_facts=(_canonical_fact(processing_run_id="other-run"),),
            registry_snapshot_payload={},
            relevant_registry_state={},
        )


def test_prompt_c_result_keeps_fact_registry_counts_without_old_proposal_shims() -> None:
    result = FaqWorkbenchRegistryMergeGenerationResult(
        fact_registry={
            "canonical_facts": [
                {"fact_id": "fact-1"},
                {"fact_id": "fact-2"},
            ],
            "fact_relations": [
                {"source_fact_id": "fact-1", "target_fact_id": "fact-2"},
            ],
        },
        registry_update_summary={"created": 2, "updated": 0},
        invocation=SimpleNamespace(),
        raw_output_artifact_payload={"raw": True},
        parsed_output_artifact_payload={"parsed": True},
    )

    assert result.canonical_fact_count == 2
    assert result.fact_relation_count == 1
    assert not hasattr(result, "proposal_count")
    assert not hasattr(result, "proposals")
