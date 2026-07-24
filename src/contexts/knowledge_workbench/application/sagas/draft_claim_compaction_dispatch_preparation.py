from __future__ import annotations

from dataclasses import dataclass, field

from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    DueWorkItemRecord,
)
from src.contexts.knowledge_workbench.application.sagas.claim_builder_dispatch_preparation import (
    ClaimBuilderDispatchPreparationBuilder,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelRouteCatalog,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile


DRAFT_CLAIM_COMPACTION_DISPATCH_PROFILE_ID = (
    "draft_claim_compaction.real_due_batch"
)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionDispatchPreparationBuilder:
    """Build dispatch capacity inputs for draft-claim compaction work items."""

    _capacity_builder: ClaimBuilderDispatchPreparationBuilder = field(
        default_factory=ClaimBuilderDispatchPreparationBuilder,
    )

    def route_catalog(
        self,
        *,
        default_catalog: LlmModelRouteCatalog,
    ) -> LlmModelRouteCatalog:
        if not isinstance(default_catalog, LlmModelRouteCatalog):
            raise TypeError("default_catalog must be LlmModelRouteCatalog")
        return default_catalog

    def build_profile_from_due_work_items(
        self,
        due_work_items: tuple[DueWorkItemRecord, ...],
    ) -> LlmTaskCapacityProfile:
        base_profile = self._capacity_builder.build_profile_from_due_work_items(
            due_work_items
        )
        return LlmTaskCapacityProfile(
            profile_id=DRAFT_CLAIM_COMPACTION_DISPATCH_PROFILE_ID,
            estimated_prompt_tokens=base_profile.estimated_prompt_tokens,
            estimated_completion_tokens=base_profile.estimated_completion_tokens,
            estimated_requests=base_profile.estimated_requests,
        )

    def build_account_capacities(
        self,
        *,
        active_model_ref: str,
        provider_account_refs: tuple[str, ...],
        model_profiles: tuple[ModelProfile, ...],
    ) -> tuple[LlmProviderAccountCapacity, ...]:
        return self._capacity_builder.build_account_capacities(
            active_model_ref=active_model_ref,
            provider_account_refs=provider_account_refs,
            model_profiles=model_profiles,
        )
