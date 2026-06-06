from __future__ import annotations

from pathlib import Path


MODAL = Path(
    "frontend/src/pages/knowledge/components/KnowledgeDocumentCurationModal.tsx"
)
API = Path("frontend/src/shared/api/modules/knowledge.ts")


def test_curation_modal_reads_workbench_evidence_trace_not_old_surface_curation() -> (
    None
):
    source = MODAL.read_text(encoding="utf-8")

    assert "knowledgeApi.evidenceTrace" in source
    assert "knowledgeCurationApi" not in source
    assert "knowledgeSurfaceApi" not in source
    assert "RetrievalSurface" not in source
    assert "publishSurfaceMutation" not in source
    assert "showSurfaceCuration" not in source
    assert "surface cards" not in source


def test_curation_modal_renders_prompt_a_trace_vocabulary() -> None:
    source = MODAL.read_text(encoding="utf-8")

    assert "Prompt A: обработанные секции и claims" in source
    assert "Prompt A processed" in source
    assert "Prompt A pending/empty" in source
    assert "Извлечённые claims" in source
    assert "Детали claim" in source
    assert "Evidence" in source
    assert "Triples" in source
    assert "Local relations" in source
    assert "Coverage" in source
    assert "Пробелы / warnings" in source
    assert "section.findings" in source
    assert "traceQuery.data?.source_units" in source
    assert "traceQuery.data?.findings" in source
    assert "traceQuery.data?.canonical_facts" in source

    prompt_a_block = source.split("activeTab === 'prompt_a'", 1)[1].split(
        "activeTab === 'facts'",
        1,
    )[0]
    assert "Canonical facts из этой секции" not in prompt_a_block
    assert "Surfaces из этой секции" not in prompt_a_block


def test_knowledge_api_exposes_workbench_evidence_trace_contract() -> None:
    source = API.read_text(encoding="utf-8")

    assert "WorkbenchEvidenceTraceResponse" in source
    assert "WorkbenchEvidenceTraceFinding" in source
    assert "WorkbenchEvidenceTraceCanonicalFact" in source
    assert "WorkbenchEvidenceTraceSourceUnit" in source
    assert "evidenceTrace: (projectId: string, documentId: string)" in source
    assert "/evidence-trace" in source


def test_frontend_surface_api_module_is_deleted_after_evidence_trace_cutover() -> None:
    assert not Path("frontend/src/shared/api/modules/knowledgeSurface.ts").exists()
    assert not Path(
        "frontend/src/pages/knowledge/components/SurfaceCompilationSummary.tsx"
    ).exists()
    assert not Path(
        "frontend/src/pages/knowledge/components/surfacePipelineContract.ts"
    ).exists()
