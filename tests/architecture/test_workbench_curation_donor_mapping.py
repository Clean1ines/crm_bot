from __future__ import annotations

from pathlib import Path


OLD_SURFACE_CURATION_SERVICE = Path(
    "src/application/services/faq_workbench_surface_curation_service.py"
)
CURRENT_MODAL = Path(
    "frontend/src/pages/knowledge/components/KnowledgeDocumentCurationModal.tsx"
)
CURRENT_EVIDENCE_TRACE = Path(
    "src/interfaces/composition/faq_workbench_evidence_trace.py"
)


def test_workbench_curation_does_not_carry_old_canonical_entry_lifecycle() -> None:
    assert not OLD_SURFACE_CURATION_SERVICE.exists()

    modal = CURRENT_MODAL.read_text(encoding="utf-8")
    assert "evidenceTrace" in modal
    assert "knowledgeSurfaceApi" not in modal
    assert "RetrievalSurface" not in modal
    assert "surface cards" not in modal


def test_workbench_curation_uses_evidence_trace_instead_of_old_surface_donors() -> None:
    assert CURRENT_EVIDENCE_TRACE.exists()
    source = CURRENT_EVIDENCE_TRACE.read_text(encoding="utf-8")

    assert "EvidenceTrace" in source or "evidence_trace" in source
    assert "faq_workbench_surface_curation_service" not in source
