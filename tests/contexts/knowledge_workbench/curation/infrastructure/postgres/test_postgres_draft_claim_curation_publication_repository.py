from __future__ import annotations

from pathlib import Path


def test_postgres_publication_repository_persists_runtime_then_deletes_draft_embeddings() -> (
    None
):
    source = Path(
        "src/contexts/knowledge_workbench/curation/infrastructure/postgres/"
        "postgres_draft_claim_curation_publication_repository.py"
    ).read_text(encoding="utf-8")

    publish_method = source[
        source.index("async def _publish_with_connection") : source.index(
            "async def _upsert_publication"
        )
    ]

    runtime_upsert = publish_method.index("_upsert_runtime_entry")
    runtime_embedding_upsert = publish_method.index("_replace_runtime_embedding")
    draft_delete = publish_method.index("DELETE FROM draft_claim_embeddings")
    workspace_publish = publish_method.index("UPDATE draft_claim_curation_workspaces")

    assert runtime_upsert < draft_delete
    assert runtime_embedding_upsert < draft_delete
    assert draft_delete < workspace_publish
    assert "editable_payload" not in source
    assert "original_payload" not in source
    assert "preview_payload" not in source


def test_publish_repository_uses_answer_text_only_as_deprecated_db_compatibility() -> (
    None
):
    source = Path(
        "src/contexts/knowledge_workbench/curation/infrastructure/postgres/"
        "postgres_draft_claim_curation_publication_repository.py"
    ).read_text(encoding="utf-8")

    assert "answer_text is a deprecated runtime table compatibility column" in source
    assert "answer_text, embedding_text" in source
    assert "answer_text = EXCLUDED.answer_text" in source


def test_publish_repository_populates_runtime_entry_canonical_fields() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/curation/infrastructure/postgres/"
        "postgres_draft_claim_curation_publication_repository.py"
    ).read_text(encoding="utf-8")
    runtime_upsert = source[
        source.index("async def _upsert_runtime_entry") : source.index(
            "async def _replace_runtime_embedding"
        )
    ]

    for column in (
        "publication_id",
        "workflow_run_id",
        "source_document_ref",
        "curation_item_ref",
        "claim_kind",
        "granularity",
        "exclusion_scope",
        "evidence_block",
        "triples",
        "source_claim_refs",
        "updated_at",
    ):
        assert column in runtime_upsert

    for expression in (
        "publication.publication_id",
        "publication.workflow_run_id",
        "publication.source_document_ref",
        "item.item_ref",
        "item.claim_kind",
        "item.granularity",
        "item.exclusion_scope",
        "item.evidence_block",
        "json.dumps(list(item.triples), ensure_ascii=False)",
        "json.dumps(list(item.source_claim_refs), ensure_ascii=False)",
    ):
        assert expression in runtime_upsert


def test_publish_repository_uses_current_registry_id_sql_columns() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/curation/infrastructure/postgres/"
        "postgres_draft_claim_curation_publication_repository.py"
    ).read_text(encoding="utf-8")

    for section_name in (
        "async def _upsert_fact_registry",
        "async def _upsert_fact",
        "async def _replace_fact_triples",
    ):
        section = source[source.index(section_name) :]
        section = section[: section.index("\n\nasync def ", 1)]
        assert "registry_id" in section
        assert "fact_registry_id" not in _sql_text_only(section)


def _sql_text_only(section: str) -> str:
    parts = section.split('"""')
    return "\n".join(parts[index] for index in range(1, len(parts), 2))
