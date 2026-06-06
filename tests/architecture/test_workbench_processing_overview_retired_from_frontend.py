from pathlib import Path


PAGE = Path("frontend/src/pages/knowledge/KnowledgePage.tsx")
API = Path("frontend/src/shared/api/modules/knowledge.ts")


def test_knowledge_page_does_not_call_retired_processing_overview() -> None:
    source = PAGE.read_text(encoding="utf-8")

    forbidden = (
        "processingOverviewQuery",
        "knowledgeApi.processingOverview",
        'queryKey: ["knowledge-processing-overview", projectId]',
    )

    for marker in forbidden:
        assert marker not in source


def test_frontend_api_does_not_expose_retired_processing_overview() -> None:
    source = API.read_text(encoding="utf-8")

    assert "processingOverview:" not in source
    assert "processing-overview" not in source
