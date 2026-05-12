from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_stage_f_has_single_production_embedding_text_builder() -> None:
    builder = _read("src/domain/project_plane/embedding_text.py")
    ingestion = _read("src/application/services/knowledge_ingestion_service.py")
    repository = _read("src/infrastructure/db/repositories/knowledge_repository.py")

    assert "CANONICAL_EMBEDDING_TEXT_VERSION" in builder
    assert "def build_canonical_entry_embedding_text" in builder
    assert "def build_retrieval_surface_search_text" in builder
    assert "retrieval_guards" in builder

    assert "def _canonical_embedding_text" not in ingestion
    assert "KCD_STAGE_CD_EMBEDDING_TEXT_VERSION" not in ingestion
    assert "build_canonical_entry_embedding_text" in repository
    assert "build_retrieval_surface_search_text" in repository


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
