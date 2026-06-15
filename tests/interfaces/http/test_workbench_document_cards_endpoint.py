from __future__ import annotations

import importlib
from pathlib import Path


def test_workbench_document_cards_endpoint_does_not_import_deleted_composition() -> (
    None
):
    source = Path("src/interfaces/http/app.py").read_text(encoding="utf-8")

    assert "faq_workbench_document_cards" not in source
    assert "src.interfaces.composition.faq_workbench_document_cards" not in source
    assert not Path(
        "src/interfaces/composition/faq_workbench_document_cards.py",
    ).exists()


def test_application_imports_without_deleted_document_cards_composition() -> None:
    module = importlib.import_module("src.interfaces.http.app")

    assert module.app is not None


def test_project_knowledge_get_route_is_registered_by_active_router() -> None:
    module = importlib.import_module("src.interfaces.http.app")

    routes = [
        route
        for route in module.app.routes
        if getattr(route, "path", "") == "/api/projects/{project_id}/knowledge"
        and "GET" in getattr(route, "methods", set())
    ]

    assert routes, "GET /api/projects/{project_id}/knowledge route is not registered"
