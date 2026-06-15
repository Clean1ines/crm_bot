from pathlib import Path


def test_execution_runtime_does_not_import_workbench_capacity_llm_or_artifact() -> None:
    root = Path("src/contexts/execution_runtime")
    assert root.is_dir()

    forbidden_markers = (
        "knowledge_workbench",
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "Groq",
        "qwen",
        "DraftObservation",
        "source_unit",
        "Prompt",
    )

    offenders: list[str] = []
    allowed_capacity_admission_boundary = Path(
        "src/contexts/execution_runtime/application/use_cases/"
        "lease_admitted_work_items.py",
    )

    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            if (
                path == allowed_capacity_admission_boundary
                and marker == "capacity_runtime"
            ):
                continue
            if marker in text:
                offenders.append(f"{path}: {marker}")

    assert offenders == []


def test_no_sync_db_workaround_in_scheduling_application_slice() -> None:
    roots = (
        Path("src/contexts/execution_runtime/application"),
        Path("src/contexts/knowledge_workbench/application/sagas"),
    )
    forbidden_markers = (
        "SyncConnection",
        "sync connection",
        "psycopg",
        "run_until_complete",
        "asyncio.run",
    )

    offenders: list[str] = []
    for root in roots:
        assert root.is_dir()
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for marker in forbidden_markers:
                if marker in text:
                    offenders.append(f"{path}: {marker}")

    assert offenders == []


def test_scheduling_repository_port_and_use_case_are_async_without_transaction_ownership() -> (
    None
):
    port = Path(
        "src/contexts/execution_runtime/application/ports/"
        "work_item_scheduling_repository_port.py",
    ).read_text(encoding="utf-8")
    use_case = Path(
        "src/contexts/execution_runtime/application/use_cases/"
        "ensure_work_items_scheduled.py",
    ).read_text(encoding="utf-8")

    required_markers = (
        "class WorkItemSchedulingRepositoryPort",
        "async def get_work_item",
        "async def get_schedule_payload_hash",
        "async def save_scheduled_work_item",
        "async def execute",
        "await self.repository.get_work_item",
        "await self.repository.save_scheduled_work_item",
    )

    forbidden_markers = (
        "WorkItemSchedulingUnitOfWorkPort",
        "async def commit",
        "async def rollback",
        ".commit(",
        ".rollback(",
        "self.unit_of_work",
    )

    for marker in required_markers:
        assert marker in port + use_case

    for marker in forbidden_markers:
        assert marker not in port + use_case


def test_postgres_work_item_scheduling_uow_does_not_silently_ignore_conflicts() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_scheduling_repository.py",
    ).read_text(encoding="utf-8")

    assert "ON CONFLICT" not in source
    assert "DO NOTHING" not in source


def test_execution_scheduling_repository_has_no_transaction_methods() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_scheduling_repository.py",
    ).read_text(encoding="utf-8")
    use_case = Path(
        "src/contexts/execution_runtime/application/use_cases/"
        "ensure_work_items_scheduled.py",
    ).read_text(encoding="utf-8")

    assert "async def commit" not in source
    assert "async def rollback" not in source
    assert "transaction()" not in source
    assert ".commit(" not in use_case
    assert ".rollback(" not in use_case
