from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_PAGE = ROOT / "frontend/src/pages/knowledge/KnowledgePage.tsx"


def test_processing_polling_is_single_overview_endpoint() -> None:
    source = KNOWLEDGE_PAGE.read_text(encoding="utf-8")

    assert "knowledgeApi.processingOverview(projectId)" in source
    assert (
        source.count("refetchInterval: baseHasProcessingDocuments ? 3000 : false") == 1
    )
    assert "refetchInterval: hasProcessingDocuments ? 3000 : false" not in source
