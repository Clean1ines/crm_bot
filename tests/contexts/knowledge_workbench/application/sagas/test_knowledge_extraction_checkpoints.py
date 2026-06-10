from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_checkpoints import (
    replace_or_append_checkpoint,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionPhaseStatus,
)


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _later() -> datetime:
    return datetime(2026, 6, 10, 13, 0, tzinfo=timezone.utc)


def _checkpoint(
    phase_key: KnowledgeExtractionPhaseKey,
    *,
    payload_value: object,
    updated_at: datetime | None = None,
    phase_status: KnowledgeExtractionPhaseStatus = (
        KnowledgeExtractionPhaseStatus.COMPLETED
    ),
) -> KnowledgeExtractionPhaseCheckpoint:
    return KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id="workflow-1",
        phase_key=phase_key,
        phase_status=phase_status,
        expected_count=1,
        completed_count=1,
        idempotency_key=f"checkpoint:{phase_key.value}",
        checkpoint_payload={"value": payload_value},
        updated_at=_now() if updated_at is None else updated_at,
    )


def test_appends_checkpoint_when_phase_is_absent() -> None:
    existing = (
        _checkpoint(
            KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED,
            payload_value="accepted",
        ),
    )
    new_checkpoint = _checkpoint(
        KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
        payload_value="persisted",
    )

    result = replace_or_append_checkpoint(existing, new_checkpoint)

    assert len(result) == 2
    assert result[-1] is new_checkpoint
    assert existing == (
        _checkpoint(
            KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED,
            payload_value="accepted",
        ),
    )


def test_replaces_checkpoint_when_phase_exists() -> None:
    old_checkpoint = _checkpoint(
        KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        payload_value="old",
        updated_at=_now(),
    )
    replacement = _checkpoint(
        KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        payload_value="new",
        updated_at=_later(),
        phase_status=KnowledgeExtractionPhaseStatus.READY,
    )

    result = replace_or_append_checkpoint((old_checkpoint,), replacement)

    assert len(result) == 1
    assert result[0] is replacement
    assert tuple(checkpoint.phase_key for checkpoint in result) == (
        KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
    )


def test_preserves_order_when_replacing_middle_checkpoint() -> None:
    first = _checkpoint(
        KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED,
        payload_value="first",
    )
    middle = _checkpoint(
        KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
        payload_value="middle-old",
    )
    last = _checkpoint(
        KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        payload_value="last",
    )
    replacement = _checkpoint(
        KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
        payload_value="middle-new",
    )

    result = replace_or_append_checkpoint((first, middle, last), replacement)

    assert result == (first, replacement, last)
    assert tuple(checkpoint.phase_key for checkpoint in result) == (
        KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED,
        KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
        KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
    )


def test_rejects_non_tuple_checkpoints() -> None:
    with pytest.raises(TypeError, match="checkpoints must be tuple"):
        replace_or_append_checkpoint(
            [
                _checkpoint(
                    KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED,
                    payload_value="accepted",
                ),
            ],
            _checkpoint(
                KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
                payload_value="persisted",
            ),
        )


def test_rejects_invalid_checkpoint_argument() -> None:
    with pytest.raises(TypeError, match="checkpoint must be"):
        replace_or_append_checkpoint((), object())


def test_rejects_invalid_item_in_checkpoints_tuple() -> None:
    with pytest.raises(TypeError, match="checkpoints must contain only"):
        replace_or_append_checkpoint(
            (
                _checkpoint(
                    KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED,
                    payload_value="accepted",
                ),
                object(),
            ),
            _checkpoint(
                KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
                payload_value="persisted",
            ),
        )


def test_checkpoint_helper_source_guard() -> None:
    helper_text = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "knowledge_extraction_checkpoints.py",
    ).read_text(encoding="utf-8")
    phase_transition_text = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "advance_to_draft_observation_scheduling_phase.py",
    ).read_text(encoding="utf-8")

    helper_required = (
        "replace_or_append_checkpoint",
        "KnowledgeExtractionPhaseCheckpoint",
    )
    helper_forbidden = (
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "execution_runtime",
        "Postgres",
        "asyncpg",
        "queue",
        "worker",
        "lease",
        "Groq",
        "qwen",
        _marker("A", "ny"),
        _marker("type", ": ignore"),
    )
    phase_required = ("replace_or_append_checkpoint",)
    phase_forbidden = (
        "_replace_or_append_checkpoint",
        "from .knowledge_extraction_saga import _replace_checkpoints",
    )

    for marker in helper_required:
        assert marker in helper_text
    for marker in helper_forbidden:
        assert marker not in helper_text
    for marker in phase_required:
        assert marker in phase_transition_text
    for marker in phase_forbidden:
        assert marker not in phase_transition_text



def _marker(*parts: str) -> str:
    return "".join(parts)
