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
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionPromptClaim,
    DraftClaimCompactionPromptPayload,
    DraftClaimReducedRewriteInputClaim,
    DraftClaimReducedRewritePayload,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNode,
    DraftClaimCompactionNodeKind,
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
            return await self._mixed(work_item=work_item, batch=batch)
        if batch.prompt_variant == "reduced_rewrite":
            return await self._reduced_rewrite(work_item=work_item, batch=batch)
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

    async def _mixed(
        self,
        *,
        work_item: WorkItem,
        batch: DraftClaimCompactionBatchForDispatch,
    ) -> DraftClaimCompactionAttemptInput:
        state = await self.reduction_state_repository.load_planner_state(
            workflow_run_id=batch.workflow_run_id,
            group_ref=batch.group_ref,
        )
        if state is None:
            raise DraftClaimCompactionPayloadUnavailable(
                "draft claim compaction reduction state is unavailable",
            )

        nodes_by_ref = {node.node_ref: node for node in state.nodes}
        compacted_nodes: list[DraftClaimCompactionNode] = []
        raw_claim_refs: list[str] = []

        for ref in batch.member_observation_refs:
            node = nodes_by_ref.get(ref)
            if node is None:
                raw_claim_refs.append(ref)
                continue
            if not node.active:
                raise DraftClaimCompactionPayloadUnavailable(
                    "mixed batch must reference active nodes only",
                )
            if node.node_kind is DraftClaimCompactionNodeKind.COMPACTED:
                compacted_nodes.append(node)
                continue
            if node.node_kind is DraftClaimCompactionNodeKind.RAW:
                raw_claim_refs.extend(node.source_claim_refs)
                continue

        raw_claim_refs_tuple = _dedupe_preserving_order(tuple(raw_claim_refs))
        if not compacted_nodes or not raw_claim_refs_tuple:
            raise DraftClaimCompactionPayloadUnavailable(
                "mixed batch requires compacted node refs and raw claim refs",
            )

        claims = await self.compaction_plan_repository.list_claims_for_compaction_batch(
            batch_ref=batch.batch_ref,
        )
        claims_by_ref = {claim.observation_ref: claim for claim in claims}
        missing_raw_refs = tuple(
            raw_ref for raw_ref in raw_claim_refs_tuple if raw_ref not in claims_by_ref
        )
        if missing_raw_refs:
            raise DraftClaimCompactionPayloadUnavailable(
                "mixed batch raw claims are unavailable: "
                + ", ".join(missing_raw_refs),
            )

        payload = DraftClaimCompactionPromptPayload(
            claims=tuple(
                _mixed_compacted_prompt_claim(node) for node in compacted_nodes
            )
            + tuple(
                _raw_prompt_claim(claims_by_ref[raw_ref])
                for raw_ref in raw_claim_refs_tuple
            ),
            prompt_variant="mixed",
        ).to_json_dict()
        payload["mixed_input"] = {
            "compacted_node_refs": [node.node_ref for node in compacted_nodes],
            "raw_claim_refs": list(raw_claim_refs_tuple),
        }

        return DraftClaimCompactionAttemptInput(
            workflow_run_id=batch.workflow_run_id,
            group_ref=batch.group_ref,
            batch_ref=batch.batch_ref,
            work_item_id=work_item.work_item_id,
            prompt_kind=DraftClaimCompactionPromptKind.MIXED_CLAIM_COMPACTION,
            prompt_ref=MIXED_CLAIM_COMPACTION_PROMPT_REF,
            model_id=batch.model_id,
            payload=payload,
            expected_output_kind=(
                DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS
            ),
        )

    async def _reduced_rewrite(
        self,
        *,
        work_item: WorkItem,
        batch: DraftClaimCompactionBatchForDispatch,
    ) -> DraftClaimCompactionAttemptInput:
        state = await self.reduction_state_repository.load_planner_state(
            workflow_run_id=batch.workflow_run_id,
            group_ref=batch.group_ref,
        )
        if state is None:
            raise DraftClaimCompactionPayloadUnavailable(
                "draft claim compaction reduction state is unavailable",
            )
        if not batch.member_observation_refs:
            raise DraftClaimCompactionPayloadUnavailable(
                "reduced_rewrite batch does not contain compacted node refs yet",
            )

        nodes_by_ref = {node.node_ref: node for node in state.nodes}
        missing_refs = tuple(
            node_ref
            for node_ref in batch.member_observation_refs
            if node_ref not in nodes_by_ref
        )
        if missing_refs:
            raise DraftClaimCompactionPayloadUnavailable(
                "reduced_rewrite batch does not contain compacted node refs yet: "
                + ", ".join(missing_refs),
            )

        compacted_nodes = tuple(
            nodes_by_ref[node_ref] for node_ref in batch.member_observation_refs
        )
        for node in compacted_nodes:
            if node.node_kind is not DraftClaimCompactionNodeKind.COMPACTED:
                raise DraftClaimCompactionPayloadUnavailable(
                    "reduced_rewrite batch must reference compacted nodes only",
                )
            if not node.active:
                raise DraftClaimCompactionPayloadUnavailable(
                    "reduced_rewrite batch must reference active compacted nodes",
                )

        payload = DraftClaimReducedRewritePayload(
            compacted_claims=tuple(
                _reduced_input_claim(node) for node in compacted_nodes
            )
        ).to_json_dict()

        return DraftClaimCompactionAttemptInput(
            workflow_run_id=batch.workflow_run_id,
            group_ref=batch.group_ref,
            batch_ref=batch.batch_ref,
            work_item_id=work_item.work_item_id,
            prompt_kind=DraftClaimCompactionPromptKind.REDUCED_CLAIM_REWRITE,
            prompt_ref=REDUCED_CLAIM_REWRITE_PROMPT_REF,
            model_id=batch.model_id,
            payload=payload,
            expected_output_kind=(
                DraftClaimCompactionExpectedOutputKind.REDUCED_REWRITE
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


def _mixed_compacted_prompt_claim(
    node: DraftClaimCompactionNode,
) -> DraftClaimCompactionPromptClaim:
    if node.compacted_claim is None:
        raise DraftClaimCompactionPayloadUnavailable(
            f"compacted node has no compacted_claim: {node.node_ref}",
        )
    return DraftClaimCompactionPromptClaim(
        claim_id=node.node_ref,
        claim=node.compacted_claim,
        questions=(),
        exclusion_scope=(),
        granularity=node.compacted_granularity or "composite",
    )


def _raw_prompt_claim(
    claim: DraftClaimForCompaction,
) -> DraftClaimCompactionPromptClaim:
    return DraftClaimCompactionPromptClaim(
        claim_id=claim.observation_ref,
        claim=claim.claim,
        questions=_dedupe_preserving_order(claim.possible_questions),
        exclusion_scope=_dedupe_preserving_order(claim.exclusion_scope),
        granularity=claim.granularity,
    )


def _dedupe_preserving_order(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise TypeError("values must contain str")
        normalized = value.strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)


def _reduced_input_claim(
    node: DraftClaimCompactionNode,
) -> DraftClaimReducedRewriteInputClaim:
    if node.compacted_key is None:
        raise DraftClaimCompactionPayloadUnavailable(
            f"compacted node has no compacted_key: {node.node_ref}",
        )
    if node.compacted_claim is None:
        raise DraftClaimCompactionPayloadUnavailable(
            f"compacted node has no compacted_claim: {node.node_ref}",
        )
    return DraftClaimReducedRewriteInputClaim(
        key=node.compacted_key,
        claim=node.compacted_claim,
        triples=node.compacted_triples,
    )
