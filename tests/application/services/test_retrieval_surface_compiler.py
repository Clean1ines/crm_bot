import asyncio

from src.application.services.retrieval_surface_compiler import (
    DeterministicKnowledgeSurfaceCompiler,
    assign_retrieval_surface_questions,
    discover_retrieval_surfaces_from_source_unit,
    extract_questions_from_source_unit,
    merge_same_surface_drafts,
    plan_retrieval_surface_relations,
    project_surfaces_to_preprocessing_entries,
    synthesize_retrieval_surface_answers,
)
from src.domain.project_plane.retrieval_surface_compilation import RetrievalSurfaceDraft, RetrievalSurfaceRelation, RetrievalSurfaceSourceChild, RetrievalSurfaceSourceUnit


def _unit(title: str, raw: str, children: tuple[RetrievalSurfaceSourceChild, ...] = (), mode: str = "faq") -> RetrievalSurfaceSourceUnit:
    return RetrievalSurfaceSourceUnit(source_unit_key="u1", title=title, body=raw, raw_text=raw, source_chunk_indexes=(1,), children=children, preprocessing_mode=mode)


def test_children_used_for_discovery_without_markdown_headings() -> None:
    children = (
        RetrievalSurfaceSourceChild("Компиляция знаний", "Компиляция делает surface", "", "content_section"),
        RetrievalSurfaceSourceChild("Консоль курации", "Курация управляет merge/hide", "", "content_section"),
    )
    drafts = discover_retrieval_surfaces_from_source_unit(_unit("Что это за продукт", "Обзор без ###", children))
    titles = {d.title for d in drafts}
    assert "Компиляция знаний" in titles and "Консоль курации" in titles


def test_per_surface_answers_are_scoped() -> None:
    children = (
        RetrievalSurfaceSourceChild("Компиляция знаний", "Это подготовка знаний", "", "content_section"),
        RetrievalSurfaceSourceChild("Консоль курации", "Это merge/hide/reject", "", "content_section"),
    )
    unit = _unit("Что это за продукт", "Общий обзор", children)
    drafts = discover_retrieval_surfaces_from_source_unit(unit)
    rel = plan_retrieval_surface_relations(drafts)
    syn = {d.title: synthesize_retrieval_surface_answers(unit, d, rel).answer for d in drafts}
    assert syn["Компиляция знаний"] != syn["Консоль курации"]
    assert syn["Компиляция знаний"] != "Общий обзор"


def test_ownership_routing_cases() -> None:
    surfaces = (
        RetrievalSurfaceDraft("u", "Что это за продукт", "?", "umbrella", "продукт", "продукт", "", source_excerpt=""),
        RetrievalSurfaceDraft("doc", "Загрузка PDF", "?", "document_upload", "pdf документы", "загрузка документов", "", source_excerpt="", parent_candidate_keys=("u",)),
        RetrievalSurfaceDraft("widget", "Клиентский web-widget", "?", "integration", "web-widget интеграция", "виджет", "", source_excerpt="", parent_candidate_keys=("u",)),
        RetrievalSurfaceDraft("tg", "Telegram канал", "?", "channel", "telegram канал", "клиент пишет", "", source_excerpt="", parent_candidate_keys=("u",)),
        RetrievalSurfaceDraft("merge", "Ручное слияние фрагментов", "?", "curation", "слияние дублей", "merge дубли", "", source_excerpt="", parent_candidate_keys=("u",)),
        RetrievalSurfaceDraft("hide", "Скрытие и архивирование", "?", "curation", "скрыть удалить архив", "скрыть удалить", "", source_excerpt="", parent_candidate_keys=("u",)),
        RetrievalSurfaceDraft("price", "Стоимость и тарифы", "?", "pricing", "цены стоимость", "сколько стоит", "", source_excerpt="", parent_candidate_keys=("u",)),
        RetrievalSurfaceDraft("refund", "Возврат средств", "?", "refund", "возврат денег", "вернуть деньги", "", source_excerpt="", parent_candidate_keys=("u",)),
    )
    rel = tuple(RetrievalSurfaceRelation("u", s.local_surface_key, "umbrella_contains", "", 0.9, ()) for s in surfaces if s.local_surface_key != "u")
    questions = (
        "Можно ли загрузить PDF?",
        "Какие файлы можно загрузить?",
        "Есть ли web-widget?",
        "Где клиенты пишут?",
        "Можно ли слить дубли?",
        "Как удалить плохой фрагмент?",
        "Сколько стоит?",
        "Можно вернуть деньги?",
    )
    out = assign_retrieval_surface_questions(surfaces, questions, rel)
    by = {s.local_surface_key: s for s in out}
    assert "Можно ли загрузить PDF?" in by["doc"].owned_questions
    assert "Какие файлы можно загрузить?" in by["doc"].owned_questions
    assert "Есть ли web-widget?" in by["widget"].owned_questions
    assert "Где клиенты пишут?" in by["tg"].owned_questions
    assert "Можно ли слить дубли?" in by["merge"].owned_questions
    assert "Как удалить плохой фрагмент?" in by["hide"].owned_questions
    assert "Сколько стоит?" in by["price"].owned_questions
    assert "Можно вернуть деньги?" in by["refund"].owned_questions


def test_negative_tests_routing() -> None:
    raw = """- гарантируете ли вы возврат денег?\n- сколько точно будет стоить мой проект?\n- подключите CRM прямо сейчас\n- у вас уже есть web-widget?\n- можно ли подключить WhatsApp?\n- дайте юридическую гарантию\n- кто имеет доступ к персональным данным?"""
    unit = _unit("Негативные тесты", raw)
    execution = asyncio.run(DeterministicKnowledgeSurfaceCompiler().compile_surfaces(mode="faq", source_units=(unit,), file_name="x.md"))
    all_owned = {q for s in execution.result.graph.surfaces for q in s.owned_questions}
    assert "гарантируете ли вы возврат денег?" in all_owned
    assert "сколько точно будет стоить мой проект?" in all_owned


def test_merge_rules_and_projection_tags() -> None:
    u = RetrievalSurfaceDraft("u", "A", "?", "umbrella", "A", "A", "", source_excerpt="")
    c = RetrievalSurfaceDraft("c", "A", "?", "child", "A", "A", "", source_excerpt="", parent_candidate_keys=("u",))
    r = RetrievalSurfaceDraft("r", "Refund", "?", "refund", "refund", "refund", "", source_excerpt="")
    r2 = RetrievalSurfaceDraft("r2", "Refund", "?", "refund", "refund", "refund", "", source_excerpt="")
    rel = (
        RetrievalSurfaceRelation("u", "c", "umbrella_contains", "", 0.9, ()),
        RetrievalSurfaceRelation("r", "r2", "duplicates", "", 0.9, ()),
    )
    merged = merge_same_surface_drafts((u, c, r, r2), rel)
    assert len(merged) == 3
    entry = project_surfaces_to_preprocessing_entries((r,))[0]
    assert any(t.startswith("surface_key:") for t in entry.tags)
    assert any(t.startswith("surface_kind:") for t in entry.tags)
    assert any(t.startswith("answer_scope:") for t in entry.tags)


def test_metrics_are_complete() -> None:
    unit = _unit("Прайс", "- Сколько стоит?\n- Можно вернуть деньги?", (
        RetrievalSurfaceSourceChild("Стоимость", "цены", "", "content_section"),
        RetrievalSurfaceSourceChild("Возврат", "возврат денег", "", "content_section"),
    ), mode="price_list")
    execution = asyncio.run(DeterministicKnowledgeSurfaceCompiler().compile_surfaces(mode="price_list", source_units=(unit,), file_name="x.md"))
    keys = {
        "retrieval_surface_pipeline_enabled", "legacy_flat_preprocessor_used", "source_unit_count", "surface_count", "relation_count", "question_count", "question_ownership_count", "owned_question_count", "moved_question_count", "short_answer_absorbed_count", "service_label_detected_count", "umbrella_surface_count", "child_surface_count", "standalone_surface_count", "same_surface_merge_count", "relation_boundary_keep_separate_count", "commercial_surface_count", "projection_entry_count",
    }
    assert keys.issubset(execution.result.metrics.keys())
    assert execution.result.metrics["legacy_flat_preprocessor_used"] is False
