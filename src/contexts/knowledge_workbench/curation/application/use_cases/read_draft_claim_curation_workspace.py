from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationWorkspaceItem,
    DraftClaimCurationWorkspaceSnapshot,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_workspace_repository_port import (
    DraftClaimCurationWorkspaceRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadModel,
    DraftClaimObservationReadRepositoryPort,
)
from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.domain.project_plane.json_types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class DraftClaimCurationWorkspaceReadResult:
    snapshot: DraftClaimCurationWorkspaceSnapshot
    progress: JsonObject
    item_provenance: tuple["DraftClaimCurationItemProvenance", ...]

    def to_json_dict(self) -> JsonObject:
        provenance_by_item_ref = {
            item.item_ref: item.to_json_dict() for item in self.item_provenance
        }
        items: list[JsonValue] = []
        for item in self.snapshot.items:
            item_json = item.to_json_dict()
            item_json["provenance"] = provenance_by_item_ref.get(
                item.item_ref,
                {"raw_claims": [], "source_units": []},
            )
            item_json["audit"] = {}
            items.append(item_json)
        return {
            "workspace": self.snapshot.workspace.to_json_dict(),
            "progress": self.progress,
            "items": items,
        }


@dataclass(frozen=True, slots=True)
class DraftClaimCurationItemProvenance:
    item_ref: str
    raw_claims: tuple[DraftClaimObservationReadModel, ...]
    source_units: tuple[SourceUnit, ...]

    def to_json_dict(self) -> JsonObject:
        return {
            "raw_claims": [_raw_claim_json(raw_claim) for raw_claim in self.raw_claims],
            "source_units": [
                _source_unit_json(source_unit) for source_unit in self.source_units
            ],
        }


@dataclass(frozen=True, slots=True)
class ReadDraftClaimCurationWorkspace:
    curation_workspace_repository: DraftClaimCurationWorkspaceRepositoryPort
    draft_claim_observation_read_repository: DraftClaimObservationReadRepositoryPort
    source_management_repository: SourceManagementRepositoryPort
    compaction_reduction_state_repository: (
        DraftClaimCompactionReductionStateRepositoryPort | None
    ) = None

    async def execute(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimCurationWorkspaceReadResult | None:
        snapshot = (
            await self.curation_workspace_repository.get_workspace_by_workflow_run_id(
                workflow_run_id=workflow_run_id,
            )
        )
        if snapshot is None:
            return None
        progress = await self._progress(workflow_run_id)
        provenance_items: list[DraftClaimCurationItemProvenance] = []
        for item in snapshot.items:
            provenance_items.append(await self._item_provenance(item))
        provenance = tuple(provenance_items)
        return DraftClaimCurationWorkspaceReadResult(
            snapshot=snapshot,
            progress=progress,
            item_provenance=provenance,
        )

    async def _progress(self, workflow_run_id: str) -> JsonObject:
        if self.compaction_reduction_state_repository is None:
            return {}
        summary = await self.compaction_reduction_state_repository.summarize_compaction_progress(
            workflow_run_id=workflow_run_id,
        )
        return {
            "workflow_run_id": summary.workflow_run_id,
            "group_count": summary.group_count,
            "done_group_count": summary.done_group_count,
            "waiting_user_model_choice_group_count": (
                summary.waiting_user_model_choice_group_count
            ),
            "active_group_count": summary.active_group_count,
            "active_node_count": summary.active_node_count,
            "pending_comparison_count": summary.pending_comparison_count,
        }

    async def _item_provenance(
        self,
        item: DraftClaimCurationWorkspaceItem,
    ) -> DraftClaimCurationItemProvenance:
        raw_claims = (
            await self.draft_claim_observation_read_repository.list_by_observation_refs(
                observation_refs=item.source_claim_refs,
            )
        )
        source_units = await self._source_units_for_raw_claims(raw_claims)
        return DraftClaimCurationItemProvenance(
            item_ref=item.item_ref,
            raw_claims=raw_claims,
            source_units=source_units,
        )

    async def _source_units_for_raw_claims(
        self,
        raw_claims: tuple[DraftClaimObservationReadModel, ...],
    ) -> tuple[SourceUnit, ...]:
        seen: set[str] = set()
        result: list[SourceUnit] = []
        for raw_claim in raw_claims:
            if raw_claim.source_unit_ref in seen:
                continue
            seen.add(raw_claim.source_unit_ref)
            source_unit = await self.source_management_repository.load_source_unit(
                SourceUnitRef(raw_claim.source_unit_ref)
            )
            if source_unit is not None:
                result.append(source_unit)
        return tuple(result)


def _raw_claim_json(raw_claim: DraftClaimObservationReadModel) -> JsonObject:
    return {
        "raw_claim_ref": raw_claim.observation_ref,
        "claim": raw_claim.claim,
        "granularity": raw_claim.granularity,
        "possible_questions": list(raw_claim.possible_questions),
        "exclusion_scope": raw_claim.exclusion_scope,
        "evidence_block": raw_claim.evidence_block,
        "source_unit_ref": raw_claim.source_unit_ref,
        "created_at": raw_claim.created_at.isoformat(),
    }


def _source_unit_json(source_unit: SourceUnit) -> JsonObject:
    return {
        "source_unit_ref": source_unit.unit_ref.value,
        "source_document_ref": source_unit.document_ref.value,
        "unit_kind": source_unit.unit_kind.value,
        "heading_path": list(source_unit.heading_path.parts),
        "source_unit_text": source_unit.text.value,
        "ordinal": source_unit.ordinal,
        "created_at": source_unit.created_at.isoformat(),
    }
