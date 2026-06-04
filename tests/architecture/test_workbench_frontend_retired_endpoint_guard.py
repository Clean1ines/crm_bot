from pathlib import Path


FRONTEND_SRC = Path("frontend/src")
IGNORED_PARTS = {
    "generated",
    "dist",
}


def _handwritten_frontend_files() -> list[Path]:
    return [
        path
        for path in FRONTEND_SRC.rglob("*")
        if path.is_file()
        and path.suffix in {".ts", ".tsx"}
        and not any(part in IGNORED_PARTS for part in path.parts)
    ]


def test_handwritten_frontend_does_not_call_retired_workbench_endpoints() -> None:
    forbidden = (
        "knowledgeApi.retighten",
        "knowledgeApi.retryFailedBatches",
        "/retighten",
        "/retry-failed-batches",
        "retry_failed_batches",
    )
    offenders: list[str] = []

    for path in _handwritten_frontend_files():
        text = path.read_text()
        for marker in forbidden:
            if marker in text:
                offenders.append(f"{path}:{marker}")

    assert offenders == []


def test_handwritten_frontend_exposes_surface_curation_mutations() -> None:
    api_source = Path("frontend/src/shared/api/modules/knowledge.ts").read_text()
    modal_source = Path(
        "frontend/src/pages/knowledge/components/KnowledgeDocumentCurationModal.tsx"
    ).read_text()

    for marker in (
        "approveSurface",
        "rejectSurface",
        "editSurface",
        "mergeFacts",
        "deleteFact",
        "publishSelectedSurfaces",
    ):
        assert marker in api_source
        assert marker in modal_source
