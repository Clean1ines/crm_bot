from src.application.services.retrieval_surface_compiler import DeterministicKnowledgeSurfaceCompiler
from src.domain.project_plane.retrieval_surface_compilation import RetrievalSurfaceSourceUnit


def test_domain_direction_source_unit_to_graph_and_projection() -> None:
    compiler = DeterministicKnowledgeSurfaceCompiler()
    unit = RetrievalSurfaceSourceUnit(
        source_unit_key="u1",
        document_id="d1",
        source_chunk_indexes=(1,),
        title="Что это за продукт",
        body="Обзор",
        children=(),
        raw_text="## Что это за продукт\nКороткий ответ клиенту: AI база знаний\n### Компиляция знаний\nподготовка",
        section_path=("Что это за продукт",),
        source_refs=("u1",),
        preprocessing_mode="faq",
        metadata={},
    )
    execution = __import__("asyncio").run(
        compiler.compile_surfaces(mode="faq", source_units=(unit,), file_name="a.md")
    )
    assert execution.result.graph.surfaces
    assert execution.result.projected_entries
    assert execution.result.projected_entries[0].title
