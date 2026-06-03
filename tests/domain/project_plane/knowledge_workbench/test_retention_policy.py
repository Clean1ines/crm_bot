from __future__ import annotations

import pytest

from src.domain.project_plane.knowledge_workbench.retention_policy import (
    FAQ_DOCUMENT_PUBLISH_RETENTION_RULES,
    WorkbenchProcessingEntity,
    WorkbenchPublishRetentionPlan,
    WorkbenchRetentionState,
    publish_retention_plan,
)


def test_publish_retention_plan_requires_final_registry_surfaces_and_runtime() -> None:
    plan = publish_retention_plan()

    assert plan.processing_method == "faq_section_registry_v1"
    assert (
        plan.state_before_publication is WorkbenchRetentionState.READY_FOR_PUBLICATION
    )
    assert plan.state_after_publication is WorkbenchRetentionState.TRANSIENT_PURGED
    assert plan.purge_transient_after_publication is True
    assert plan.resume_allowed_after_transient_purge is False
    assert plan.requires_final_registry is True
    assert plan.requires_final_surfaces is True
    assert plan.requires_runtime_publication is True


def test_processing_workspace_entities_are_transient_until_publication() -> None:
    plan = publish_retention_plan()

    transient_entities = (
        WorkbenchProcessingEntity.DOCUMENT_SECTION,
        WorkbenchProcessingEntity.KNOWLEDGE_PROCESSING_RUN,
        WorkbenchProcessingEntity.PROCESSING_NODE_RUN,
        WorkbenchProcessingEntity.PROCESSING_NODE_ARTIFACT,
        WorkbenchProcessingEntity.MODEL_INVOCATION_DETAIL,
        WorkbenchProcessingEntity.SECTION_FINDING,
        WorkbenchProcessingEntity.DETERMINISTIC_DEDUP_RESULT,
        WorkbenchProcessingEntity.REGISTRY_UPDATE_PROPOSAL,
        WorkbenchProcessingEntity.REGISTRY_UPDATE_APPLICATION,
        WorkbenchProcessingEntity.INTERMEDIATE_REGISTRY_SNAPSHOT,
    )

    for entity in transient_entities:
        assert plan.is_transient_until_publication(entity), entity


def test_intermediate_surface_lineage_is_transient_until_publication() -> None:
    plan = publish_retention_plan()

    for entity in (
        WorkbenchProcessingEntity.SURFACE_CANDIDATE,
        WorkbenchProcessingEntity.DEDUPLICATED_SURFACE_CANDIDATE,
        WorkbenchProcessingEntity.FINAL_SURFACE_DRAFT,
        WorkbenchProcessingEntity.FINAL_RECONCILIATION_RUN,
        WorkbenchProcessingEntity.FINAL_RECONCILIATION_SUGGESTION,
        WorkbenchProcessingEntity.SURFACE_MATERIALIZATION_RESULT,
    ):
        assert plan.is_transient_until_publication(entity), entity


def test_final_knowledge_state_is_retained_after_publication() -> None:
    plan = publish_retention_plan()

    retained_entities = (
        WorkbenchProcessingEntity.KNOWLEDGE_DOCUMENT_METADATA,
        WorkbenchProcessingEntity.FINAL_QUESTION_REGISTRY,
        WorkbenchProcessingEntity.FINAL_REGISTRY_SNAPSHOT,
        WorkbenchProcessingEntity.FINAL_REGISTRY_ENTRY,
        WorkbenchProcessingEntity.KNOWLEDGE_SURFACE,
        WorkbenchProcessingEntity.SURFACE_RELATION,
        WorkbenchProcessingEntity.RUNTIME_PUBLICATION,
        WorkbenchProcessingEntity.RUNTIME_RETRIEVAL_ENTRY,
        WorkbenchProcessingEntity.MODEL_USAGE_AGGREGATE,
    )

    for entity in retained_entities:
        assert plan.is_retained_after_publication(entity), entity


def test_publish_retention_rules_cover_every_declared_entity_once() -> None:
    plan = publish_retention_plan()

    entities = [rule.entity for rule in plan.rules]

    assert len(entities) == len(set(entities))
    assert set(entities) == set(WorkbenchProcessingEntity)


def test_publish_retention_plan_rejects_resume_after_transient_purge() -> None:
    with pytest.raises(ValueError, match="resume must be forbidden"):
        WorkbenchPublishRetentionPlan(
            processing_method="faq_section_registry_v1",
            state_before_publication=WorkbenchRetentionState.READY_FOR_PUBLICATION,
            state_after_publication=WorkbenchRetentionState.TRANSIENT_PURGED,
            rules=FAQ_DOCUMENT_PUBLISH_RETENTION_RULES,
            purge_transient_after_publication=True,
            resume_allowed_after_transient_purge=True,
            requires_final_registry=True,
            requires_final_surfaces=True,
            requires_runtime_publication=True,
        )


def test_publish_retention_plan_rejects_missing_purge_step() -> None:
    with pytest.raises(ValueError, match="must purge transient"):
        WorkbenchPublishRetentionPlan(
            processing_method="faq_section_registry_v1",
            state_before_publication=WorkbenchRetentionState.READY_FOR_PUBLICATION,
            state_after_publication=WorkbenchRetentionState.TRANSIENT_PURGED,
            rules=FAQ_DOCUMENT_PUBLISH_RETENTION_RULES,
            purge_transient_after_publication=False,
            resume_allowed_after_transient_purge=False,
            requires_final_registry=True,
            requires_final_surfaces=True,
            requires_runtime_publication=True,
        )
