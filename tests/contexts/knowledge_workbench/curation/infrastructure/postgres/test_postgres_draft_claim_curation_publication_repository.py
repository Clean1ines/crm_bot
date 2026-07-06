from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_publication import (
    DraftClaimCurationPublicationCandidate,
    DraftClaimCurationPublicationItem,
)
from src.contexts.knowledge_workbench.curation.infrastructure.postgres.postgres_draft_claim_curation_publication_repository import (
    PostgresDraftClaimCurationPublicationRepository,
)


def test_postgres_publication_repository_materializes_runtime_before_workspace_publish() -> (
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
    runtime_projection_reset = publish_method.index(
        "_deactivate_existing_runtime_projection"
    )
    workspace_publish = publish_method.index("UPDATE draft_claim_curation_workspaces")

    assert runtime_projection_reset < runtime_upsert
    assert runtime_embedding_upsert < workspace_publish
    assert "DELETE FROM draft_claim_embeddings" not in publish_method
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


@pytest.mark.asyncio
async def test_republication_deactivates_stale_runtime_entries_and_embeddings() -> None:
    connection = _FakePublicationConnection()
    repository = PostgresDraftClaimCurationPublicationRepository(connection)
    first = _publication(
        publication_id="publication-1",
        workflow_run_id="workflow-1",
        items=(_item("item-a"), _item("item-b")),
    )

    first_result = await repository.publish_curated_claims(publication=first)

    assert first_result.runtime_entry_count == 2
    assert first_result.embedding_count == 2
    assert first_result.deleted_draft_embedding_count == 0
    assert _active_runtime_entry_ids(connection) == {
        "runtime:item-a",
        "runtime:item-b",
    }
    assert set(connection.runtime_embeddings) == {
        ("runtime:item-a", "embedding-model"),
        ("runtime:item-b", "embedding-model"),
    }

    second = _publication(
        publication_id="publication-2",
        workflow_run_id="workflow-1",
        items=(_item("item-a", vector=(0.3, 0.4)),),
    )

    second_result = await repository.publish_curated_claims(publication=second)

    assert second_result.runtime_entry_count == 1
    assert second_result.embedding_count == 1
    assert second_result.deleted_draft_embedding_count == 0
    assert _active_runtime_entry_ids(connection) == {"runtime:item-a"}
    stale = connection.runtime_entries["runtime:item-b"]
    assert stale["visibility"] == "hidden"
    assert stale["status"] == "inactive"
    assert ("runtime:item-b", "embedding-model") not in connection.runtime_embeddings
    assert set(connection.runtime_embeddings) == {("runtime:item-a", "embedding-model")}
    assert (
        connection.runtime_embeddings[("runtime:item-a", "embedding-model")][
            "embedding"
        ]
        == "[0.3,0.4]"
    )


def test_runtime_search_sql_does_not_use_draft_embeddings_or_observations() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_search_queries.py"
    ).read_text(encoding="utf-8")

    assert "draft_claim_embeddings" not in source
    assert "draft_claim_observations" not in source
    assert "knowledge_workbench_runtime_retrieval_entry_embeddings" in source


def _sql_text_only(section: str) -> str:
    parts = section.split('"""')
    return "\n".join(parts[index] for index in range(1, len(parts), 2))


@dataclass(slots=True)
class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


class _FakePublicationConnection:
    def __init__(self) -> None:
        self.runtime_entries: dict[str, dict[str, object]] = {}
        self.runtime_embeddings: dict[tuple[str, str], dict[str, object]] = {}

    def transaction(self) -> _Transaction:
        return _Transaction()

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        if (
            "SELECT runtime_entry_id" in query
            and "FROM knowledge_workbench_runtime_retrieval_entries" in query
        ):
            workflow_run_id = str(args[0])
            return [
                {"runtime_entry_id": runtime_entry_id}
                for runtime_entry_id, row in self.runtime_entries.items()
                if row["workflow_run_id"] == workflow_run_id
            ]
        return []

    async def execute(self, query: str, *args: object) -> str:
        if (
            "DELETE FROM knowledge_workbench_runtime_retrieval_entry_embeddings"
            in query
            and "ANY" in query
        ):
            runtime_entry_ids = set(args[0])
            before = len(self.runtime_embeddings)
            self.runtime_embeddings = {
                key: value
                for key, value in self.runtime_embeddings.items()
                if key[0] not in runtime_entry_ids
            }
            return f"DELETE {before - len(self.runtime_embeddings)}"
        if (
            "UPDATE knowledge_workbench_runtime_retrieval_entries" in query
            and "visibility = 'hidden'" in query
        ):
            workflow_run_id = str(args[0])
            updated_at = args[1]
            count = 0
            for row in self.runtime_entries.values():
                if row["workflow_run_id"] == workflow_run_id:
                    row["visibility"] = "hidden"
                    row["status"] = "inactive"
                    row["updated_at"] = updated_at
                    count += 1
            return f"UPDATE {count}"
        if (
            "INSERT INTO knowledge_workbench_runtime_retrieval_entries" in query
            and "ON CONFLICT" in query
        ):
            self.runtime_entries[str(args[0])] = {
                "runtime_entry_id": args[0],
                "project_id": args[1],
                "fact_id": args[2],
                "publication_id": args[3],
                "workflow_run_id": args[4],
                "source_document_ref": args[5],
                "curation_item_ref": args[6],
                "claim": args[7],
                "claim_kind": args[8],
                "granularity": args[9],
                "possible_questions": json.loads(str(args[10])),
                "exclusion_scope": args[11],
                "evidence_block": args[12],
                "triples": json.loads(str(args[13])),
                "source_claim_refs": json.loads(str(args[14])),
                "answer_text": args[15],
                "embedding_text": args[16],
                "source_refs": json.loads(str(args[17])),
                "visibility": "published",
                "status": "active",
                "created_at": args[18],
                "updated_at": args[18],
            }
            return "INSERT 0 1"
        if (
            "DELETE FROM knowledge_workbench_runtime_retrieval_entry_embeddings"
            in query
            and "runtime_entry_id = $1" in query
        ):
            key = (str(args[0]), str(args[1]))
            existed = key in self.runtime_embeddings
            self.runtime_embeddings.pop(key, None)
            return f"DELETE {1 if existed else 0}"
        if (
            "INSERT INTO knowledge_workbench_runtime_retrieval_entry_embeddings"
            in query
        ):
            key = (str(args[0]), str(args[1]))
            self.runtime_embeddings[key] = {
                "runtime_entry_id": args[0],
                "embedding_model_id": args[1],
                "dimensions": args[2],
                "embedding": args[3],
                "embedding_text_hash": args[4],
                "created_at": args[5],
            }
            return "INSERT 0 1"
        if "DELETE FROM draft_claim_embeddings" in query:
            raise AssertionError("publication must not delete draft_claim_embeddings")
        return "UPDATE 0"


def _publication(
    *,
    publication_id: str,
    workflow_run_id: str,
    items: tuple[DraftClaimCurationPublicationItem, ...],
) -> DraftClaimCurationPublicationCandidate:
    return DraftClaimCurationPublicationCandidate(
        publication_id=publication_id,
        workflow_run_id=workflow_run_id,
        project_id="11111111-1111-1111-1111-111111111111",
        source_document_ref="source-document-1",
        fact_registry_id="registry-1",
        items=items,
        excluded_item_count=0,
        published_at=datetime(2026, 7, 5, 12, 0, tzinfo=UTC),
    )


def _item(
    item_ref: str,
    *,
    vector: tuple[float, ...] = (0.1, 0.2),
) -> DraftClaimCurationPublicationItem:
    return DraftClaimCurationPublicationItem(
        item_ref=item_ref,
        fact_id=f"fact:{item_ref}",
        runtime_entry_id=f"runtime:{item_ref}",
        claim=f"Claim for {item_ref}",
        claim_kind="faq_workbench_fact",
        granularity="atomic",
        possible_questions=(f"Question for {item_ref}?",),
        exclusion_scope="",
        evidence_block=f"Evidence for {item_ref}",
        source_claim_refs=(f"source-claim:{item_ref}",),
        triples=({"subject": item_ref, "predicate": "is", "object": "published"},),
        embedding_text=f"Claim for {item_ref}\nQuestion for {item_ref}?",
        embedding_text_hash=f"hash:{item_ref}",
        embedding_model_id="embedding-model",
        embedding_dimensions=len(vector),
        vector=vector,
    )


def _active_runtime_entry_ids(connection: _FakePublicationConnection) -> set[str]:
    return {
        runtime_entry_id
        for runtime_entry_id, row in connection.runtime_entries.items()
        if row["visibility"] == "published" and row["status"] == "active"
    }
