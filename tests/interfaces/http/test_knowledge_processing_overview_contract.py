from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HTTP_KNOWLEDGE = ROOT / "src/interfaces/http/knowledge.py"
KNOWLEDGE_TS = ROOT / "frontend/src/shared/api/modules/knowledge.ts"
KNOWLEDGE_PAGE = ROOT / "frontend/src/pages/knowledge/KnowledgePage.tsx"


def test_processing_overview_endpoint_contract_exists() -> None:
    source = HTTP_KNOWLEDGE.read_text(encoding="utf-8")

    assert '@router.get("/processing-overview")' in source
    assert "knowledge_processing_overview" in source
    assert "build_knowledge_processing_report" in source
    assert '"processing_reports": processing_reports' in source
    assert '"partial_surface_count": partial_surface_count' in source
    assert '"source_unit_summary": source_unit_summary' in source
    assert '"groq_route_summary": groq_route_summary' in source
    assert '"economy_mode_summary": economy_mode_summary' in source


def test_frontend_api_exposes_processing_overview() -> None:
    source = KNOWLEDGE_TS.read_text(encoding="utf-8")

    assert "KnowledgeProcessingOverviewResponse" in source
    assert "processingOverview:" in source
    assert "/knowledge/processing-overview" in source


def test_processing_screen_uses_overview_for_polling_and_lazies_heavy_queries() -> None:
    source = KNOWLEDGE_PAGE.read_text(encoding="utf-8")

    assert "knowledge-processing-overview" in source
    assert "knowledgeApi.processingOverview(projectId)" in source
    assert "processingOverviewQuery.data?.processing_reports" in source
    assert "baseHasProcessingDocuments ? 3000 : false" in source
    assert "hasProcessingDocuments ? [] : documents.map" in source
    assert "draftsDocumentId" in source
    assert "sourceUnitsDocumentId" in source
    assert "enabled: !!projectId && !hasProcessingDocuments" in source
    assert "refetchInterval: hasProcessingDocuments ? 3000 : false" not in source
