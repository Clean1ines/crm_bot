import sys
import types

from src.infrastructure.db.repositories.project import ProjectRepository
from src.interfaces.composition import fastapi_lifespan


def test_build_orchestrator_wires_project_repository_facade(monkeypatch):
    captured = {}

    fake_graph_module = types.ModuleType("src.agent.graph")
    fake_graph_module.create_agent = object()
    monkeypatch.setitem(sys.modules, "src.agent.graph", fake_graph_module)

    class StubConversationOrchestrator:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        fastapi_lifespan,
        "ConversationOrchestrator",
        StubConversationOrchestrator,
    )

    fake_pool = object()

    fastapi_lifespan.build_orchestrator(fake_pool)

    project_repo = captured["project_repo"]

    assert isinstance(project_repo, ProjectRepository)
    assert hasattr(project_repo, "get_project_configuration_view")
