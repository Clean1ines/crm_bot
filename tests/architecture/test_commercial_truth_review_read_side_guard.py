from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REVIEW_SERVICE = ROOT / "src/application/services/commercial_truth_review_service.py"
COMMERCIAL_SERVICE = (
    ROOT / "src/application/services/commercial_price_review_service.py"
)
HTTP = ROOT / "src/interfaces/http/knowledge.py"


def _slice_between(source: str, start_marker: str, end_markers: tuple[str, ...]) -> str:
    start = source.index(start_marker)
    end_candidates = [
        source.index(marker, start)
        for marker in end_markers
        if marker in source[start + len(start_marker) :]
    ]
    end = min(end_candidates) if end_candidates else len(source)
    return source[start:end]


def test_commercial_truth_review_read_side_has_service_method_and_route() -> None:
    service_source = COMMERCIAL_SERVICE.read_text(encoding="utf-8")
    http_source = HTTP.read_text(encoding="utf-8")

    assert "async def commercial_truth_review(" in service_source
    assert '@router.get("/{document_id}/commercial-truth-review")' in http_source
    assert "CommercialTruthReviewService()" in service_source
    assert "review_price_facts(" in service_source
    assert "KnowledgeService(" not in service_source


def test_commercial_truth_review_read_side_includes_non_runtime_facts() -> None:
    source = COMMERCIAL_SERVICE.read_text(encoding="utf-8")

    assert "_price_document_for_knowledge_document(document_id)" in source
    assert "get_price_document_by_knowledge_document" in source
    assert "list_price_facts_for_document" in source
    assert "include_non_runtime=True" in source
    assert "commercial_source_descriptor_from_price_document" in source


def test_commercial_truth_review_source_classification_is_conservative() -> None:
    source = REVIEW_SERVICE.read_text(encoding="utf-8")

    assert "def commercial_source_kind_from_price_document(" in source
    assert "PriceDocumentSourceFormat.CSV" in source
    assert "PriceDocumentInputKind.TABLE" in source
    assert "CommercialSourceKind.STRUCTURED_PRICE_LIST" in source
    assert "CommercialSourceKind.COMMERCIAL_OFFER" in source
    assert "CommercialSourceKind.UNKNOWN" in source


def test_commercial_truth_review_read_side_does_not_publish_or_touch_runtime_lookup() -> (
    None
):
    service_source = COMMERCIAL_SERVICE.read_text(encoding="utf-8")
    http_source = HTTP.read_text(encoding="utf-8")
    review_method = _slice_between(
        service_source,
        "    async def commercial_truth_review(",
        ("    async def _price_document_for_knowledge_document(",),
    )

    combined = review_method + "\n" + http_source

    assert "publish_price_facts(" not in review_method
    assert "reject_price_facts(" not in review_method
    assert "list_published_price_facts_for_lookup(" not in combined
    assert "PriceLookupTool" not in combined
    assert "SearchKnowledgeTool" not in combined


def test_commercial_truth_review_read_side_exposes_value_text_and_source_quote() -> (
    None
):
    source = REVIEW_SERVICE.read_text(encoding="utf-8")

    assert "value_text: str" in source
    assert "source_quote: str" in source
    assert "commercial_truth_fact_value_text" in source
    assert "commercial_truth_source_quote" in source
    assert '"value_text": self.value_text' in source
    assert '"source_quote": self.source_quote' in source


def test_commercial_truth_review_read_side_exposes_surface_fact_reviews() -> None:
    source = REVIEW_SERVICE.read_text(encoding="utf-8")

    assert "def surface_fact_reviews(self)" in source
    assert '"surface_facts": [' in source
    assert "surface_fact_reviews" in source
    assert "surface_fact_ids" in source


def test_commercial_truth_review_uses_knowledge_document_metadata_for_source_semantics() -> (
    None
):
    review_source = REVIEW_SERVICE.read_text(encoding="utf-8")
    service_source = COMMERCIAL_SERVICE.read_text(encoding="utf-8")
    http_source = HTTP.read_text(encoding="utf-8")

    assert "knowledge_document" in review_source
    assert 'preprocessing_mode == "price_list"' in review_source
    assert 'preprocessing_mode == "faq"' in review_source
    assert "observed_at=_commercial_source_observed_at" in review_source
    assert "title=_commercial_source_title" in review_source

    assert "CommercialKnowledgeDocumentMetadataPort" in service_source
    assert "self._knowledge_document_repo.get_document(" in service_source
    assert "commercial_source_descriptor_from_price_document(" in service_source
    assert "make_commercial_price_review_service(pool)" in http_source


def test_commercial_truth_review_read_side_exposes_source_title_and_observed_at() -> (
    None
):
    source = REVIEW_SERVICE.read_text(encoding="utf-8")

    assert "source_title: str" in source
    assert "source_observed_at: str" in source
    assert "commercial_truth_source_observed_at_text" in source
    assert '"source_title": self.source_title' in source
    assert '"source_observed_at": self.source_observed_at' in source
    assert "source_title=snapshot.source.title" in source
    assert "source_observed_at=commercial_truth_source_observed_at_text" in source


def test_commercial_truth_review_read_side_accepts_policy_preview_without_mutation() -> (
    None
):
    service_source = COMMERCIAL_SERVICE.read_text(encoding="utf-8")
    http_source = HTTP.read_text(encoding="utf-8")

    assert "CommercialTruthResolutionPolicy" in service_source
    assert "CommercialTruthResolutionPolicy" in http_source
    assert "policy: CommercialTruthResolutionPolicy" in service_source
    assert "policy: CommercialTruthResolutionPolicy" in http_source
    assert "policy=policy" in service_source
    assert "policy=policy" in http_source

    review_method = _slice_between(
        service_source,
        "    async def commercial_truth_review(",
        ("    async def _price_document_for_knowledge_document(",),
    )

    assert "publish_price_facts(" not in review_method
    assert "reject_price_facts(" not in review_method
    assert "list_published_price_facts_for_lookup(" not in review_method


def test_commercial_truth_policy_query_param_is_scoped_to_commercial_truth_routes() -> (
    None
):
    source = HTTP.read_text(encoding="utf-8")
    allowed_route_names = (
        "async def project_commercial_truth_review(",
        "async def knowledge_commercial_truth_review(",
    )

    for route_name in allowed_route_names:
        route_start = source.index(route_name)
        next_route = source.find("\n@router.", route_start)
        route = (
            source[route_start:] if next_route == -1 else source[route_start:next_route]
        )

        assert "CommercialTruthResolutionPolicy.MANUAL_REVIEW" in route
        assert "policy=policy" in route

    route_blocks = source.split("\n@router.")
    for block in route_blocks:
        if (
            "CommercialTruthResolutionPolicy.MANUAL_REVIEW" not in block
            and "policy=policy" not in block
        ):
            continue
        assert any(route_name in block for route_name in allowed_route_names)


def test_commercial_truth_review_policy_preview_is_document_scoped_today() -> None:
    service_source = COMMERCIAL_SERVICE.read_text(encoding="utf-8")
    review_method = _slice_between(
        service_source,
        "    async def commercial_truth_review(",
        ("    async def _price_document_for_knowledge_document(",),
    )
    price_document_helper = _slice_between(
        service_source,
        "    async def _price_document_for_knowledge_document(",
        ("    async def _require_price_document_for_knowledge_document(",),
    )

    assert "_price_document_for_knowledge_document(document_id)" in review_method
    assert "get_price_document_by_knowledge_document" in price_document_helper
    assert "list_price_facts_for_document" in review_method
    assert "price_document_id=str(price_document.id)" in review_method
    assert "self._knowledge_document_repo.get_document(" in service_source

    assert "list_price_documents_for_project" not in review_method
    assert "list_price_facts_for_documents" not in review_method
