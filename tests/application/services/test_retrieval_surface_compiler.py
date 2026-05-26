from src.application.services.retrieval_surface_compiler import (
    DeterministicKnowledgeSurfaceCompiler,
    assign_retrieval_surface_questions,
    discover_retrieval_surfaces_from_source_unit,
    merge_same_surface_drafts,
    plan_retrieval_surface_relations,
    project_surfaces_to_preprocessing_entries,
    synthesize_retrieval_surface_answers,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceDraft,
    RetrievalSurfaceRelation,
    RetrievalSurfaceSourceChild,
    RetrievalSurfaceSourceUnit,
)


def _unit(title: str, raw: str, children: tuple[RetrievalSurfaceSourceChild, ...] = ()) -> RetrievalSurfaceSourceUnit:
    return RetrievalSurfaceSourceUnit(source_unit_key="u1", title=title, body=raw, raw_text=raw, source_chunk_indexes=(1,), children=children)


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


def test_relation_scope_aware_ownership() -> None:
    u = RetrievalSurfaceDraft("u","Что это за продукт","?","umbrella","продукт","продукт","",source_excerpt="")
    c = RetrievalSurfaceDraft("c","Компиляция знаний","?","specific","компиляция знаний","компиляция","продукт",source_excerpt="",parent_candidate_keys=("u",))
    rel = (RetrievalSurfaceRelation("u","c","umbrella_contains","",0.9,()),)
    out = assign_retrieval_surface_questions((u,c),("что это за продукт?","что такое компиляция знаний?"),rel)
    by = {x.local_surface_key: x for x in out}
    assert "что это за продукт?" in by["u"].owned_questions
    assert "что такое компиляция знаний?" in by["c"].owned_questions


def test_merge_respects_umbrella_relation_boundary() -> None:
    u = RetrievalSurfaceDraft("u","A","?","umbrella","A","A","",source_excerpt="")
    c = RetrievalSurfaceDraft("c","A","?","child","A","A","",source_excerpt="",parent_candidate_keys=("u",))
    rel = (RetrievalSurfaceRelation("u","c","umbrella_contains","",0.9,()),)
    merged = merge_same_surface_drafts((u,c),rel)
    assert len(merged) == 2


def test_short_answer_not_standalone_and_projected_parent_title() -> None:
    unit = _unit("Поисковая поверхность","Короткий ответ клиенту: искать по базе")
    drafts = discover_retrieval_surfaces_from_source_unit(unit)
    syn = synthesize_retrieval_surface_answers(unit,drafts[0],())
    assert syn.title != "Короткий ответ клиенту"
    entry = project_surfaces_to_preprocessing_entries((syn,))[0]
    assert entry.title == "Поисковая поверхность"


def test_compiler_metrics_are_rich() -> None:
    execution = __import__("asyncio").run(DeterministicKnowledgeSurfaceCompiler().compile_surfaces(mode="faq", source_units=(_unit("T","- где?"),), file_name="x.md"))
    assert {"source_unit_count","surface_count","relation_count","question_count","owned_question_count","projected_entry_count"}.issubset(execution.result.graph.metrics.keys())
