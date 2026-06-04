from __future__ import annotations

from pathlib import Path


OLD_SURFACE_CURATION_SERVICE = Path(
    "src/application/services/faq_workbench_surface_curation_service.py"
)
OLD_SURFACE_MATERIALIZATION_SERVICE = Path(
    "src/application/services/faq_workbench_surface_materialization_service.py"
)
OLD_SURFACE_SUMMARY = Path(
    "frontend/src/pages/knowledge/components/SurfaceCompilationSummary.tsx"
)
OLD_SURFACE_CONTRACT = Path(
    "frontend/src/pages/knowledge/components/surfacePipelineContract.ts"
)
OLD_SURFACE_API = Path("frontend/src/shared/api/modules/knowledgeSurface.ts")

CURRENT_CURATION_MODAL = Path(
    "frontend/src/pages/knowledge/components/KnowledgeDocumentCurationModal.tsx"
)
CURRENT_EVIDENCE_TRACE_COMPOSITION = Path(
    "src/interfaces/composition/faq_workbench_evidence_trace.py"
)
CURRENT_PUBLISH_READY_COMPOSITION = Path(
    "src/interfaces/composition/faq_workbench_publish_ready.py"
)


def test_old_surface_backend_and_frontend_chain_is_deleted() -> None:
    deleted = (
        OLD_SURFACE_CURATION_SERVICE,
        OLD_SURFACE_MATERIALIZATION_SERVICE,
        OLD_SURFACE_SUMMARY,
        OLD_SURFACE_CONTRACT,
        OLD_SURFACE_API,
    )

    for path in deleted:
        assert not path.exists(), f"{path} should stay deleted"


def test_workbench_trace_and_publish_are_the_supported_paths() -> None:
    assert CURRENT_CURATION_MODAL.exists()
    assert CURRENT_EVIDENCE_TRACE_COMPOSITION.exists()
    assert CURRENT_PUBLISH_READY_COMPOSITION.exists()

    modal = CURRENT_CURATION_MODAL.read_text(encoding="utf-8")
    assert "evidenceTrace" in modal
    assert "knowledgeSurfaceApi" not in modal
    assert "RetrievalSurface" not in modal


def test_old_surface_chain_is_not_imported_by_current_knowledge_ui_or_backend() -> None:
    offenders: list[str] = []
    forbidden = (
        "faq_workbench_surface_curation_service",
        "faq_workbench_surface_materialization_service",
        "knowledgeSurfaceApi",
        "SurfaceCompilationSummary",
        "surfacePipelineContract",
        "@shared/api/modules/knowledgeSurface",
    )

    roots = (
        Path("src/application"),
        Path("src/interfaces"),
        Path("frontend/src/pages/knowledge"),
        Path("frontend/src/shared/api/modules"),
    )

    this_file = Path(__file__).resolve()
    for root in roots:
        if not root.exists():
            continue
        for candidate in root.rglob("*"):
            if not candidate.is_file() or candidate.suffix not in {
                ".py",
                ".ts",
                ".tsx",
            }:
                continue
            if candidate.resolve() == this_file:
                continue
            source = candidate.read_text(encoding="utf-8", errors="ignore")
            for marker in forbidden:
                if marker in source:
                    offenders.append(f"{candidate}: {marker}")

    assert offenders == []
