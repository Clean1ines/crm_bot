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
