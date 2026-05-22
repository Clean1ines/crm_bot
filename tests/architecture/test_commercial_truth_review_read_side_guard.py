from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REVIEW_SERVICE = ROOT / "src/application/services/commercial_truth_review_service.py"
KNOWLEDGE_SERVICE = ROOT / "src/application/services/knowledge_service.py"
HTTP = ROOT / "src/interfaces/http/knowledge.py"


def test_commercial_truth_review_read_side_has_service_method_and_route() -> None:
    service_source = KNOWLEDGE_SERVICE.read_text(encoding="utf-8")
    http_source = HTTP.read_text(encoding="utf-8")

    assert "async def commercial_truth_review(" in service_source
    assert '@router.get("/{document_id}/commercial-truth-review")' in http_source
    assert "CommercialTruthReviewService().review_price_facts(" in service_source


def test_commercial_truth_review_read_side_includes_non_runtime_facts() -> None:
    source = KNOWLEDGE_SERVICE.read_text(encoding="utf-8")

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
    combined = (
        KNOWLEDGE_SERVICE.read_text(encoding="utf-8")
        + "\n"
        + HTTP.read_text(encoding="utf-8")
    )

    assert "publish_price_facts(" in combined
    assert "reject_price_facts(" in combined

    review_method_start = combined.index("async def commercial_truth_review(")
    review_method_end = combined.index(
        "async def cancel_document_processing(", review_method_start
    )
    review_method = combined[review_method_start:review_method_end]

    assert "publish_price_facts(" not in review_method
    assert "reject_price_facts(" not in review_method
    assert "list_published_price_facts_for_lookup(" not in review_method
    assert "PriceLookupTool" not in review_method


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
    service_source = KNOWLEDGE_SERVICE.read_text(encoding="utf-8")
    http_source = HTTP.read_text(encoding="utf-8")

    assert "KnowledgeDocumentDetailView" in review_source
    assert "knowledge_document: KnowledgeDocumentDetailView | None" in review_source
    assert 'preprocessing_mode == "price_list"' in review_source
    assert 'preprocessing_mode == "faq"' in review_source
    assert "observed_at=_commercial_source_observed_at" in review_source
    assert "title=_commercial_source_title" in review_source
    assert (
        "knowledge_repo_factory: KnowledgeServiceRepositoryFactoryPort"
        in service_source
    )
    assert "knowledge_repo.get_document(document_id)" in service_source
    assert "knowledge_repo_factory=make_knowledge_repo" in http_source


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
    service_source = KNOWLEDGE_SERVICE.read_text(encoding="utf-8")
    http_source = HTTP.read_text(encoding="utf-8")

    assert "CommercialTruthResolutionPolicy" in service_source
    assert "CommercialTruthResolutionPolicy" in http_source
    assert "policy: CommercialTruthResolutionPolicy" in service_source
    assert "policy: CommercialTruthResolutionPolicy" in http_source
    assert "policy=policy" in service_source
    assert "policy=policy" in http_source

    review_method_start = service_source.index("async def commercial_truth_review(")
    review_method_end = service_source.index(
        "async def cancel_document_processing(",
        review_method_start,
    )
    review_method = service_source[review_method_start:review_method_end]

    assert "publish_price_facts(" not in review_method
    assert "reject_price_facts(" not in review_method
    assert "list_published_price_facts_for_lookup(" not in review_method


def test_commercial_truth_policy_query_param_is_scoped_to_commercial_truth_route() -> (
    None
):
    source = HTTP.read_text(encoding="utf-8")
    policy_param = (
        "policy: CommercialTruthResolutionPolicy = "
        "CommercialTruthResolutionPolicy.MANUAL_REVIEW"
    )

    assert source.count(policy_param) == 1

    route_start = source.index("async def knowledge_commercial_truth_review(")
    route_end = source.index("@router.post", route_start)
    commercial_truth_route = source[route_start:route_end]

    assert policy_param in commercial_truth_route
    assert "policy=policy" in commercial_truth_route

    forbidden_route_names = (
        "async def preview_knowledge(",
        "async def knowledge_usage(",
        "async def list_project_knowledge(",
        "async def upload_project_knowledge(",
        "async def get_knowledge_processing_report(",
        "async def knowledge_processing_progress(",
        "async def knowledge_price_facts(",
    )

    for route_name in forbidden_route_names:
        if route_name not in source:
            continue

        start = source.index(route_name)
        next_route = source.find("\n@router.", start)
        route = source[start:] if next_route == -1 else source[start:next_route]

        assert policy_param not in route
        assert "policy=policy" not in route


def test_commercial_truth_review_policy_preview_is_document_scoped_today() -> None:
    service_source = KNOWLEDGE_SERVICE.read_text(encoding="utf-8")

    review_method_start = service_source.index("async def commercial_truth_review(")
    review_method_end = service_source.index(
        "async def cancel_document_processing(",
        review_method_start,
    )
    review_method = service_source[review_method_start:review_method_end]

    assert "get_price_document_by_knowledge_document" in review_method
    assert "list_price_facts_for_document" in review_method
    assert "price_document_id=price_document.id" in review_method
    assert "knowledge_document_id=document_id" in review_method

    # Important product boundary:
    # current policy preview is a read-only per-document review. It can preview
    # policy effects for conflicts present inside the loaded document's facts,
    # but it is not yet a project-wide or upload-batch Commercial Truth surface.
    #
    # Cross-document conflicts such as:
    # - prices_may.md says Pro = 2490 RUB
    # - faq_old.md says Pro = 2990 RUB
    #
    # require a separate project/batch review port that can load multiple
    # price_documents and their KnowledgeDocument metadata together.
    assert "list_price_documents_for_project" not in review_method
    assert "list_price_facts_for_project" not in review_method
    assert "list_project_commercial_truth" not in review_method
