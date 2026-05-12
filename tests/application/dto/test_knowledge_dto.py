from src.application.dto.knowledge_dto import (
    KnowledgePreviewResultDto,
    KnowledgeUploadResultDto,
)
from src.domain.project_plane.knowledge_views import (
    KnowledgeSearchResultView,
    SourceRefView,
)


def test_knowledge_upload_result_dto_serializes_stably():
    dto = KnowledgeUploadResultDto.create(message="Uploaded 2 chunks", chunks=2)

    assert dto.to_dict() == {
        "message": "Uploaded 2 chunks",
        "chunks": 2,
    }


def test_preview_result_serializes_source_refs() -> None:
    view = KnowledgeSearchResultView(
        id="entry-1",
        content="Answer text",
        score=0.9,
        method="hybrid",
        document_id="doc-1",
        source="kb.md",
        document_status="processed",
        entry_kind="answer",
        title="Answer",
        source_excerpt="Exact evidence.",
        source_refs=(SourceRefView(source_index=2, quote="Exact evidence."),),
    )

    dto = KnowledgePreviewResultDto.from_search_result(view)
    payload = dto.to_dict()

    assert payload["source_refs"] == [{"quote": "Exact evidence.", "source_index": 2}]
