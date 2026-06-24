from __future__ import annotations

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    CapacityAdmissionLaneTarget,
)
from src.contexts.capacity_admission_queue.application.capacity_admission_lane_target_resolver import (
    CapacityAdmissionLaneTargetRegistry,
)


def test_resolves_lane_target_by_work_kind() -> None:
    target = CapacityAdmissionLaneTarget(
        provider="groq",
        account_ref="groq-account-1",
        model_ref="qwen/qwen3-32b",
    )
    registry = CapacityAdmissionLaneTargetRegistry(
        targets_by_work_kind={
            "knowledge_workbench.claim_builder.section_extraction": target,
        }
    )

    assert (
        registry.resolve_lane_target_for_work_kind(
            "knowledge_workbench.claim_builder.section_extraction"
        )
        == target
    )


def test_returns_none_for_unconfigured_work_kind() -> None:
    registry = CapacityAdmissionLaneTargetRegistry(targets_by_work_kind={})

    assert registry.resolve_lane_target_for_work_kind("unknown.work") is None
