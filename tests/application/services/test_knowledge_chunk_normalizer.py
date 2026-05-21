from __future__ import annotations

from src.application.services.knowledge_chunk_normalizer import (
    log_knowledge_chunk_audit,
    normalize_knowledge_chunks,
)


class _FakeLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def debug(self, message: str, *, extra: dict[str, object] | None = None) -> None:
        self.events.append((message, extra or {}))

    def info(self, message: str, *, extra: dict[str, object] | None = None) -> None:
        self.events.append((message, extra or {}))

    def warning(self, message: str, *, extra: dict[str, object] | None = None) -> None:
        self.events.append((message, extra or {}))

    def error(self, message: str, *, extra: dict[str, object] | None = None) -> None:
        self.events.append((message, extra or {}))

    def exception(
        self, message: str, *, extra: dict[str, object] | None = None
    ) -> None:
        self.events.append((message, extra or {}))


def test_normalize_knowledge_chunks_accepts_text_and_mappings() -> None:
    chunks = normalize_knowledge_chunks(
        [
            "  plain answer  ",
            "",
            {"content": "  structured answer  ", "questions": ["Q?"]},
            {"title": "missing content"},
            123,
        ]
    )

    assert chunks == [
        {"content": "plain answer"},
        {"content": "structured answer", "questions": ["Q?"]},
    ]


def test_log_knowledge_chunk_audit_reports_counts_without_content_dump() -> None:
    logger = _FakeLogger()
    chunks = [
        {"content": "A", "title": "T", "extra": "X"},
        {"content": "B", "questions": ["Q1", "Q2"]},
    ]

    log_knowledge_chunk_audit(logger, chunks, context="unit_test")

    assert len(logger.events) == 1
    message, extra = logger.events[0]
    assert message == "Knowledge upload chunk audit"
    assert extra["context"] == "unit_test"
    assert extra["chunk_count"] == 2
    assert extra["field_counts"] == {
        "content": 2,
        "entry_kind": 0,
        "title": 1,
        "source_excerpt": 0,
        "questions": 1,
        "synonyms": 0,
        "tags": 0,
        "embedding_text": 0,
    }
    assert extra["unknown_field_counts"] == {"extra": 1}
    assert extra["content_length"] == {"min": 1, "max": 1, "avg": 1.0}
