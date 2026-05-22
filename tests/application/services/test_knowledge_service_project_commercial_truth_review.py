from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import cast

import pytest

from src.application.ports.commercial_price import CommercialPriceKnowledgePort
from src.application.services.knowledge_service import (
    JwtDecoderPort,
    KnowledgeProjectAccessPort,
    KnowledgeService,
    KnowledgeServiceRepositoryPort,
    LoggerPort,
)
from src.domain.commercial.commercial_truth import CommercialTruthResolutionPolicy
from src.domain.commercial.price_knowledge import (
    PriceDocument,
    PriceDocumentInputKind,
    PriceDocumentSourceFormat,
    PriceDocumentStatus,
    PriceFactStatus,
    PriceSourceRef,
    PriceValueKind,
    PublishedPriceFact,
)
from src.domain.commercial.pricing import MoneyAmount
from src.domain.project_plane.knowledge_views import KnowledgeDocumentDetailView


class FakeJwt:
    ExpiredSignatureError: type[Exception] = Exception
    InvalidTokenError: type[Exception] = Exception

    @staticmethod
    def decode(token: str, secret: str, algorithms: list[str]) -> dict[str, object]:
        return {"sub": token}


class FakeProjectRepo:
    async def user_has_project_role(
        self,
        project_id: str,
        user_id: str,
        allowed_roles: Sequence[str],
    ) -> bool:
        return project_id == "project-1" and user_id == "owner-user"

    async def project_exists(self, project_id: str) -> bool:
        return project_id == "project-1"


class FakeUserRepo:
    async def is_platform_admin(self, user_id: str) -> bool:
        return False


class FakeLogger:
    def debug(self, *args: object, **kwargs: object) -> None:
        return None

    def warning(self, *args: object, **kwargs: object) -> None:
        return None

    def info(self, *args: object, **kwargs: object) -> None:
        return None

    def error(self, *args: object, **kwargs: object) -> None:
        return None

    def exception(self, *args: object, **kwargs: object) -> None:
        return None


class FakeCommercialPriceRepo:
    def __init__(
        self,
        *,
        price_documents: Sequence[PriceDocument],
        facts: Sequence[PublishedPriceFact],
    ) -> None:
        self.price_documents = tuple(price_documents)
        self.facts = tuple(facts)
        self.list_documents_calls: list[str] = []
        self.list_facts_calls: list[tuple[str, tuple[str, ...], bool]] = []

    async def list_price_documents_for_project(
        self,
        *,
        project_id: str,
    ) -> tuple[PriceDocument, ...]:
        self.list_documents_calls.append(project_id)
        return self.price_documents

    async def list_price_facts_for_documents(
        self,
        *,
        project_id: str,
        price_document_ids: Sequence[str],
        include_non_runtime: bool = False,
    ) -> tuple[PublishedPriceFact, ...]:
        requested_ids = tuple(price_document_ids)
        self.list_facts_calls.append((project_id, requested_ids, include_non_runtime))
        requested = set(requested_ids)
        return tuple(fact for fact in self.facts if fact.price_document_id in requested)


class FakeKnowledgeRepo:
    def __init__(
        self,
        documents_by_id: dict[str, KnowledgeDocumentDetailView],
    ) -> None:
        self.documents_by_id = dict(documents_by_id)
        self.get_document_calls: list[str] = []

    async def get_document(
        self,
        document_id: str,
    ) -> KnowledgeDocumentDetailView | None:
        self.get_document_calls.append(document_id)
        return self.documents_by_id.get(document_id)


def _price_document(
    *,
    price_document_id: str,
    knowledge_document_id: str,
) -> PriceDocument:
    return PriceDocument(
        id=price_document_id,
        project_id="project-1",
        knowledge_document_id=knowledge_document_id,
        source_format=PriceDocumentSourceFormat.MARKDOWN,
        input_kind=PriceDocumentInputKind.MIXED,
        status=PriceDocumentStatus.READY,
    )


def _knowledge_document(
    *,
    document_id: str,
    file_name: str,
    preprocessing_mode: str,
    created_at: str,
) -> KnowledgeDocumentDetailView:
    return KnowledgeDocumentDetailView(
        id=document_id,
        project_id="project-1",
        file_name=file_name,
        file_size=1024,
        status="processed",
        error=None,
        uploaded_by=None,
        created_at=created_at,
        updated_at=created_at,
        chunk_count=1,
        preprocessing_mode=preprocessing_mode,
    )


def _source_ref(
    *,
    price_document_id: str,
    quote: str,
) -> PriceSourceRef:
    return PriceSourceRef(
        price_document_id=price_document_id,
        source_unit_id=f"{price_document_id}-unit-1",
        source_row_id=None,
        quote=quote,
    )


def _published_price_fact(
    *,
    fact_id: str,
    price_document_id: str,
    amount: str,
    quote: str,
) -> PublishedPriceFact:
    return PublishedPriceFact(
        id=fact_id,
        project_id="project-1",
        price_document_id=price_document_id,
        item_name="Pro",
        value_kind=PriceValueKind.EXACT,
        status=PriceFactStatus.PUBLISHED,
        amount=MoneyAmount(amount=Decimal(amount), currency="RUB"),
        unit="month",
        source_refs=(_source_ref(price_document_id=price_document_id, quote=quote),),
        confidence=Decimal("0.95"),
    )


def _service() -> KnowledgeService:
    return KnowledgeService(
        cast(KnowledgeProjectAccessPort, FakeProjectRepo()),
        FakeUserRepo(),
        object(),
        "secret",
        cast(JwtDecoderPort, FakeJwt),
    )


@pytest.mark.asyncio
async def test_project_commercial_truth_review_policy_preview_cross_document_conflict() -> (
    None
):
    price_list_document = _price_document(
        price_document_id="price-doc-prices",
        knowledge_document_id="knowledge-prices",
    )
    faq_document = _price_document(
        price_document_id="price-doc-faq",
        knowledge_document_id="knowledge-faq",
    )

    price_list_fact = _published_price_fact(
        fact_id="price-list-pro",
        price_document_id=price_list_document.id,
        amount="2490",
        quote="Pro — 2490 ₽/мес.",
    )
    faq_fact = _published_price_fact(
        fact_id="faq-pro",
        price_document_id=faq_document.id,
        amount="2990",
        quote="Pro стоит 2990 ₽ в месяц.",
    )

    price_repo = FakeCommercialPriceRepo(
        price_documents=(price_list_document, faq_document),
        facts=(price_list_fact, faq_fact),
    )
    knowledge_repo = FakeKnowledgeRepo(
        {
            "knowledge-prices": _knowledge_document(
                document_id="knowledge-prices",
                file_name="prices_may.md",
                preprocessing_mode="price_list",
                created_at="2026-05-01T12:00:00+00:00",
            ),
            "knowledge-faq": _knowledge_document(
                document_id="knowledge-faq",
                file_name="faq_newer.md",
                preprocessing_mode="faq",
                created_at="2026-05-03T12:00:00+00:00",
            ),
        }
    )
    service = _service()

    def commercial_price_repo_factory(pool: object) -> CommercialPriceKnowledgePort:
        return cast(CommercialPriceKnowledgePort, price_repo)

    def knowledge_repo_factory(pool: object) -> KnowledgeServiceRepositoryPort:
        return cast(KnowledgeServiceRepositoryPort, knowledge_repo)

    manual_report = await service.project_commercial_truth_review(
        "project-1",
        "Bearer owner-user",
        commercial_price_repo_factory=commercial_price_repo_factory,
        knowledge_repo_factory=knowledge_repo_factory,
        logger=cast(LoggerPort, FakeLogger()),
        policy=CommercialTruthResolutionPolicy.MANUAL_REVIEW,
    )
    higher_authority_report = await service.project_commercial_truth_review(
        "project-1",
        "Bearer owner-user",
        commercial_price_repo_factory=commercial_price_repo_factory,
        knowledge_repo_factory=knowledge_repo_factory,
        logger=cast(LoggerPort, FakeLogger()),
        policy=CommercialTruthResolutionPolicy.HIGHER_AUTHORITY_WINS,
    )
    newer_source_report = await service.project_commercial_truth_review(
        "project-1",
        "Bearer owner-user",
        commercial_price_repo_factory=commercial_price_repo_factory,
        knowledge_repo_factory=knowledge_repo_factory,
        logger=cast(LoggerPort, FakeLogger()),
        policy=CommercialTruthResolutionPolicy.NEWER_SOURCE_WINS,
    )

    assert manual_report.conflict_count == 1
    assert manual_report.unresolved_conflict_count == 1
    assert manual_report.surface_fact_ids == ()

    assert higher_authority_report.conflict_count == 1
    assert higher_authority_report.resolved_conflict_count == 1
    assert higher_authority_report.surface_fact_ids == ("price-list-pro",)
    assert higher_authority_report.conflicts[0].selected_fact_id == "price-list-pro"

    assert newer_source_report.conflict_count == 1
    assert newer_source_report.resolved_conflict_count == 1
    assert newer_source_report.surface_fact_ids == ("faq-pro",)
    assert newer_source_report.conflicts[0].selected_fact_id == "faq-pro"

    assert price_repo.list_documents_calls == ["project-1", "project-1", "project-1"]
    assert price_repo.list_facts_calls == [
        ("project-1", ("price-doc-prices", "price-doc-faq"), True),
        ("project-1", ("price-doc-prices", "price-doc-faq"), True),
        ("project-1", ("price-doc-prices", "price-doc-faq"), True),
    ]
    assert knowledge_repo.get_document_calls == [
        "knowledge-prices",
        "knowledge-faq",
        "knowledge-prices",
        "knowledge-faq",
        "knowledge-prices",
        "knowledge-faq",
    ]


@pytest.mark.asyncio
async def test_project_commercial_truth_review_returns_empty_report_without_price_documents() -> (
    None
):
    price_repo = FakeCommercialPriceRepo(price_documents=(), facts=())
    knowledge_repo = FakeKnowledgeRepo({})
    service = _service()

    def commercial_price_repo_factory(pool: object) -> CommercialPriceKnowledgePort:
        return cast(CommercialPriceKnowledgePort, price_repo)

    def knowledge_repo_factory(pool: object) -> KnowledgeServiceRepositoryPort:
        return cast(KnowledgeServiceRepositoryPort, knowledge_repo)

    report = await service.project_commercial_truth_review(
        "project-1",
        "Bearer owner-user",
        commercial_price_repo_factory=commercial_price_repo_factory,
        knowledge_repo_factory=knowledge_repo_factory,
        logger=cast(LoggerPort, FakeLogger()),
        policy=CommercialTruthResolutionPolicy.HIGHER_AUTHORITY_WINS,
    )

    assert report.policy == CommercialTruthResolutionPolicy.HIGHER_AUTHORITY_WINS
    assert report.fact_count == 0
    assert report.conflict_count == 0
    assert report.surface_fact_ids == ()
    assert price_repo.list_documents_calls == ["project-1"]
    assert price_repo.list_facts_calls == []
    assert knowledge_repo.get_document_calls == []
