from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_apply_result import (
    raw_claim_node_ref,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_attempt_input import (
    DraftClaimCompactionExpectedOutputKind,
    DraftClaimCompactionPromptKind,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionBatchForDispatch,
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionTriple,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNode,
    DraftClaimCompactionNodeKind,
    DraftClaimCompactionPlannerState,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_plan_repository_port import (
    DraftClaimCompactionPlanPersistenceResult,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStatePersistenceResult,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.build_draft_claim_compaction_attempt_input import (
    BuildDraftClaimCompactionAttemptInput,
    DraftClaimCompactionAttemptInputBuildError,
    DraftClaimCompactionBatchNotFound,
    DraftClaimCompactionPayloadUnavailable,
    UnsupportedDraftClaimCompactionPromptVariant,
)


@dataclass(slots=True)
class FakePlanRepository:
    batch: DraftClaimCompactionBatchForDispatch | None
    claims: tuple[DraftClaimForCompaction, ...] = ()

    async def get_compaction_batch_by_ref(
        self,
        *,
        batch_ref: str,
    ) -> DraftClaimCompactionBatchForDispatch | None:
        if self.batch is not None and self.batch.batch_ref == batch_ref:
            return self.batch
        return None

    async def list_claims_for_compaction_batch(
        self,
        *,
        batch_ref: str,
    ) -> tuple[DraftClaimForCompaction, ...]:
        assert self.batch is not None
        assert batch_ref == self.batch.batch_ref
        return self.claims

    async def list_claims_for_compaction(
        self,
        *,
        workflow_run_id: str,
        embedding_model_id: str,
    ) -> tuple[DraftClaimForCompaction, ...]:
        del workflow_run_id, embedding_model_id
        return ()

    async def persist_compaction_plan(
        self,
        *,
        edges,
        groups,
        batches,
        created_at,
    ) -> DraftClaimCompactionPlanPersistenceResult:
        del edges, groups, batches, created_at
        raise AssertionError("persist_compaction_plan must not be called")


@dataclass(slots=True)
class FakeReductionStateRepository:
    has_state: bool = True

    async def load_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
    ) -> DraftClaimCompactionPlannerState | None:
        del workflow_run_id, group_ref
        if not self.has_state:
            return None
        return DraftClaimCompactionPlannerState(
            cluster_ref="group-1",
            nodes=(
                DraftClaimCompactionNode(
                    node_ref="compacted-a",
                    node_kind=DraftClaimCompactionNodeKind.COMPACTED,
                    source_claim_refs=("claim-a",),
                    active=True,
                    compacted_key="refund_support_a",
                    compacted_claim="Product supports refunds in channel A.",
                    compacted_triples=(_triple(),),
                ),
                DraftClaimCompactionNode(
                    node_ref="compacted-b",
                    node_kind=DraftClaimCompactionNodeKind.COMPACTED,
                    source_claim_refs=("claim-b",),
                    active=True,
                    compacted_key="refund_support_b",
                    compacted_claim="Product supports refunds in channel B.",
                    compacted_triples=(_triple(),),
                ),
                DraftClaimCompactionNode(
                    node_ref=raw_claim_node_ref(
                        workflow_run_id="workflow-1",
                        group_ref="group-1",
                        observation_ref="claim-c",
                    ),
                    node_kind=DraftClaimCompactionNodeKind.RAW,
                    source_claim_refs=("claim-c",),
                    active=True,
                ),
            ),
        )

    async def seed_initial_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        raw_nodes,
        created_at,
    ) -> DraftClaimCompactionReductionStatePersistenceResult:
        del workflow_run_id, group_ref, raw_nodes, created_at
        raise AssertionError("seed_initial_planner_state must not be called")


def _triple() -> DraftClaimCompactionTriple:
    return DraftClaimCompactionTriple(
        subject="Product",
        predicate="has_capability",
        object="refunds",
        qualifiers=(),
    )


def _work_item(
    batch_ref: str = "batch-1", workflow_run_id: str = "workflow-1"
) -> WorkItem:
    return WorkItem(
        work_item_id=f"claim-compaction:{workflow_run_id}:{batch_ref}",
        work_kind=WorkKind("knowledge_workbench.draft_claim_compaction"),
    )


def _batch(
    prompt_variant: str = "draft_vs_draft",
) -> DraftClaimCompactionBatchForDispatch:
    return DraftClaimCompactionBatchForDispatch(
        batch_ref="batch-1",
        workflow_run_id="workflow-1",
        group_ref="group-1",
        prompt_variant=prompt_variant,
        model_id="openai/gpt-oss-120b",
        estimated_input_tokens=100,
        member_observation_refs=("claim-a", "claim-b"),
    )


def _claim(ref: str) -> DraftClaimForCompaction:
    return DraftClaimForCompaction(
        observation_ref=ref,
        embedding_ref=f"embedding-{ref}",
        workflow_run_id="workflow-1",
        source_document_ref="document-1",
        source_unit_ref="unit-1",
        claim=f"Claim {ref}",
        possible_questions=(f"Question {ref}?",),
        exclusion_scope=(),
        granularity="atomic",
        embedding_text=f"Claim {ref}",
        embedding_model_id="openai/gpt-oss-120b",
        dimensions=2,
        vector=(1.0, 0.0),
    )


@pytest.mark.asyncio
async def test_builds_draft_vs_draft_attempt_input_without_kind_or_compacted_claims() -> (
    None
):
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(
            batch=_batch(),
            claims=(_claim("claim-b"), _claim("claim-a")),
        ),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    result = await use_case.execute(_work_item())

    assert result.workflow_run_id == "workflow-1"
    assert result.group_ref == "group-1"
    assert result.batch_ref == "batch-1"
    assert result.work_item_id == "claim-compaction:workflow-1:batch-1"
    assert result.prompt_kind is DraftClaimCompactionPromptKind.DRAFT_CLAIM_COMPACTION
    assert result.model_id == "openai/gpt-oss-120b"
    assert result.expected_output_kind is (
        DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS
    )
    assert result.payload.keys() == {"claims"}
    assert [claim["id"] for claim in result.payload["claims"]] == [
        "claim-a",
        "claim-b",
    ]
    assert "kind" not in result.payload["claims"][0]
    assert "compacted_claims" not in result.payload


@pytest.mark.asyncio
async def test_builds_single_draft_claim_enrichment_attempt_input() -> None:
    batch = DraftClaimCompactionBatchForDispatch(
        batch_ref="batch-1",
        workflow_run_id="workflow-1",
        group_ref="group-1",
        prompt_variant="single_draft_claim_enrichment",
        model_id="openai/gpt-oss-120b",
        estimated_input_tokens=100,
        member_observation_refs=("claim-a",),
    )
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(
            batch=batch,
            claims=(_claim("claim-a"),),
        ),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    result = await use_case.execute(_work_item())

    assert result.prompt_kind is (
        DraftClaimCompactionPromptKind.SINGLE_DRAFT_CLAIM_ENRICHMENT
    )
    assert result.prompt_ref.endswith("single_draft_claim_enrichment.txt")
    assert result.expected_output_kind is (
        DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS
    )
    assert result.payload.keys() == {"claims"}
    assert result.payload["claims"] == [
        {
            "id": "claim-a",
            "claim": "Claim claim-a",
            "questions": ["Question claim-a?"],
        }
    ]


@pytest.mark.asyncio
async def test_single_draft_claim_enrichment_rejects_non_singleton_batch() -> None:
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(
            batch=_batch("single_draft_claim_enrichment"),
            claims=(_claim("claim-a"), _claim("claim-b")),
        ),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    with pytest.raises(DraftClaimCompactionPayloadUnavailable, match="exactly one"):
        await use_case.execute(_work_item())


@pytest.mark.asyncio
async def test_rejects_unknown_prompt_variant_with_typed_failure() -> None:
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(batch=_batch("unknown")),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    with pytest.raises(UnsupportedDraftClaimCompactionPromptVariant):
        await use_case.execute(_work_item())


@pytest.mark.asyncio
async def test_rejects_missing_batch_ref_with_typed_failure() -> None:
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(batch=_batch()),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    with pytest.raises(DraftClaimCompactionAttemptInputBuildError, match="batch_ref"):
        await use_case.execute(_work_item(batch_ref=""))


@pytest.mark.asyncio
async def test_rejects_missing_workflow_run_id_with_typed_failure() -> None:
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(batch=_batch()),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    with pytest.raises(
        DraftClaimCompactionAttemptInputBuildError,
        match="workflow_run_id",
    ):
        await use_case.execute(_work_item(workflow_run_id=""))


@pytest.mark.asyncio
async def test_rejects_unknown_batch_ref_with_typed_failure() -> None:
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(batch=None),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    with pytest.raises(DraftClaimCompactionBatchNotFound):
        await use_case.execute(_work_item(batch_ref="missing-batch"))


@pytest.mark.asyncio
async def test_reduced_rewrite_is_unavailable_without_compacted_node_refs_in_batch() -> (
    None
):
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(batch=_batch("reduced_rewrite")),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    with pytest.raises(
        DraftClaimCompactionPayloadUnavailable,
        match="compacted node refs",
    ):
        await use_case.execute(_work_item())


@pytest.mark.asyncio
async def test_mixed_is_unavailable_without_explicit_raw_and_compacted_node_refs() -> (
    None
):
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(batch=_batch("mixed")),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    with pytest.raises(
        DraftClaimCompactionPayloadUnavailable,
        match="compacted node refs and raw claim refs",
    ):
        await use_case.execute(_work_item())


@pytest.mark.asyncio
async def test_reduced_rewrite_builds_payload_from_compacted_node_refs() -> None:
    batch = DraftClaimCompactionBatchForDispatch(
        batch_ref="batch-1",
        workflow_run_id="workflow-1",
        group_ref="group-1",
        prompt_variant="reduced_rewrite",
        model_id="openai/gpt-oss-120b",
        estimated_input_tokens=100,
        member_observation_refs=("compacted-b", "compacted-a"),
    )
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(batch=batch),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    result = await use_case.execute(_work_item())

    assert result.prompt_kind is DraftClaimCompactionPromptKind.REDUCED_CLAIM_REWRITE
    assert result.expected_output_kind is (
        DraftClaimCompactionExpectedOutputKind.REDUCED_REWRITE
    )
    assert result.prompt_ref.endswith("reduced_claim_rewrite.txt")
    assert result.payload.keys() == {"compacted_claims"}
    assert [item["key"] for item in result.payload["compacted_claims"]] == [
        "refund_support_b",
        "refund_support_a",
    ]
    assert set(result.payload["compacted_claims"][0]) == {"key", "claim", "triples"}


@pytest.mark.asyncio
async def test_reduced_rewrite_is_unavailable_without_compacted_node_refs() -> None:
    batch = DraftClaimCompactionBatchForDispatch(
        batch_ref="batch-1",
        workflow_run_id="workflow-1",
        group_ref="group-1",
        prompt_variant="reduced_rewrite",
        model_id="openai/gpt-oss-120b",
        estimated_input_tokens=100,
        member_observation_refs=("claim-a", "claim-b"),
    )
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(batch=batch),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    with pytest.raises(
        DraftClaimCompactionPayloadUnavailable, match="compacted node refs"
    ):
        await use_case.execute(_work_item())


@pytest.mark.asyncio
async def test_mixed_remains_unavailable_without_explicit_raw_and_compacted_node_refs() -> (
    None
):
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(batch=_batch("mixed")),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    with pytest.raises(
        DraftClaimCompactionPayloadUnavailable,
        match="compacted node refs and raw claim refs",
    ):
        await use_case.execute(_work_item())


@pytest.mark.asyncio
async def test_mixed_builds_payload_from_compacted_node_and_raw_claim_ref() -> None:
    raw_node_ref = raw_claim_node_ref(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        observation_ref="claim-c",
    )
    batch = DraftClaimCompactionBatchForDispatch(
        batch_ref="batch-1",
        workflow_run_id="workflow-1",
        group_ref="group-1",
        prompt_variant="mixed",
        model_id="openai/gpt-oss-120b",
        estimated_input_tokens=100,
        member_observation_refs=("compacted-a", raw_node_ref),
    )
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(
            batch=batch,
            claims=(_claim("claim-c"),),
        ),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    result = await use_case.execute(_work_item())

    assert result.prompt_kind is DraftClaimCompactionPromptKind.MIXED_CLAIM_COMPACTION
    assert result.expected_output_kind is (
        DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS
    )
    assert result.prompt_ref.endswith("enriched_claim_compaction.txt")
    assert result.payload["mixed_input"] == {
        "compacted_node_refs": ["compacted-a"],
        "raw_claim_refs": ["claim-c"],
    }
    assert [claim["id"] for claim in result.payload["claims"]] == [
        "compacted-a",
        "claim-c",
    ]
    assert result.payload["claims"][0]["claim"] == (
        "Product supports refunds in channel A."
    )
    assert result.payload["claims"][1]["claim"] == "Claim claim-c"


@pytest.mark.asyncio
async def test_compacted_vs_compacted_uses_enriched_prompt_contract() -> None:
    batch = DraftClaimCompactionBatchForDispatch(
        batch_ref="batch-1",
        workflow_run_id="workflow-1",
        group_ref="group-1",
        prompt_variant="compacted_vs_compacted",
        model_id="openai/gpt-oss-120b",
        estimated_input_tokens=100,
        member_observation_refs=("compacted-a", "compacted-b"),
    )
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(batch=batch),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    result = await use_case.execute(_work_item())

    assert result.prompt_kind is DraftClaimCompactionPromptKind.MIXED_CLAIM_COMPACTION
    assert result.prompt_ref.endswith("enriched_claim_compaction.txt")
    assert result.expected_output_kind is (
        DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS
    )
    assert [claim["id"] for claim in result.payload["claims"]] == [
        "compacted-a",
        "compacted-b",
    ]


@pytest.mark.asyncio
async def test_mixed_rejects_compacted_node_from_another_cluster_state() -> None:
    raw_node_ref = raw_claim_node_ref(
        workflow_run_id="workflow-1",
        group_ref="group-1",
        observation_ref="claim-c",
    )
    batch = DraftClaimCompactionBatchForDispatch(
        batch_ref="batch-1",
        workflow_run_id="workflow-1",
        group_ref="group-1",
        prompt_variant="mixed",
        model_id="openai/gpt-oss-120b",
        estimated_input_tokens=100,
        member_observation_refs=("compacted-from-other-group", raw_node_ref),
    )
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(
            batch=batch,
            claims=(_claim("claim-c"),),
        ),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    with pytest.raises(
        DraftClaimCompactionPayloadUnavailable,
        match="compacted node refs and raw claim refs",
    ):
        await use_case.execute(_work_item())
