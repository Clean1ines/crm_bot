from __future__ import annotations

from pathlib import Path

from src.domain.project_plane.knowledge_workbench.retention_policy import (
    WorkbenchProcessingEntity,
    publish_retention_plan,
)


POLICY = Path("src/domain/project_plane/knowledge_workbench/retention_policy.py")


def test_workbench_retention_policy_is_not_provider_specific() -> None:
    source = POLICY.read_text(encoding="utf-8")

    forbidden = (
        "Groq",
        "AsyncGroq",
        "GROQ_API_KEY",
        "RotatingAsyncGroq",
        "GroqLlmJsonInvocationAdapter",
    )
    for marker in forbidden:
        assert marker not in source


def test_workbench_retention_policy_does_not_restore_old_compiler_domain() -> None:
    source = POLICY.read_text(encoding="utf-8")

    forbidden = (
        "knowledge_compilation",
        "AnswerCandidate",
        "CandidateCluster",
        "CanonicalKnowledgeEntry",
        "KnowledgeSurfaceCompilerPort",
        "RetrievalSurfaceCandidate",
        "SurfaceDiscoveryResult",
        "LocalSurfaceRelation",
    )
    for marker in forbidden:
        assert marker not in source


def test_publish_retention_policy_keeps_raw_llm_outputs_transient() -> None:
    plan = publish_retention_plan()

    assert plan.is_transient_until_publication(
        WorkbenchProcessingEntity.PROCESSING_NODE_ARTIFACT
    )
    assert plan.is_transient_until_publication(
        WorkbenchProcessingEntity.MODEL_INVOCATION_DETAIL
    )


def test_publish_retention_policy_keeps_only_final_registry_and_surfaces() -> None:
    plan = publish_retention_plan()

    assert plan.is_retained_after_publication(
        WorkbenchProcessingEntity.FINAL_QUESTION_REGISTRY
    )
    assert plan.is_retained_after_publication(
        WorkbenchProcessingEntity.FINAL_REGISTRY_SNAPSHOT
    )
    assert plan.is_retained_after_publication(
        WorkbenchProcessingEntity.KNOWLEDGE_SURFACE
    )
    assert plan.is_retained_after_publication(
        WorkbenchProcessingEntity.RUNTIME_RETRIEVAL_ENTRY
    )

    assert plan.is_transient_until_publication(
        WorkbenchProcessingEntity.INTERMEDIATE_REGISTRY_SNAPSHOT
    )
    assert plan.is_transient_until_publication(
        WorkbenchProcessingEntity.SURFACE_CANDIDATE
    )
    assert plan.is_transient_until_publication(
        WorkbenchProcessingEntity.DEDUPLICATED_SURFACE_CANDIDATE
    )
    assert plan.is_transient_until_publication(
        WorkbenchProcessingEntity.FINAL_SURFACE_DRAFT
    )


def test_publish_retention_policy_makes_resume_impossible_after_purge() -> None:
    plan = publish_retention_plan()

    assert plan.state_after_publication.value == "transient_purged"
    assert plan.resume_allowed_after_transient_purge is False
