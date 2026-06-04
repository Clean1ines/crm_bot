from pathlib import Path


FRESH_UPLOAD_SERVICE = Path(
    "src/application/services/faq_workbench_fresh_upload_service.py"
)
REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")
PORT = Path("src/application/ports/knowledge_workbench.py")


def test_fresh_upload_creates_fact_registry_before_initial_registry_snapshot() -> None:
    source = FRESH_UPLOAD_SERVICE.read_text()

    create_registry_index = source.index("create_fact_registry(registry)")
    create_snapshot_index = source.index("create_registry_snapshot(initial_snapshot)")

    assert create_registry_index < create_snapshot_index


def test_repository_implements_fact_registry_parent_insert_for_snapshot_fk() -> None:
    source = REPOSITORY.read_text()

    assert "async def create_fact_registry(" in source
    assert "INSERT INTO knowledge_workbench_fact_registries" in source
    assert "registry_id," in source
    assert "ON CONFLICT (registry_id) DO UPDATE SET" in source
    assert (
        "fact_registry_id"
        not in source[
            source.index("async def create_fact_registry(") : source.index(
                "async def create_document("
            )
        ]
    )


def test_fresh_upload_port_requires_fact_registry_creation() -> None:
    source = PORT.read_text()

    assert (
        "async def create_fact_registry(self, registry: FactRegistry) -> None" in source
    )
