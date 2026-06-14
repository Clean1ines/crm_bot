from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_attempt_input import (
    DraftClaimCompactionAttemptInput,
    DraftClaimCompactionExpectedOutputKind,
    DraftClaimCompactionPromptKind,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionBatchForDispatch,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_prompt_payload_builder import (
    DraftClaimCompactionPromptPayloadBuilder,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_plan_repository_port import (
    DraftClaimCompactionPlanRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)

DRAFT_CLAIM_COMPACTION_WORK_KIND = WorkKind(
    "knowledge_workbench.draft_claim_compaction"
)
DRAFT_CLAIM_COMPACTION_PROMPT_REF = (
    "src/contexts/knowledge_workbench/extraction/application/prompts/"
    "draft_claim_compaction.txt"
)
MIXED_CLAIM_COMPACTION_PROMPT_REF = (
    "src/contexts/knowledge_workbench/extraction/application/prompts/"
    "enriched_claim_compaction.txt"
)
REDUCED_CLAIM_REWRITE_PROMPT_REF = (
    "src/contexts/knowledge_workbench/extraction/application/prompts/"
    "reduced_claim_rewrite.txt"
)


class DraftClaimCompactionAttemptInputBuildError(Exception):
    pass


class UnsupportedDraftClaimCompactionPromptVariant(
    DraftClaimCompactionAttemptInputBuildError
):
    pass


class DraftClaimCompactionBatchNotFound(DraftClaimCompactionAttemptInputBuildError):
    pass


class DraftClaimCompactionPayloadUnavailable(
    DraftClaimCompactionAttemptInputBuildError
):
    pass


@dataclass(frozen=True, slots=True)
class BuildDraftClaimCompactionAttemptInput:
    compaction_plan_repository: DraftClaimCompactionPlanRepositoryPort
    reduction_state_repository: DraftClaimCompactionReductionStateRepositoryPort
    payload_builder: DraftClaimCompactionPromptPayloadBuilder = (
        DraftClaimCompactionPromptPayloadBuilder()
    )

    async def execute(self, work_item: WorkItem) -> DraftClaimCompactionAttemptInput:
        if work_item.work_kind != DRAFT_CLAIM_COMPACTION_WORK_KIND:
            raise DraftClaimCompactionAttemptInputBuildError(
                "work_item kind must be knowledge_workbench.draft_claim_compaction",
            )

        workflow_run_id, batch_ref = _parse_claim_compaction_work_item_id(
            work_item.work_item_id,
        )
        batch = await self.compaction_plan_repository.get_compaction_batch_by_ref(
            batch_ref=batch_ref,
        )
        if batch is None:
            raise DraftClaimCompactionBatchNotFound(
                f"draft claim compaction batch not found: {batch_ref}",
            )
        if batch.workflow_run_id != workflow_run_id:
            raise DraftClaimCompactionAttemptInputBuildError(
                "work_item workflow_run_id does not match compaction batch",
            )

        if batch.prompt_variant == "draft_vs_draft":
            return await self._draft_vs_draft(work_item=work_item, batch=batch)
        if batch.prompt_variant == "mixed":
            return await self._payload_unavailable(
                batch=batch,
                message=(
                    "mixed compaction requires compacted output persistence "
                    "before attempt payload can be built"
                ),
            )
        if batch.prompt_variant == "reduced_rewrite":
            return await self._payload_unavailable(
                batch=batch,
                message=(
                    "reduced rewrite requires compacted output persistence "
                    "before attempt payload can be built"
                ),
            )
        raise UnsupportedDraftClaimCompactionPromptVariant(
            f"unsupported draft claim compaction prompt_variant: {batch.prompt_variant}",
        )

    async def _draft_vs_draft(
        self,
        *,
        work_item: WorkItem,
        batch: DraftClaimCompactionBatchForDispatch,
    ) -> DraftClaimCompactionAttemptInput:
        claims = await self.compaction_plan_repository.list_claims_for_compaction_batch(
            batch_ref=batch.batch_ref,
        )
        claims_by_ref = {claim.observation_ref: claim for claim in claims}
        missing_refs = tuple(
            ref for ref in batch.member_observation_refs if ref not in claims_by_ref
        )
        if missing_refs:
            raise DraftClaimCompactionPayloadUnavailable(
                "draft claim compaction batch claims are unavailable: "
                + ", ".join(missing_refs),
            )
        ordered_claims = tuple(
            claims_by_ref[ref] for ref in batch.member_observation_refs
        )
        payload = self.payload_builder.build_draft_vs_draft_payload(
            ordered_claims,
        ).to_json_dict()
        return DraftClaimCompactionAttemptInput(
            workflow_run_id=batch.workflow_run_id,
            group_ref=batch.group_ref,
            batch_ref=batch.batch_ref,
            work_item_id=work_item.work_item_id,
            prompt_kind=DraftClaimCompactionPromptKind.DRAFT_CLAIM_COMPACTION,
            prompt_ref=DRAFT_CLAIM_COMPACTION_PROMPT_REF,
            model_id=batch.model_id,
            payload=payload,
            expected_output_kind=(
                DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS
            ),
        )

    async def _payload_unavailable(
        self,
        *,
        batch: DraftClaimCompactionBatchForDispatch,
        message: str,
    ) -> DraftClaimCompactionAttemptInput:
        state = await self.reduction_state_repository.load_planner_state(
            workflow_run_id=batch.workflow_run_id,
            group_ref=batch.group_ref,
        )
        if state is None:
            raise DraftClaimCompactionPayloadUnavailable(
                "draft claim compaction reduction state is unavailable",
            )
        raise DraftClaimCompactionPayloadUnavailable(message)


def _parse_claim_compaction_work_item_id(work_item_id: str) -> tuple[str, str]:
    parts = work_item_id.split(":", 2)
    if len(parts) != 3 or parts[0] != "claim-compaction":
        raise DraftClaimCompactionAttemptInputBuildError(
            "work_item_id must match claim-compaction:{workflow_run_id}:{batch_ref}",
        )
    workflow_run_id = parts[1].strip()
    batch_ref = parts[2].strip()
    if not workflow_run_id:
        raise DraftClaimCompactionAttemptInputBuildError(
            "work_item_id must include workflow_run_id",
        )
    if not batch_ref:
        raise DraftClaimCompactionAttemptInputBuildError(
            "work_item_id must include batch_ref",
        )
    return workflow_run_id, batch_ref
