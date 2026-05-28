from pathlib import Path


def test_cancel_document_processing_cancels_surface_runs_and_stages() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")

    assert "UPDATE knowledge_surface_compiler_runs" in source
    assert "UPDATE knowledge_surface_compiler_stages" in source
    assert "status = 'cancelled'" in source
    assert "error_type = 'processing_cancelled'" in source
