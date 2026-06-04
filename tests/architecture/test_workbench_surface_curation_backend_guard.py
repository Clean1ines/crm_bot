from pathlib import Path


HTTP_PATH = Path("src/interfaces/http/knowledge.py")
REPOSITORY_PATH = Path("src/infrastructure/db/workbench_surface_curation_repository.py")
COMMAND_PATH = Path("src/application/workbench_commands/surface_curation.py")


def test_surface_curation_backend_mutations_are_exposed_without_retired_endpoint_revival() -> (
    None
):
    http_source = HTTP_PATH.read_text()

    for marker in (
        "approve_knowledge_surface",
        "reject_knowledge_surface",
        "edit_knowledge_surface",
        "merge_knowledge_facts",
        "delete_knowledge_fact",
        "publish_selected_workbench_surfaces",
    ):
        assert marker in http_source

    assert "KnowledgeWorkbenchRepository(connection)" not in http_source
    assert "retry_knowledge_failed_batches" in http_source
    assert "retighten_knowledge_document" in http_source


def test_surface_curation_repository_uses_typed_connection_protocol() -> None:
    source = REPOSITORY_PATH.read_text()

    assert "class WorkbenchSurfaceCurationConnection(Protocol):" in source
    assert "def fetchrow(" in source
    assert "def execute(" in source
    assert "def transaction(" in source
    assert "self._connection: object" not in source
    assert "type: ignore" not in source


def test_surface_curation_application_command_has_no_forbidden_typing_debt() -> None:
    source = COMMAND_PATH.read_text()
    forbidden_any_name = chr(65) + chr(110) + chr(121)
    forbidden_ignore_marker = "type:" + " ignore"
    assert forbidden_any_name not in source
    assert forbidden_ignore_marker not in source
