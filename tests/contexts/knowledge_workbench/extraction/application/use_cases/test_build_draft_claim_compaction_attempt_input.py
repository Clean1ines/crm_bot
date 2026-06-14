from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_attempt_input import (
    DraftClaimCompactionExpectedOutputKind,
    DraftClaimCompactionPromptKind,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionBatchForDispatch,
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
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
        return DraftClaimCompactionPlannerState(cluster_ref="group-1", nodes=())

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
async def test_reduced_rewrite_is_unavailable_until_compacted_outputs_are_persisted() -> (
    None
):
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(batch=_batch("reduced_rewrite")),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    with pytest.raises(DraftClaimCompactionPayloadUnavailable, match="reduced rewrite"):
        await use_case.execute(_work_item())


@pytest.mark.asyncio
async def test_mixed_is_unavailable_until_compacted_outputs_are_persisted() -> None:
    use_case = BuildDraftClaimCompactionAttemptInput(
        compaction_plan_repository=FakePlanRepository(batch=_batch("mixed")),
        reduction_state_repository=FakeReductionStateRepository(),
    )

    with pytest.raises(
        DraftClaimCompactionPayloadUnavailable, match="mixed compaction"
    ):
        await use_case.execute(_work_item())
