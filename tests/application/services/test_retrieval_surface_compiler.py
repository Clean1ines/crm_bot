from src.application.services.retrieval_surface_compiler import (
    RetrievalSurfaceDraft,
    RetrievalSurfaceSourceUnit,
    assign_retrieval_surface_questions,
    discover_retrieval_surfaces_from_source_unit,
    merge_same_surface_drafts,
    plan_retrieval_surface_relations,
    project_surfaces_to_preprocessing_entries,
    synthesize_retrieval_surface_answers,
)


def _unit(title: str, raw: str) -> RetrievalSurfaceSourceUnit:
    return RetrievalSurfaceSourceUnit(source_unit_key="u1", title=title, body=raw, raw_text=raw, source_chunk_indexes=(1,))


def test_a_direct_source_unit_search_surface() -> None:
    raw = "## Поисковая поверхность\nПоисковая поверхность — это набор опубликованных знаний.\nКороткий ответ клиенту: Ассистент ищет по подготовленной базе знаний."
    unit = _unit("Поисковая поверхность", raw)
    drafts = discover_retrieval_surfaces_from_source_unit(unit)
    assert any(d.title == "Поисковая поверхность" for d in drafts)
    assert all(d.title != "Короткий ответ клиенту" for d in drafts)
    ready = synthesize_retrieval_surface_answers(unit, drafts[0], ())
    assert "подготовленной базе" in ready.short_answer
    entry = project_surfaces_to_preprocessing_entries((ready,))[0]
    assert entry.title == "Поисковая поверхность"
    assert "набор опубликованных знаний" in entry.answer


def test_b_overview_with_children_and_relations() -> None:
    raw = "## Что это за продукт\nОбзор\n### Компиляция знаний\ntext\n### Консоль курации\ntext\n### Режимы подготовки\ntext"
    drafts = discover_retrieval_surfaces_from_source_unit(_unit("Что это за продукт", raw))
    assert any(d.surface_kind == "umbrella" for d in drafts)
    assert any(d.title == "Компиляция знаний" for d in drafts)
    rel = plan_retrieval_surface_relations(drafts)
    assert any(r.relation_type == "umbrella_contains" for r in rel)


def test_c_eval_questions_assigned() -> None:
    s1 = RetrievalSurfaceDraft("k1", "Что это за продукт", "Что это за продукт?", "umbrella", "", "", "")
    s2 = RetrievalSurfaceDraft("k2", "Компиляция знаний", "Что такое компиляция знаний?", "child", "", "", "")
    out = assign_retrieval_surface_questions((s1, s2), ("что это за сервис?", "что происходит после загрузки документа?", "можно ли слить дубли?"))
    assert any("сервис" in q for q in out[0].owned_questions)


def test_d_negative_tests_not_monolith() -> None:
    raw = "## Негативные тесты\n- гарантируете возврат?\n- сколько точно стоит?\n- есть web-widget?"
    drafts = discover_retrieval_surfaces_from_source_unit(_unit("Ограничения автономности", raw))
    assert not any(d.title == "Негативные тесты" for d in drafts)


def test_e_merge_vs_hide_archive_split() -> None:
    raw = "## Ручное слияние фрагментов\n### Скрытие, отклонение и архивирование\n"
    drafts = discover_retrieval_surfaces_from_source_unit(_unit("Ручное слияние фрагментов", raw))
    assert any("Скрытие" in d.title for d in drafts)


def test_f_web_widget_vs_telegram() -> None:
    raw = "## Telegram assistant\nгде клиенты пишут?\n### Client web-widget\nесть web-widget?"
    drafts = discover_retrieval_surfaces_from_source_unit(_unit("Telegram assistant", raw))
    out = assign_retrieval_surface_questions(drafts, ("где клиенты пишут?", "есть web-widget?"))
    assert any("web-widget" in " ".join(s.owned_questions) for s in out)


def test_g_projection_preserves_fields() -> None:
    draft = RetrievalSurfaceDraft("k", "t", "cq", "specific", "", "", "", answer="a", owned_questions=("q",), source_excerpt="se", source_chunk_indexes=(2,))
    entry = project_surfaces_to_preprocessing_entries((draft,))[0]
    assert entry.title == "t" and entry.questions == ("q",)
    assert entry.source_chunk_indexes == (2,)


def test_h_direction_guard_rejects_preprocessing_entries() -> None:
    try:
        discover_retrieval_surfaces_from_source_unit(object())  # type: ignore[arg-type]
    except TypeError:
        assert True
    else:
        raise AssertionError("expected TypeError")


def test_i_same_surface_merge_only() -> None:
    d1 = RetrievalSurfaceDraft("k1", "A", "cq", "umbrella", "", "", "", answer="1")
    d2 = RetrievalSurfaceDraft("k2", "A", "cq", "child", "", "", "", answer="12")
    merged = merge_same_surface_drafts((d1, d2), ())
    assert len(merged) == 1
