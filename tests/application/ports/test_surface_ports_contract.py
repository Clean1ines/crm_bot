from src.application.ports.knowledge import (
    KnowledgeSurfaceCompilerRunPort,
    KnowledgeSurfaceCompilerStagePort,
    KnowledgeSurfaceDraftPort,
    KnowledgeSurfaceMergeDecisionPort,
    KnowledgeSurfacePublicationPort,
    KnowledgeSurfaceQuestionOwnershipPort,
    KnowledgeSurfaceRelationPort,
    KnowledgeSurfaceSourceUnitPort,
)


def test_surface_ports_are_exported() -> None:
    assert KnowledgeSurfaceCompilerRunPort
    assert KnowledgeSurfaceCompilerStagePort
    assert KnowledgeSurfaceSourceUnitPort
    assert KnowledgeSurfaceDraftPort
    assert KnowledgeSurfaceRelationPort
    assert KnowledgeSurfaceQuestionOwnershipPort
    assert KnowledgeSurfaceMergeDecisionPort
    assert KnowledgeSurfacePublicationPort
