from __future__ import annotations

from pathlib import Path

from src.application.services.knowledge_generated_entry_repair import (
    repair_generated_entry,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    build_embedding_text,
)


def _entry(
    *,
    answer: str,
    source_excerpt: str = "CRM бот помогает продавать и отвечать клиентам.",
    title: str = "FAQ",
    canonical_question: str = "Что делает сервис?",
    questions: tuple[str, ...] = ("Что делает сервис?",),
    synonyms: tuple[str, ...] = ("crm бот",),
    tags: tuple[str, ...] = ("faq",),
    embedding_text: str = "stale embedding",
) -> KnowledgePreprocessingEntry:
    return KnowledgePreprocessingEntry(
        title=title,
        canonical_question=canonical_question,
        answer=answer,
        source_excerpt=source_excerpt,
        questions=questions,
        synonyms=synonyms,
        tags=tags,
        embedding_text=embedding_text,
    )


def test_markdown_heading_repair_strips_heading_markers() -> None:
    repaired, warnings = repair_generated_entry(
        _entry(answer="## CRM бот\nCRM бот помогает продавать."),
        source_excerpt="CRM бот помогает продавать.",
    )

    assert repaired.answer == "CRM бот CRM бот помогает продавать."
    assert "generated_answer_markdown_heading_repaired" in warnings


def test_service_label_repair_removes_expected_topic_label() -> None:
    repaired, warnings = repair_generated_entry(
        _entry(answer="Expected topic: CRM бот помогает продавать."),
        source_excerpt="CRM бот помогает продавать.",
    )

    assert repaired.answer == "CRM бот помогает продавать."
    assert "generated_answer_service_label_repaired" in warnings


def test_conversational_prefix_repair_removes_greeting() -> None:
    repaired, warnings = repair_generated_entry(
        _entry(answer="Здравствуйте, CRM бот помогает продавать."),
        source_excerpt="CRM бот помогает продавать.",
    )

    assert repaired.answer == "CRM бот помогает продавать."
    assert "generated_answer_conversational_prefix_repaired" in warnings


def test_forbidden_cjk_removed_only_when_source_has_no_cjk() -> None:
    repaired, warnings = repair_generated_entry(
        _entry(
            answer="CRM бот помогает продавать 中文",
            title="FAQ 中文",
            canonical_question="Что делает сервис? 中文",
            questions=("Что делает сервис? 中文",),
            synonyms=("crm bot 中文",),
            tags=("faq 中文",),
        ),
        source_excerpt="CRM бот помогает продавать.",
    )

    assert "中文" not in repaired.answer
    assert "中文" not in repaired.title
    assert "中文" not in repaired.canonical_question
    assert all("中文" not in value for value in repaired.questions)
    assert all("中文" not in value for value in repaired.synonyms)
    assert all("中文" not in value for value in repaired.tags)
    assert "generated_answer_forbidden_script_repaired" in warnings
    assert "generated_enrichment_forbidden_script_repaired" in warnings

    preserved, preserved_warnings = repair_generated_entry(
        _entry(answer="CRM бот помогает продавать 中文"),
        source_excerpt="Источник содержит 中文.",
    )

    assert "中文" in preserved.answer
    assert "generated_answer_forbidden_script_repaired" not in preserved_warnings


def test_empty_answer_falls_back_to_source_excerpt_digest() -> None:
    repaired, warnings = repair_generated_entry(
        _entry(answer="中文", source_excerpt=""),
        source_excerpt="CRM бот помогает продавать и отвечать клиентам.",
    )

    assert repaired.answer == "CRM бот помогает продавать и отвечать клиентам."
    assert repaired.source_excerpt == "CRM бот помогает продавать и отвечать клиентам."
    assert "generated_answer_forbidden_script_repaired" in warnings
    assert "generated_answer_empty_after_repair_warning" in warnings
    assert "generated_source_excerpt_empty_after_repair_warning" in warnings


def test_embedding_text_is_rebuilt_after_repair() -> None:
    entry = _entry(
        answer="Expected topic: CRM бот помогает продавать.",
        source_excerpt="CRM бот помогает продавать.",
        embedding_text="stale embedding",
    )

    repaired, _warnings = repair_generated_entry(
        entry,
        source_excerpt="CRM бот помогает продавать.",
    )

    assert repaired.embedding_text == build_embedding_text(repaired)
    assert repaired.embedding_text != "stale embedding"


def test_ingestion_facade_no_longer_keeps_generated_repair_alias() -> None:
    ingestion_source = Path(
        "src/application/services/knowledge_ingestion_service.py"
    ).read_text(encoding="utf-8")
    repair_source = Path(
        "src/application/services/knowledge_generated_entry_repair.py"
    ).read_text(encoding="utf-8")

    assert (
        "from src.application.services.knowledge_generated_entry_repair import"
        not in (ingestion_source)
    )
    assert "_repair_generated_entry" not in ingestion_source

    assert "def repair_generated_entry(" in repair_source
    for marker in (
        "def _entry_has_markdown_heading(",
        "def _strip_markdown_heading_markers(",
        "def _remove_forbidden_cjk_korean_chars(",
        "def _strip_service_labels(",
        "def _strip_conversational_prefix(",
        "def _source_answer_coverage_ratio(",
    ):
        assert marker in repair_source
        assert marker not in ingestion_source
