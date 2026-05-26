import asyncio

from src.application.services.retrieval_surface_compiler import (
    DeterministicKnowledgeSurfaceCompiler,
    assign_retrieval_surface_questions,
    discover_retrieval_surfaces_from_source_unit,
    merge_same_surface_drafts,
    plan_retrieval_surface_relations,
    project_surfaces_to_preprocessing_entries,
    synthesize_retrieval_surface_answers,
)
from src.domain.project_plane.retrieval_surface_compilation import RetrievalSurfaceDraft, RetrievalSurfaceRelation, RetrievalSurfaceSourceChild, RetrievalSurfaceSourceUnit, SurfaceQuestionReassignment


def _unit(title: str, raw: str, children: tuple[RetrievalSurfaceSourceChild, ...] = (), mode: str = "faq") -> RetrievalSurfaceSourceUnit:
    return RetrievalSurfaceSourceUnit(source_unit_key="u1", title=title, body=raw, raw_text=raw, source_chunk_indexes=(1,), children=children, preprocessing_mode=mode)


def _owner_by_question(surfaces, question: str):
    for s in surfaces:
        if question in s.owned_questions:
            return s
    return None


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


def test_negative_tests_routing_by_owner_kind() -> None:
    raw = """- гарантируете ли вы возврат денег?\n- сколько точно будет стоить мой проект?\n- подключите CRM прямо сейчас\n- у вас уже есть web-widget?\n- можно ли подключить WhatsApp?\n- дайте юридическую гарантию\n- кто имеет доступ к персональным данным?\n- можно ли оплатить нестандартным способом?"""
    children = (
        RetrievalSurfaceSourceChild("Интеграции", "CRM и web-widget и WhatsApp", "", "content_section"),
        RetrievalSurfaceSourceChild("Возврат средств", "Возврат и деньги", "", "content_section"),
        RetrievalSurfaceSourceChild("Стоимость", "Цена и тарифы", "", "content_section"),
        RetrievalSurfaceSourceChild("Оплата", "Оплата и нестандартные способы", "", "content_section"),
    )
    unit = _unit("Негативные тесты", raw, children)
    execution = asyncio.run(DeterministicKnowledgeSurfaceCompiler().compile_surfaces(mode="faq", source_units=(unit,), file_name="x.md"))
    surfaces = execution.result.graph.surfaces

    refund_owner = _owner_by_question(surfaces, "гарантируете ли вы возврат денег?")
    assert refund_owner is not None and refund_owner.surface_kind in {"refund", "handoff", "service_limits"}

    price_owner = _owner_by_question(surfaces, "сколько точно будет стоить мой проект?")
    assert price_owner is not None and price_owner.surface_kind in {"pricing", "handoff", "service_limits"}

    crm_owner = _owner_by_question(surfaces, "подключите CRM прямо сейчас")
    wa_owner = _owner_by_question(surfaces, "можно ли подключить WhatsApp?")
    assert crm_owner is not None and crm_owner.surface_kind in {"integration", "service_limits", "handoff"}
    assert wa_owner is not None and wa_owner.surface_kind in {"integration", "service_limits", "handoff"}

    widget_owner = _owner_by_question(surfaces, "у вас уже есть web-widget?")
    assert widget_owner is not None and widget_owner.surface_kind in {"integration", "service_limits", "handoff"}

    legal_owner = _owner_by_question(surfaces, "дайте юридическую гарантию")
    privacy_owner = _owner_by_question(surfaces, "кто имеет доступ к персональным данным?")
    pay_owner = _owner_by_question(surfaces, "можно ли оплатить нестандартным способом?")
    assert legal_owner is not None and legal_owner.surface_kind in {"service_limits", "handoff"}
    assert privacy_owner is not None and privacy_owner.surface_kind in {"service_limits", "handoff"}
    assert pay_owner is not None and pay_owner.surface_kind in {"payment", "handoff", "service_limits"}


def test_price_list_commercial_behavior() -> None:
    children = (
        RetrievalSurfaceSourceChild("Стоимость", "Стоимость зависит от объёма базы знаний, количества документов, сложности курации, числа ботов и менеджеров.", "", "content_section"),
        RetrievalSurfaceSourceChild("Оплата", "Условия оплаты уточняет менеджер. Нестандартный способ оплаты требует согласования.", "", "content_section"),
        RetrievalSurfaceSourceChild("Возврат средств", "Условия возврата зависят от ситуации и этапа работы. Лучше передать вопрос менеджеру.", "", "content_section"),
        RetrievalSurfaceSourceChild("Коммерческие ограничения", "Ассистент не должен обещать точную стоимость, гарантии возврата или юридические условия.", "", "content_section"),
    )
    raw = """- Сколько стоит?\n- Можно оплатить нестандартным способом?\n- Можно вернуть деньги?\n- Вы гарантируете возврат?\n- Сколько точно будет стоить мой проект?"""
    unit = _unit("Коммерческие условия", raw, children, mode="price_list")
    execution = asyncio.run(DeterministicKnowledgeSurfaceCompiler().compile_surfaces(mode="price_list", source_units=(unit,), file_name="price.md"))
    surfaces = execution.result.graph.surfaces
    kinds = {s.surface_kind for s in surfaces}
    assert "pricing" in kinds and "payment" in kinds and "refund" in kinds
    assert any(k in kinds for k in {"service_limits", "handoff"})

    q1 = _owner_by_question(surfaces, "Сколько стоит?")
    q2 = _owner_by_question(surfaces, "Можно оплатить нестандартным способом?")
    q3 = _owner_by_question(surfaces, "Можно вернуть деньги?")
    q4 = _owner_by_question(surfaces, "Вы гарантируете возврат?")
    q5 = _owner_by_question(surfaces, "Сколько точно будет стоить мой проект?")
    assert q1 is not None and q1.surface_kind == "pricing"
    assert q2 is not None and q2.surface_kind in {"payment", "handoff", "service_limits"}
    assert q3 is not None and q3.surface_kind in {"refund", "handoff", "service_limits"}
    assert q4 is not None and q4.surface_kind in {"refund", "service_limits", "handoff"}
    assert q5 is not None and q5.surface_kind in {"pricing", "service_limits", "handoff"}
    umbrella = next(s for s in surfaces if s.surface_kind == "umbrella")
    for q in ("Сколько стоит?", "Можно вернуть деньги?", "Сколько точно будет стоить мой проект?"):
        assert q not in umbrella.owned_questions


def test_merge_rules_projection_tags_and_reassignment_preserved() -> None:
    u = RetrievalSurfaceDraft("u", "A", "?", "umbrella", "A", "A", "", source_excerpt="")
    c = RetrievalSurfaceDraft("c", "A", "?", "child", "A", "A", "", source_excerpt="", parent_candidate_keys=("u",))
    r = RetrievalSurfaceDraft("r", "Refund", "?", "refund", "refund", "refund", "", source_excerpt="", rejected_or_reassigned_questions=(
        # should survive merge
        SurfaceQuestionReassignment('q','r','reason'),
    ))
    r2 = RetrievalSurfaceDraft("r2", "Refund", "?", "refund", "refund", "refund", "", source_excerpt="")
    rel = (
        RetrievalSurfaceRelation("u", "c", "umbrella_contains", "", 0.9, ()),
        RetrievalSurfaceRelation("r", "r2", "duplicates", "", 0.9, ()),
    )
    merged = merge_same_surface_drafts((u, c, r, r2), rel)
    assert len(merged) == 3
    refund = next(x for x in merged if x.surface_kind == "refund")
    assert len(refund.rejected_or_reassigned_questions) == 1
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
