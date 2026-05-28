from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "src/application/services/knowledge_surface_ingestion_service.py"


def test_faq_surface_ingestion_wires_cooperative_cancel_contract() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "KnowledgeSurfaceCancelAwareCompilerPort" in source
    assert "KnowledgeSurfaceIngestionCancelled" in source
    assert "async def ensure_not_cancelled() -> None" in source
    assert "is_document_processing_cancelled" in source
    assert "compiler.set_cancel_check(ensure_not_cancelled)" in source
    assert 'status="cancelled"' in source
    assert "await ensure_not_cancelled()" in source
