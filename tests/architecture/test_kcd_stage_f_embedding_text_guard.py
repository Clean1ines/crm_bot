from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_stage_f_has_single_production_embedding_text_builder() -> None:
    repository = _read("src/infrastructure/db/repositories/knowledge_repository.py")
    entry_persistence = _read(
        "src/infrastructure/db/repositories/knowledge_entry_persistence.py"
    )
    embedding_contract = _read("src/domain/project_plane/embedding_text.py")

    assert "entry_embedding_text(" in repository
    assert "build_canonical_entry_embedding_text(" not in repository

    assert "entry_embedding_text(" in entry_persistence
    assert "build_canonical_entry_embedding_text(" in entry_persistence
    assert "CANONICAL_EMBEDDING_TEXT_VERSION" in embedding_contract


def test_stage_f_removes_legacy_chunk_embedding_builder_from_production_path() -> None:
    assert not Path("src/domain/project_plane/knowledge_embedding_text.py").exists()

    normalization = _read("src/application/services/knowledge_normalization_service.py")
    assert "build_knowledge_embedding_text" not in normalization
    assert ".with_embedding_text(" not in normalization


def test_stage_f_does_not_expose_raw_embedding_text_to_public_or_prompt_payloads() -> (
    None
):
    dto = _read("src/application/dto/knowledge_dto.py")
    rag_contract = _read("src/infrastructure/llm/rag_contract.py")
    rag_eval_adapter = _read("src/infrastructure/rag_eval/adapters.py")
    rag_eval_repo = _read("src/infrastructure/db/repositories/rag_eval_repository.py")

    assert '"embedding_text": self.embedding_text' not in dto
    assert '"embedding_text": payload.embedding_text' not in rag_contract
    assert '"embedding_text",' not in rag_contract
    assert '"embedding_text": row.get("embedding_text")' not in rag_eval_adapter
    assert '"embedding_text": row.get("embedding_text")' not in rag_eval_repo
