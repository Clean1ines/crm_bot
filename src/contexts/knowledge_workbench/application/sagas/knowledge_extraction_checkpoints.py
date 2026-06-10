from __future__ import annotations

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseCheckpoint,
)


def replace_or_append_checkpoint(
    checkpoints: tuple[KnowledgeExtractionPhaseCheckpoint, ...],
    checkpoint: KnowledgeExtractionPhaseCheckpoint,
) -> tuple[KnowledgeExtractionPhaseCheckpoint, ...]:
    if not isinstance(checkpoints, tuple):
        raise TypeError("checkpoints must be tuple")
    if not isinstance(checkpoint, KnowledgeExtractionPhaseCheckpoint):
        raise TypeError("checkpoint must be KnowledgeExtractionPhaseCheckpoint")

    for existing in checkpoints:
        if not isinstance(existing, KnowledgeExtractionPhaseCheckpoint):
            raise TypeError(
                "checkpoints must contain only KnowledgeExtractionPhaseCheckpoint"
            )

    replaced = False
    merged: list[KnowledgeExtractionPhaseCheckpoint] = []
    for existing in checkpoints:
        if existing.phase_key is checkpoint.phase_key:
            merged.append(checkpoint)
            replaced = True
        else:
            merged.append(existing)

    if not replaced:
        merged.append(checkpoint)

    return tuple(merged)
