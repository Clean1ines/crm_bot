from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, cast

from src.application.dto.knowledge_dto import (
    KnowledgePriceFactsMutationResultDto,
    KnowledgePriceFactsResponseDto,
)
from src.application.ports.commercial_price import CommercialPriceKnowledgePort
from src.application.services.commercial_truth_review_service import (
    CommercialTruthReviewService,
    commercial_source_descriptor_from_price_document,
)
from src.domain.commercial.commercial_truth import (
    CommercialSourceDescriptor,
    CommercialTruthResolutionPolicy,
)
from src.domain.commercial.price_knowledge import (
    PriceDocument,
    PublishedPriceFact,
)
from src.domain.project_plane.knowledge_views import KnowledgeDocumentDetailView


class CommercialKnowledgeDocumentMetadataPort(Protocol):
    async def get_document(
        self,
        document_id: str,
    ) -> object | None: ...


class CommercialPriceReviewService:
    """Read-side and review actions for commercial structured knowledge.

    This service replaces the commercial methods that used to live on the
    retired KnowledgeService facade. It deliberately does not call runtime
    lookup tools and does not publish facts to runtime retrieval.
    """

    def __init__(
        self,
        *,
        repo: CommercialPriceKnowledgePort,
        knowledge_document_repo: CommercialKnowledgeDocumentMetadataPort,
    ) -> None:
        self._repo = repo
        self._knowledge_document_repo = knowledge_document_repo
        self._truth_review = CommercialTruthReviewService()

    async def price_facts(self, *, document_id: str) -> dict[str, object]:
        price_document = await self._price_document_for_knowledge_document(document_id)
        if price_document is None:
            return _price_facts_empty_response(document_id=document_id)

        facts = await self._repo.list_price_facts_for_document(
            project_id=price_document.project_id,
            price_document_id=price_document.id,
            include_non_runtime=True,
        )
        return _price_facts_response(
            document_id=document_id,
            price_document_id=price_document.id,
            facts=facts,
        )

    async def publish_price_facts(
        self,
        *,
        document_id: str,
        fact_ids: Sequence[str] = (),
        reviewed_by: str = "system",
    ) -> dict[str, object]:
        price_document = await self._require_price_document_for_knowledge_document(
            document_id
        )

        affected = await self._repo.publish_price_facts(
            project_id=price_document.project_id,
            price_document_id=price_document.id,
            fact_ids=tuple(fact_ids),
        )
        facts = await self._repo.list_price_facts_for_document(
            project_id=price_document.project_id,
            price_document_id=price_document.id,
            include_non_runtime=True,
        )
        return _price_facts_mutation_response(
            document_id=document_id,
            price_document_id=price_document.id,
            affected_count=int(affected or 0),
            facts=facts,
        )

    async def reject_price_facts(
        self,
        *,
        document_id: str,
        fact_ids: Sequence[str] = (),
        reviewed_by: str = "system",
        reason: str = "",
    ) -> dict[str, object]:
        price_document = await self._require_price_document_for_knowledge_document(
            document_id
        )

        affected = await self._repo.reject_price_facts(
            project_id=price_document.project_id,
            price_document_id=price_document.id,
            fact_ids=tuple(fact_ids),
            reason=reason,
        )
        facts = await self._repo.list_price_facts_for_document(
            project_id=price_document.project_id,
            price_document_id=price_document.id,
            include_non_runtime=True,
        )
        return _price_facts_mutation_response(
            document_id=document_id,
            price_document_id=price_document.id,
            affected_count=int(affected or 0),
            facts=facts,
        )

    async def project_commercial_truth_review(
        self,
        *,
        project_id: str,
        policy: CommercialTruthResolutionPolicy = CommercialTruthResolutionPolicy.MANUAL_REVIEW,
    ) -> dict[str, object]:
        price_documents = await self._repo.list_price_documents_for_project(
            project_id=project_id
        )
        price_document_ids = tuple(document.id for document in price_documents)

        facts = await self._repo.list_price_facts_for_documents(
            project_id=project_id,
            price_document_ids=price_document_ids,
            include_non_runtime=True,
        )

        sources_by_price_document_id = await self._sources_by_price_document_id(
            price_documents
        )

        return self._truth_review.review_price_facts(
            facts=facts,
            sources_by_price_document_id=sources_by_price_document_id,
            policy=policy,
        ).to_dict()

    async def commercial_truth_review(
        self,
        *,
        document_id: str,
        policy: CommercialTruthResolutionPolicy = CommercialTruthResolutionPolicy.MANUAL_REVIEW,
    ) -> dict[str, object]:
        price_document = await self._price_document_for_knowledge_document(document_id)
        if price_document is None:
            return self._truth_review.review_price_facts(
                facts=(),
                sources_by_price_document_id={},
                policy=policy,
            ).to_dict()

        facts = await self._repo.list_price_facts_for_document(
            project_id=price_document.project_id,
            price_document_id=price_document.id,
            include_non_runtime=True,
        )
        knowledge_document = await self._knowledge_document_repo.get_document(
            document_id
        )
        source = commercial_source_descriptor_from_price_document(
            price_document,
            knowledge_document=cast(
                KnowledgeDocumentDetailView | None,
                knowledge_document,
            ),
        )

        # Important product boundary:
        # current document policy preview is read-only and document-scoped.
        # Cross-document conflicts are handled by project_commercial_truth_review.
        return self._truth_review.review_price_facts(
            facts=facts,
            sources_by_price_document_id={price_document.id: source},
            policy=policy,
        ).to_dict()

    async def _price_document_for_knowledge_document(
        self,
        document_id: str,
    ) -> PriceDocument | None:
        knowledge_document = await self._knowledge_document_repo.get_document(
            document_id
        )
        if knowledge_document is None:
            return None
        project_id = getattr(knowledge_document, "project_id", None)
        if project_id is None:
            return None
        return await self._repo.get_price_document_by_knowledge_document(
            project_id=str(project_id),
            knowledge_document_id=document_id,
        )

    async def _require_price_document_for_knowledge_document(
        self,
        document_id: str,
    ) -> PriceDocument:
        price_document = await self._price_document_for_knowledge_document(document_id)
        if price_document is None:
            raise ValueError(
                f"Price document not found for knowledge document {document_id}"
            )
        return price_document

    async def _sources_by_price_document_id(
        self,
        price_documents: Sequence[PriceDocument],
    ) -> dict[str, CommercialSourceDescriptor]:
        sources_by_price_document_id: dict[str, CommercialSourceDescriptor] = {}
        for price_document in price_documents:
            knowledge_document = await self._knowledge_document_repo.get_document(
                price_document.knowledge_document_id
            )
            sources_by_price_document_id[price_document.id] = (
                commercial_source_descriptor_from_price_document(
                    price_document,
                    knowledge_document=cast(
                        KnowledgeDocumentDetailView | None,
                        knowledge_document,
                    ),
                )
            )
        return sources_by_price_document_id


def _price_facts_empty_response(*, document_id: str) -> dict[str, object]:
    return KnowledgePriceFactsResponseDto.empty(
        knowledge_document_id=document_id,
    ).to_dict()


def _price_facts_response(
    *,
    document_id: str,
    price_document_id: str,
    facts: Sequence[PublishedPriceFact],
) -> dict[str, object]:
    return KnowledgePriceFactsResponseDto.from_facts(
        knowledge_document_id=document_id,
        price_document_id=price_document_id,
        facts=tuple(facts),
    ).to_dict()


def _price_facts_mutation_response(
    *,
    document_id: str,
    price_document_id: str,
    affected_count: int,
    facts: Sequence[PublishedPriceFact],
) -> dict[str, object]:
    return KnowledgePriceFactsMutationResultDto.from_facts(
        knowledge_document_id=document_id,
        price_document_id=price_document_id,
        affected_count=affected_count,
        facts=tuple(facts),
    ).to_dict()
