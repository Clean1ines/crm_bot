from __future__ import annotations

from src.application.services.knowledge_ingestion_service import (
    _apply_semantic_merge_tightening_decisions,
    _compiler_source_chunks_for_preprocessing,
    _raw_answer_candidates_from_preprocessing_entries,
)
from src.application.services.markdown_structure_extractor import (
    MarkdownStructureExtractor,
)
from src.domain.project_plane.knowledge_compilation import SourceChunk
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgeAnswerResolutionDecision,
)


def _json_chunk(content: str) -> dict[str, object]:
    return {"content": content}


def test_markdown_extractor_preserves_faq_container_children() -> None:
    source = """## 31. Частые вопросы и правильные ответы

### Что это за сервис?
Это AI-ассистент...

### Чем вы занимаетесь?
Мы помогаем бизнесу...
"""
    document = MarkdownStructureExtractor().extract(
        document_title="test.md",
        source_text=source,
    )
    units = MarkdownStructureExtractor().to_semantic_units(document)

    assert len(units) == 1
    unit = units[0]
    assert unit.title == "31. Частые вопросы и правильные ответы"
    assert [child.title for child in unit.children] == [
        "Что это за сервис?",
        "Чем вы занимаетесь?",
    ]
    assert "Это AI-ассистент" in unit.children[0].body
    assert "Мы помогаем бизнесу" in unit.children[1].body
    assert unit.source_span.section_path == (
        "test.md",
        "31. Частые вопросы и правильные ответы",
    )


def test_markdown_semantic_chunks_keep_test_suite_as_one_parent_unit() -> None:
    source = """## 32. Тестовые вопросы для проверки базы знаний

Эти вопросы нужно использовать для тестирования preview и качества ответов.

### О продукте
- что это за сервис?
- чем вы занимаетесь?

Ожидаемая тема:
Описание продукта...
"""
    chunks = _compiler_source_chunks_for_preprocessing(
        file_name="test.md",
        chunks=[_json_chunk(source)],
        mode="faq",
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["source_format"] == "markdown"
    assert chunk["section_title"] == "32. Тестовые вопросы для проверки базы знаний"
    assert "что это за сервис?" in str(chunk["content"])
    assert "Ожидаемая тема" in str(chunk["content"])
    assert isinstance(chunk["children"], list)
    assert chunk["metadata"]["kad_v1_semantic_source_unit"] is True


def test_markdown_semantic_chunks_keep_rag_rule_examples_inside_section() -> None:
    source = """## 34. Правило для RAG-поиска

Каждая тема должна быть отделена от других.

Не смешивать:
- возврат средств и отключение сервиса;
- цену и сроки внедрения;
"""
    chunks = _compiler_source_chunks_for_preprocessing(
        file_name="rules.md",
        chunks=[_json_chunk(source)],
        mode="faq",
    )

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["section_title"] == "34. Правило для RAG-поиска"
    assert "Каждая тема должна быть отделена" in str(chunk["content"])
    assert "возврат средств и отключение сервиса" in str(chunk["content"])
    assert "цену и сроки внедрения" in str(chunk["content"])


def test_semantic_merge_uses_answer_only_resolution_not_concatenation() -> None:
    entries = (
        KnowledgePreprocessingEntry(
            title="Возврат средств",
            canonical_question="Есть ли возврат средств?",
            answer="Условия возврата зависят от ситуации.",
            source_excerpt="Условия возврата зависят от ситуации.",
            questions=("Есть ли возврат средств?",),
            synonyms=("возврат",),
            tags=("оплата",),
        ),
        KnowledgePreprocessingEntry(
            title="Возврат оплаты",
            canonical_question="Можно ли вернуть оплату?",
            answer="Условия возврата средств зависят от этапа работы.",
            source_excerpt="Условия возврата средств зависят от этапа работы.",
            questions=("Можно ли вернуть оплату?",),
            synonyms=("вернуть оплату",),
            tags=("деньги",),
        ),
    )
    decision = KnowledgeAnswerResolutionDecision(
        case_id="g1",
        action="merge",
        candidate_ids=("entry-0", "entry-1"),
        canonical_answer="Возврат средств зависит от ситуации и этапа работы.",
    )

    merged, source_excerpts = _apply_semantic_merge_tightening_decisions(
        entries=entries,
        decisions=(decision,),
    )

    assert len(merged) == 1
    assert merged[0].answer == ("Возврат средств зависит от ситуации и этапа работы.")
    assert "Условия возврата зависят от ситуации. Условия возврата средств" not in (
        merged[0].answer
    )
    assert merged[0].canonical_question == "Есть ли возврат средств?"
    assert "Можно ли вернуть оплату?" in merged[0].questions
    assert "вернуть оплату" in merged[0].synonyms
    assert source_excerpts == (
        (
            "Условия возврата зависят от ситуации.",
            "Условия возврата средств зависят от этапа работы.",
        ),
    )


def test_raw_candidates_are_built_before_merge_publication() -> None:
    source_chunks = (
        SourceChunk(
            id="doc:0",
            document_id="doc",
            project_id="project",
            source_index=0,
            content="### Что это за сервис?\nЭто AI-ассистент...",
            section_title="31. Частые вопросы",
            start_offset=0,
            end_offset=42,
        ),
    )
    entries = (
        KnowledgePreprocessingEntry(
            title="Что это за сервис?",
            canonical_question="Что это за сервис?",
            answer="Это AI-ассистент.",
            source_excerpt="Это AI-ассистент...",
            questions=("Что это за сервис?",),
            source_chunk_indexes=(0,),
        ),
    )

    candidates = _raw_answer_candidates_from_preprocessing_entries(
        project_id="project",
        document_id="doc",
        compiler_run_id="run",
        batch_id="batch-1",
        batch_index=1,
        entries=entries,
        source_chunks=source_chunks,
        mode="faq",
    )

    assert len(candidates) == 1
    assert candidates[0].status == "extracted"
    assert candidates[0].metadata["batch_id"] == "batch-1"
    assert candidates[0].metadata["canonical_question"] == "Что это за сервис?"
    assert candidates[0].source_refs
    assert candidates[0].source_refs[0].source_chunk_id == "doc:0"
