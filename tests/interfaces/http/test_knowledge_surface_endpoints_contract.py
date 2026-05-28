from pathlib import Path


def test_knowledge_http_exposes_surface_endpoints() -> None:
    source = Path("src/interfaces/http/knowledge_surface.py").read_text(
        encoding="utf-8"
    )
    assert '@router.get("/{document_id}/surface-compilation")' in source
    assert '@router.get("/{document_id}/surfaces")' in source
    assert '@router.get("/{document_id}/surface-relations")' in source
    assert '@router.get("/{document_id}/surface-ownership")' in source
    assert '@router.get("/{document_id}/surface-merge-decisions")' in source
    assert '@router.post("/{document_id}/surfaces/{surface_id}/publish")' in source
