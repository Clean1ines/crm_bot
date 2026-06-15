from __future__ import annotations

from pathlib import Path


FORBIDDEN = (
    "src.application." + "workbench_observability",
    "src.application." + "workbench_commands",
    "src.application." + "workbench",
    "src.infrastructure.db." + "knowledge_workbench_repository",
    "src.infrastructure.db." + "workbench_runtime_retrieval_repository",
    "src.infrastructure." + "rag_eval",
    "publish" + "SelectedSurfaces",
    "approve" + "Surface",
    "reject" + "Surface",
    "edit" + "Surface",
    "merge" + "Facts",
    "delete" + "Fact",
    "evidence" + "Trace",
    "Knowledge" + "DocumentCurationModal",
)


def test_live_code_does_not_reference_legacy_workbench_edges() -> None:
    roots = (
        Path("src"),
        Path("frontend/src"),
    )

    offenders: list[str] = []
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            source = path.read_text(encoding="utf-8")
            for token in FORBIDDEN:
                if token in source:
                    offenders.append(f"{path.as_posix()}: {token}")

    assert offenders == []


def test_deleted_legacy_composition_files_stay_deleted() -> None:
    deleted = (
        Path("src/interfaces/composition/faq_workbench_documents.py"),
        Path("src/interfaces/composition/faq_workbench_document_cards.py"),
        Path("src/interfaces/composition/faq_workbench_clear.py"),
        Path("src/interfaces/composition/faq_workbench_delete.py"),
        Path("src/interfaces/composition/faq_workbench_cancel.py"),
        Path("src/interfaces/composition/faq_workbench_progress.py"),
        Path("src/interfaces/composition/faq_workbench_import_quality.py"),
        Path("src/interfaces/composition/faq_workbench_evidence_trace.py"),
        Path("src/interfaces/composition/faq_workbench_surface_curation.py"),
        Path(
            "frontend/src/pages/knowledge/components/"
            + "Knowledge"
            + "DocumentCurationModal.tsx"
        ),
    )

    assert [path.as_posix() for path in deleted if path.exists()] == []
