from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
    EmbeddingGenerationRequest,
)
from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_publication import (
    DraftClaimCurationPublicationCandidate,
    DraftClaimCurationPublicationItem,
    DraftClaimCurationPublicationResult,
)
from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationWorkspaceItem,
    DraftClaimCurationWorkspaceStatus,
)
from src.contexts.knowledge_workbench.curation.application.policies.curated_claim_embedding_input_builder import (
    CuratedClaimEmbeddingInput,
    CuratedClaimEmbeddingInputBuilder,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_publication_repository_port import (
    DraftClaimCurationPublicationRepositoryPort,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_workspace_repository_port import (
    DraftClaimCurationWorkspaceRepositoryPort,
)
from src.domain.project_plane.json_types import JsonObject


class DraftClaimCurationPublicationNotFoundError(LookupError):
    pass


class DraftClaimCurationPublicationAlreadyPublishedError(RuntimeError):
    pass


class DraftClaimCurationPublicationEmptyError(RuntimeError):
    pass


class DraftClaimCurationPublicationEmbeddingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PublishDraftClaimCurationWorkspace:
    curation_workspace_repository: DraftClaimCurationWorkspaceRepositoryPort
    curation_publication_repository: DraftClaimCurationPublicationRepositoryPort
    embedding_generation_port: EmbeddingGenerationPort
    embedding_model_id: str
    embedding_dimensions: int
    embedding_input_builder: CuratedClaimEmbeddingInputBuilder = (
        CuratedClaimEmbeddingInputBuilder()
    )

    async def execute(
        self,
        *,
        workflow_run_id: str,
        published_at: datetime,
    ) -> DraftClaimCurationPublicationResult:
        _require_text(workflow_run_id, "workflow_run_id")
        if not isinstance(published_at, datetime):
            raise TypeError("published_at must be datetime")
        _require_text(self.embedding_model_id, "embedding_model_id")
        if self.embedding_dimensions <= 0:
            raise ValueError("embedding_dimensions must be positive")

        snapshot = (
            await self.curation_workspace_repository.get_workspace_by_workflow_run_id(
                workflow_run_id=workflow_run_id
            )
        )
        if snapshot is None:
            raise DraftClaimCurationPublicationNotFoundError(
                "curation workspace not found"
            )
        if snapshot.workspace.status is DraftClaimCurationWorkspaceStatus.PUBLISHED:
            raise DraftClaimCurationPublicationAlreadyPublishedError(
                "curation workspace already published"
            )

        project_id = snapshot.workspace.project_id
        source_document_ref = snapshot.workspace.source_document_ref
        if project_id is None or source_document_ref is None:
            raise ValueError("curation workspace must have project/source ownership")

        publishable_items = tuple(item for item in snapshot.items if not item.excluded)
        if not publishable_items:
            raise DraftClaimCurationPublicationEmptyError(
                "curation workspace has no publishable items"
            )

        embedding_inputs = self.embedding_input_builder.build(publishable_items)
        embedding_result = await self._embed(embedding_inputs)

        publication_items = tuple(
            _publication_item(
                workflow_run_id=workflow_run_id,
                item=item,
                embedding_input=embedding_input,
                vector=vector,
                embedding_model_id=embedding_result.model_id,
                embedding_dimensions=embedding_result.dimensions,
            )
            for item, embedding_input, vector in zip(
                publishable_items,
                embedding_inputs,
                embedding_result.embeddings,
                strict=True,
            )
        )

        publication = DraftClaimCurationPublicationCandidate(
            publication_id=_publication_id(workflow_run_id),
            workflow_run_id=workflow_run_id,
            project_id=project_id,
            source_document_ref=source_document_ref,
            fact_registry_id=_fact_registry_id(workflow_run_id),
            items=publication_items,
            excluded_item_count=len(snapshot.items) - len(publishable_items),
            published_at=published_at,
        )
        return await self.curation_publication_repository.publish_curated_claims(
            publication=publication
        )

    async def _embed(
        self,
        embedding_inputs: tuple[CuratedClaimEmbeddingInput, ...],
    ):
        try:
            result = await self.embedding_generation_port.embed(
                EmbeddingGenerationRequest(
                    texts=tuple(item.text for item in embedding_inputs),
                    model_id=self.embedding_model_id,
                    expected_dimensions=self.embedding_dimensions,
                    task="retrieval.passage",
                )
            )
        except Exception as exc:
            raise DraftClaimCurationPublicationEmbeddingError(
                "failed to generate runtime retrieval embeddings"
            ) from exc

        if len(result.embeddings) != len(embedding_inputs):
            raise DraftClaimCurationPublicationEmbeddingError(
                "embedding result count must match publishable item count"
            )
        if result.dimensions != self.embedding_dimensions:
            raise DraftClaimCurationPublicationEmbeddingError(
                "embedding result dimensions must match expected dimensions"
            )
        return result


def _publication_item(
    *,
    workflow_run_id: str,
    item: DraftClaimCurationWorkspaceItem,
    embedding_input: CuratedClaimEmbeddingInput,
    vector: tuple[float, ...],
    embedding_model_id: str,
    embedding_dimensions: int,
) -> DraftClaimCurationPublicationItem:
    payload = item.editable_payload.to_json_dict()
    return DraftClaimCurationPublicationItem(
        item_ref=item.item_ref,
        fact_id=_fact_id(workflow_run_id, item.item_ref),
        runtime_entry_id=_runtime_entry_id(workflow_run_id, item.item_ref),
        claim=_payload_text(payload, "claim"),
        claim_kind=_payload_text(payload, "claim_kind"),
        granularity=_payload_text(payload, "granularity"),
        possible_questions=_payload_text_tuple(payload, "possible_questions"),
        exclusion_scope=_payload_optional_text(payload, "exclusion_scope"),
        evidence_block=_payload_text(payload, "evidence_block"),
        source_claim_refs=tuple(item.source_claim_refs),
        triples=_payload_triples(payload),
        embedding_text=embedding_input.text,
        embedding_text_hash=embedding_input.text_hash,
        embedding_model_id=embedding_model_id,
        embedding_dimensions=embedding_dimensions,
        vector=vector,
    )


def _publication_id(workflow_run_id: str) -> str:
    return f"draft-claim-curation-publication:{workflow_run_id}"


def _fact_registry_id(workflow_run_id: str) -> str:
    return f"draft-claim-curation-fact-registry:{workflow_run_id}"


def _fact_id(workflow_run_id: str, item_ref: str) -> str:
    return "draft-claim-curation-fact:" + _digest(workflow_run_id, item_ref)


def _runtime_entry_id(workflow_run_id: str, item_ref: str) -> str:
    return "draft-claim-curation-runtime-entry:" + _digest(workflow_run_id, item_ref)


def _digest(*parts: str) -> str:
    return sha256(":".join(parts).encode("utf-8")).hexdigest()


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value.strip()


def _payload_optional_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError(f"{key} must be text")
    return value.strip()


def _payload_text_tuple(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise TypeError(f"{key} must be list")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise TypeError(f"{key}[{index}] must be text")
        stripped = item.strip()
        if stripped:
            result.append(stripped)
    return tuple(result)


def _payload_triples(payload: Mapping[str, object]) -> tuple[JsonObject, ...]:
    value = payload.get("triples")
    if not isinstance(value, list):
        raise TypeError("triples must be list")
    result: list[JsonObject] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise TypeError(f"triples[{index}] must be object")
        result.append(dict(item))
    return tuple(result)


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
