from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.application.sagas import llm_dispatch_ownership


@dataclass(frozen=True, slots=True)
class LlmDispatchOwnershipPolicy:
    capacity_queue_runtime_core_enabled: bool
    claim_builder_capacity_drain_bridge_enabled: bool
    draft_claim_compaction_capacity_drain_bridge_enabled: bool
    capacity_queue_owns_llm_dispatch: bool

    @property
    def claim_builder_capacity_queue_owns_dispatch(self) -> bool:
        return (
            self.capacity_queue_runtime_core_enabled
            and self.capacity_queue_owns_llm_dispatch
            and self.claim_builder_capacity_drain_bridge_enabled
        )

    @property
    def draft_claim_compaction_capacity_queue_owns_dispatch(self) -> bool:
        return (
            self.capacity_queue_runtime_core_enabled
            and self.capacity_queue_owns_llm_dispatch
            and self.draft_claim_compaction_capacity_drain_bridge_enabled
        )


def current_llm_dispatch_ownership_policy() -> LlmDispatchOwnershipPolicy:
    return LlmDispatchOwnershipPolicy(
        capacity_queue_runtime_core_enabled=(
            llm_dispatch_ownership.CAPACITY_QUEUE_RUNTIME_CORE_ENABLED
        ),
        claim_builder_capacity_drain_bridge_enabled=(
            llm_dispatch_ownership.CLAIM_BUILDER_CAPACITY_DRAIN_BRIDGE_ENABLED
        ),
        draft_claim_compaction_capacity_drain_bridge_enabled=(
            llm_dispatch_ownership.DRAFT_CLAIM_COMPACTION_CAPACITY_DRAIN_BRIDGE_ENABLED
        ),
        capacity_queue_owns_llm_dispatch=(
            llm_dispatch_ownership.CAPACITY_QUEUE_OWNS_LLM_DISPATCH
        ),
    )
