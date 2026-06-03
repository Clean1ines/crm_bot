from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PORT = ROOT / "src/application/ports/commercial_price.py"
REPO = ROOT / "src/infrastructure/db/repositories/commercial_price_repository.py"
SERVICE = ROOT / "src/application/services/commercial_price_review_service.py"
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


def test_project_commercial_truth_review_has_project_wide_port_methods() -> None:
    port_source = PORT.read_text(encoding="utf-8")
    repo_source = REPO.read_text(encoding="utf-8")

    assert "async def list_price_documents_for_project(" in port_source
    assert "async def list_price_facts_for_documents(" in port_source
    assert "async def list_price_documents_for_project(" in repo_source
    assert "async def list_price_facts_for_documents(" in repo_source
    assert "FROM commercial_price_documents" in repo_source
    assert "FROM commercial_price_facts" in repo_source
    assert "price_document_id = ANY($2::text[])" in repo_source


def test_project_commercial_truth_review_service_loads_all_project_price_documents() -> (
    None
):
    service_source = SERVICE.read_text(encoding="utf-8")
    method = _slice_between(
        service_source,
        "    async def project_commercial_truth_review(",
        ("    async def commercial_truth_review(",),
    )
    source_helper = _slice_between(
        service_source,
        "    async def _sources_by_price_document_id(",
        ("def _price_facts_empty_response(",),
    )

    assert "list_price_documents_for_project(" in method
    assert "list_price_facts_for_documents(" in method
    assert "include_non_runtime=True" in method
    assert "_sources_by_price_document_id(" in method
    assert "sources_by_price_document_id" in method

    assert "self._knowledge_document_repo.get_document(" in source_helper
    assert "commercial_source_descriptor_from_price_document(" in source_helper
    assert "CommercialTruthReviewService()" in service_source
    assert "review_price_facts(" in method
    assert "policy=policy" in method


def test_project_commercial_truth_review_route_is_static_and_before_document_route() -> (
    None
):
    http_source = HTTP.read_text(encoding="utf-8")

    project_route = '@router.get("/commercial-truth-review")'
    document_route = '@router.get("/{document_id}/commercial-truth-review")'

    assert project_route in http_source
    assert document_route in http_source
    assert http_source.index(project_route) < http_source.index(document_route)
    assert "service.project_commercial_truth_review(" in http_source


def test_project_commercial_truth_review_does_not_publish_or_touch_runtime_lookup() -> (
    None
):
    service_source = SERVICE.read_text(encoding="utf-8")
    http_source = HTTP.read_text(encoding="utf-8")

    service_method = _slice_between(
        service_source,
        "    async def project_commercial_truth_review(",
        ("    async def commercial_truth_review(",),
    )
    route = _slice_between(
        http_source,
        '@router.get("/commercial-truth-review")',
        ('@router.get("/{document_id}/commercial-truth-review")',),
    )
    combined = service_method + "\n" + route

    assert "publish_price_facts(" not in combined
    assert "reject_price_facts(" not in combined
    assert "list_published_price_facts_for_lookup(" not in combined
    assert "commercial_price_lookup" not in combined
    assert "PriceLookupTool" not in combined
