from __future__ import annotations

from src.application.services.knowledge_ingestion_service import (
    _apply_answer_resolution_decisions,
    _compiler_source_chunks_for_preprocessing,
    _raw_answer_candidates_from_preprocessing_entries,
    _reassign_umbrella_questions,
    _surface_kind_for_entry,
    _build_local_surface_graph_from_entries,
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


def test_answer_resolution_uses_answer_only_resolution_not_concatenation() -> None:
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

    merged, source_excerpts = _apply_answer_resolution_decisions(
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


def test_answer_resolution_merges_russian_product_duplicates_with_short_answers() -> None:
    entries = (
        KnowledgePreprocessingEntry(
            title="Что это за продукт",
            canonical_question="Что это за продукт?",
            answer="CRM бот для продаж.",
            source_excerpt="CRM бот для продаж и поддержки.",
            questions=("что это за продукт",),
            synonyms=("о продукте",),
        ),
        KnowledgePreprocessingEntry(
            title="О продукте",
            canonical_question="О продукте",
            answer="Продукт автоматизирует продажи.",
            source_excerpt="Продукт автоматизирует продажи и заявки.",
            questions=("о продукте", "как продукт помогает"),
            synonyms=("что это за продукт",),
        ),
    )
    decision = KnowledgeAnswerResolutionDecision(
        case_id="product-duplicates-ru",
        action="merge",
        candidate_ids=("entry-0", "entry-1"),
        canonical_answer="Это CRM-бот: он автоматизирует продажи и помогает поддержке.",
    )

    merged, _source_excerpts = _apply_answer_resolution_decisions(
        entries=entries,
        decisions=(decision,),
    )

    assert len(merged) == 1
    assert merged[0].answer == "Это CRM-бот: он автоматизирует продажи и помогает поддержке."
    assert "как продукт помогает" in merged[0].questions


def test_short_answer_service_label_is_not_standalone_and_absorbed() -> None:
    umbrella = KnowledgePreprocessingEntry(
        title="Поисковая поверхность",
        canonical_question="Что такое поисковая поверхность?",
        answer="Поисковая поверхность — это набор опубликованных знаний.",
        source_excerpt="Короткий ответ клиенту: Ассистент ищет по подготовленной базе знаний.",
        questions=("Что такое поисковая поверхность?",),
    )
    short = KnowledgePreprocessingEntry(
        title="Короткий ответ клиенту",
        canonical_question="Короткий ответ клиенту",
        answer="Ассистент ищет по подготовленной базе знаний.",
        source_excerpt="Ассистент ищет по подготовленной базе знаний.",
        questions=("По чему ассистент ищет ответ?",),
    )
    decision = KnowledgeAnswerResolutionDecision(case_id="s1", action="merge", candidate_ids=("entry-0", "entry-1"), canonical_answer="Поисковая поверхность — опубликованная база знаний; ассистент ищет именно в ней.")
    merged, _ = _apply_answer_resolution_decisions(entries=(umbrella, short), decisions=(decision,))
    assert len(merged) == 1
    assert merged[0].title == "Поисковая поверхность"


def test_surface_kind_and_question_ownership_reassignment() -> None:
    umbrella = KnowledgePreprocessingEntry(
        title="Что это за продукт",
        canonical_question="Что это за продукт?",
        answer="Обзор платформы.",
        source_excerpt="...",
        questions=("Что это за сервис?", "Можно ли загрузить PDF?"),
    )
    child = KnowledgePreprocessingEntry(
        title="Компиляция знаний",
        canonical_question="Что такое компиляция знаний?",
        answer="Процесс подготовки знаний.",
        source_excerpt="...",
        questions=("Что такое компиляция знаний?",),
    )
    assert _surface_kind_for_entry(umbrella) == "umbrella"
    assert _surface_kind_for_entry(child) == "child"
    reassigned = _reassign_umbrella_questions((umbrella, child))
    assert "Можно ли загрузить PDF?" not in reassigned[0].questions
    assert "Можно ли загрузить PDF?" in reassigned[1].questions


def test_umbrella_child_relation_is_not_duplicate_merge() -> None:
    entries = (
        KnowledgePreprocessingEntry(title="Что это за продукт", canonical_question="Что это за продукт?", answer="Обзор", source_excerpt="...", questions=("Что это за сервис?",)),
        KnowledgePreprocessingEntry(title="Клиентский web-widget", canonical_question="Есть ли web-widget?", answer="Да", source_excerpt="...", questions=("Есть ли web-widget?",)),
    )
    decision = KnowledgeAnswerResolutionDecision(case_id="s2", action="merge", candidate_ids=("entry-0", "entry-1"), canonical_answer="test")
    merged, _ = _apply_answer_resolution_decisions(entries=entries, decisions=(decision,))
    assert len(merged) == 2


def test_web_widget_does_not_own_telegram_question_after_reassign() -> None:
    umbrella = KnowledgePreprocessingEntry(title="О продукте", canonical_question="О продукте", answer="...", source_excerpt="...", questions=("Где клиенты пишут?",))
    widget = KnowledgePreprocessingEntry(title="Клиентский web-widget", canonical_question="Есть ли web-widget?", answer="...", source_excerpt="...", questions=("Есть ли web-widget?",))
    reassigned = _reassign_umbrella_questions((umbrella, widget))
    assert "Где клиенты пишут?" in reassigned[0].questions
    assert "Где клиенты пишут?" not in reassigned[1].questions


def test_acceptance_a_search_surface_short_answer_absorbed() -> None:
    entries=(
        KnowledgePreprocessingEntry(title="Поисковая поверхность", canonical_question="Что такое поисковая поверхность?", answer="Поисковая поверхность — набор опубликованных знаний.", source_excerpt="...", questions=("Что такое поисковая поверхность?",)),
        KnowledgePreprocessingEntry(title="Короткий ответ клиенту", canonical_question="Короткий ответ", answer="Ассистент ищет по подготовленной базе знаний.", source_excerpt="...", questions=("По чему ассистент ищет ответ?",)),
    )
    _graph, projected, metrics = _build_local_surface_graph_from_entries(entries)
    assert len(projected)==1
    assert projected[0].title=="Поисковая поверхность"
    assert "подготовленной базе" in projected[0].answer
    assert metrics["short_answer_absorbed_count"] >= 1


def test_acceptance_b_umbrella_keeps_broad_not_child_specific() -> None:
    entries=(
        KnowledgePreprocessingEntry(title="Что это за продукт", canonical_question="Что это за продукт?", answer="Обзор.", source_excerpt="...", questions=("Что это за сервис?","Можно ли загрузить PDF?")),
        KnowledgePreprocessingEntry(title="Компиляция знаний", canonical_question="Что такое компиляция знаний?", answer="...", source_excerpt="...", questions=("Что такое компиляция знаний?",)),
    )
    _graph, projected, _m = _build_local_surface_graph_from_entries(entries)
    assert "Что это за сервис?" in projected[0].questions
    assert "Можно ли загрузить PDF?" not in projected[0].questions
    assert "Можно ли загрузить PDF?" in projected[1].questions


def test_acceptance_c_negative_tests_split_to_meaningful_surfaces() -> None:
    entries=(
        KnowledgePreprocessingEntry(title="Негативные тесты", canonical_question="Негативные тесты", answer="Ограничения автономности и эскалация к менеджеру; рискованные вопросы.", source_excerpt="...", questions=("Когда передаёт менеджеру?", "Какие рискованные вопросы?")),
        KnowledgePreprocessingEntry(title="Ограничения автономности ассистента", canonical_question="Какие ограничения?", answer="...", source_excerpt="...", questions=("Какие ограничения автономности?",)),
        KnowledgePreprocessingEntry(title="Когда ассистент передаёт вопрос менеджеру", canonical_question="Когда эскалация?", answer="...", source_excerpt="...", questions=("Когда передаёт менеджеру?",)),
    )
    graph, projected, _ = _build_local_surface_graph_from_entries(entries)
    assert any(s.title=="Ограничения автономности ассистента" for s in graph.surfaces)
    assert any(s.title.startswith("Когда ассистент") for s in graph.surfaces)
    assert len(projected) >= 2


def test_acceptance_d_manual_merge_vs_hide_archive_ownership() -> None:
    entries=(
        KnowledgePreprocessingEntry(title="Ручное слияние фрагментов", canonical_question="Как слить дубли?", answer="...", source_excerpt="...", questions=("Как слить дубли?","Как скрыть плохой фрагмент?")),
        KnowledgePreprocessingEntry(title="Скрытие, отклонение и архивирование фрагментов", canonical_question="Как скрыть/архивировать?", answer="...", source_excerpt="...", questions=("Как скрыть фрагмент?",)),
    )
    _g, projected, _ = _build_local_surface_graph_from_entries(entries)
    assert "Как слить дубли?" in projected[0].questions
    assert "Как скрыть плохой фрагмент?" in projected[1].questions


def test_acceptance_e_widget_vs_telegram_ownership() -> None:
    entries=(
        KnowledgePreprocessingEntry(title="Клиентский web-widget", canonical_question="Есть ли web-widget?", answer="...", source_excerpt="...", questions=("Есть ли web-widget?","Где клиенты пишут?")),
        KnowledgePreprocessingEntry(title="Telegram-ассистент", canonical_question="Где клиенты пишут в Telegram?", answer="...", source_excerpt="...", questions=("Где клиенты пишут?",)),
    )
    _g, projected, _ = _build_local_surface_graph_from_entries(entries)
    assert "Где клиенты пишут?" in projected[1].questions


def test_acceptance_f_same_surface_duplicates_merge() -> None:
    entries=(
        KnowledgePreprocessingEntry(title="Возврат средств", canonical_question="Есть ли возврат?", answer="Возврат зависит от этапа работы.", source_excerpt="Возврат зависит от этапа работы.", questions=("Есть ли возврат?",)),
        KnowledgePreprocessingEntry(title="Возврат оплаты", canonical_question="Можно вернуть оплату?", answer="Вернуть оплату можно по правилам договора.", source_excerpt="Вернуть оплату можно по правилам договора.", questions=("Можно вернуть оплату?",)),
    )
    decision=KnowledgeAnswerResolutionDecision(case_id='x', action='merge', candidate_ids=('entry-0','entry-1'), canonical_answer='Возврат оплаты зависит от этапа и условий договора.')
    merged,_=_apply_answer_resolution_decisions(entries=entries, decisions=(decision,))
    assert len(merged)==1


def test_acceptance_g_umbrella_child_relation_boundary() -> None:
    entries=(
        KnowledgePreprocessingEntry(title="Что это за продукт", canonical_question="?", answer="...", source_excerpt="...", questions=("Что это за сервис?",)),
        KnowledgePreprocessingEntry(title="Консоль курации знаний", canonical_question="?", answer="...", source_excerpt="...", questions=("Что такое консоль курации?",)),
    )
    graph,_,metrics=_build_local_surface_graph_from_entries(entries)
    assert any(r.relation_type=='umbrella_contains' for r in graph.relations)
    assert metrics['relation_boundary_keep_separate_count'] >= 1


def test_acceptance_h_repair_first_non_fatal_remains() -> None:
    entry = KnowledgePreprocessingEntry(title="# Заголовок", answer="Ответ", source_excerpt="Ответ", questions=("？",), canonical_question="")
    from src.application.services.knowledge_ingestion_service import _repair_generated_entry
    repaired,warnings=_repair_generated_entry(entry, source_excerpt=entry.source_excerpt)
    assert repaired.answer
    assert isinstance(warnings, tuple)
