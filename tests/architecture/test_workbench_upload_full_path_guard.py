from pathlib import Path


UPLOAD_COMPOSITION = Path("src/interfaces/composition/faq_workbench_upload.py")
UPLOAD_SERVICE = Path("src/application/workbench/upload_service.py")
QUEUE_ADAPTER = Path("src/infrastructure/queue/workbench_parallel_queue.py")
FRESH_UPLOAD_SERVICE = Path(
    "src/application/services/faq_workbench_fresh_upload_service.py"
)
REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")


def test_upload_composition_wires_parallel_queue_adapter_to_pool_not_queue_repo() -> (
    None
):
    source = UPLOAD_COMPOSITION.read_text()

    assert "WorkbenchParallelQueueAdapter(" in source
    start = source.index("WorkbenchParallelQueueAdapter(")
    end = source.index("id_factory=UuidIdFactory()", start)
    adapter_block = source[start:end]

    assert "connection=cast(WorkbenchParallelQueueConnection, pool)" in adapter_block
    assert (
        "connection=cast(WorkbenchParallelQueueConnection, queue_repo)"
        not in adapter_block
    )


def test_parallel_queue_adapter_contract_requires_execute_connection() -> None:
    source = QUEUE_ADAPTER.read_text()

    assert "class WorkbenchParallelQueueConnection(Protocol):" in source
    assert "def execute(self, query: str, *args: object)" in source
    assert "await self.connection.execute(" in source


def test_upload_service_enqueues_after_fresh_upload_result() -> None:
    source = UPLOAD_SERVICE.read_text()

    fresh_index = source.index("start_fresh_upload(")
    enqueue_index = source.index("enqueue_process_workbench_document(queue_payload)")

    assert fresh_index < enqueue_index


def test_fresh_upload_parent_registry_is_written_before_registry_snapshot() -> None:
    source = FRESH_UPLOAD_SERVICE.read_text()

    registry_index = source.index("create_fact_registry(registry)")
    snapshot_index = source.index("create_registry_snapshot(initial_snapshot)")

    assert registry_index < snapshot_index


def test_repository_contains_fact_registry_parent_insert_and_snapshot_child_insert() -> (
    None
):
    source = REPOSITORY.read_text()

    assert "async def create_fact_registry(" in source
    assert "INSERT INTO knowledge_workbench_fact_registries" in source
    assert "registry_id," in source
    assert "async def create_registry_snapshot(" in source
    assert "INSERT INTO knowledge_workbench_registry_snapshots" in source
    assert (
        "registry_id," in source[source.index("async def create_registry_snapshot(") :]
    )
