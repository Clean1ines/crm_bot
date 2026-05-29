from __future__ import annotations

from fastapi.routing import APIRoute

from src.interfaces.http.knowledge import router


def test_delete_knowledge_document_route_is_registered() -> None:
    routes = [
        route
        for route in router.routes
        if isinstance(route, APIRoute)
        and "DELETE" in route.methods
        and route.endpoint.__name__ == "delete_knowledge_document"
    ]

    assert routes
    assert routes[0].path.endswith("/knowledge/{document_id}")
