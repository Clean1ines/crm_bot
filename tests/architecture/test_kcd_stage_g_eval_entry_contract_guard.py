from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

EVAL_CONTRACT_PATHS = (
    "src/application/rag_eval",
    "src/infrastructure/rag_eval",
    "src/infrastructure/db/repositories/rag_eval_repository.py",
    "src/infrastructure/queue/handlers/rag_eval.py",
    "src/interfaces/http/rag_eval.py",
)

FORBIDDEN_PRIMARY_EVIDENCE_TERMS = (
    "RagEvalChunk",
    "RagEvalChunkSourcePort",
    "expected_chunk_ids",
    "retrieved_chunk_ids",
    "retrieved_chunks",
    "load_document_chunks",
    "wrong_chunk_top1",
    "expected_chunk_found",
)

REQUIRED_ENTRY_TERMS = (
    "RagEvalEvidenceEntry",
    "RagEvalEvidenceEntrySourcePort",
    "expected_entry_ids",
    "retrieved_entry_ids",
    "retrieved_entries",
    "load_document_entries",
    "wrong_entry_top1",
    "expected_entry_found",
)


def _files() -> list[Path]:
    files: list[Path] = []
    for relative in EVAL_CONTRACT_PATHS:
        path = ROOT / relative
        if path.is_file():
            files.append(path)
        else:
            files.extend(
                item for item in path.rglob("*.py") if "__pycache__" not in item.parts
            )
    return sorted(files)


def test_stage_g_eval_primary_evidence_is_entry_first() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in _files())

    for term in FORBIDDEN_PRIMARY_EVIDENCE_TERMS:
        assert term not in combined

    for term in REQUIRED_ENTRY_TERMS:
        assert term in combined


def test_stage_g_keeps_source_chunk_id_as_raw_source_ref_evidence() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in _files())

    assert "source_chunk_id" in combined
    assert "source_entry_id" not in combined


def test_stage_g_has_typed_failure_classification_and_proposed_actions() -> None:
    source = (ROOT / "src/application/rag_eval/failure_classification.py").read_text(
        encoding="utf-8"
    )
    schemas = (ROOT / "src/application/rag_eval/schemas.py").read_text(encoding="utf-8")

    assert "class FailureClassification" in source
    assert "class KnowledgeEditAction" in source
    assert "classification: FailureClassification | None" in schemas
    assert "proposed_actions: list[KnowledgeEditAction]" in schemas


def test_stage_g_migration_promotes_eval_result_classification_and_actions() -> None:
    migration = (
        ROOT / "migrations/061_rag_eval_entry_evidence_and_failure_actions.sql"
    ).read_text(encoding="utf-8")

    assert "expected_entry_ids" in migration
    assert "retrieved_entry_ids" in migration
    assert "expected_entry_found" in migration
    assert "wrong_entry_top1" in migration
    assert "classification JSONB" in migration
    assert "proposed_actions JSONB" in migration
