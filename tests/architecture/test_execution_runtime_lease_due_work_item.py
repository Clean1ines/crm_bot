from pathlib import Path


def test_lease_due_work_item_required_markers_exist() -> None:
    files = (
        Path(
            "src/contexts/execution_runtime/application/use_cases/"
            "lease_due_work_item.py",
        ),
        Path(
            "src/contexts/execution_runtime/application/ports/"
            "work_item_lease_repository_port.py",
        ),
        Path(
            "src/contexts/execution_runtime/infrastructure/postgres/"
            "postgres_work_item_lease_repository.py",
        ),
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in files)

    required = (
        "LeaseDueWorkItem",
        "WorkItemLeaseRepositoryPort",
        "LeasedWorkItemRecord",
        "PostgresWorkItemLeaseRepository",
        "FOR UPDATE SKIP LOCKED",
        "WorkItemStateMachine.lease_ready",
        "execution_work_items",
        "execution_work_item_schedules",
    )
    for marker in required:
        assert marker in source


def test_lease_due_work_item_application_has_no_infra_or_context_imports() -> None:
    roots = (
        Path(
            "src/contexts/execution_runtime/application/use_cases/lease_due_work_item.py"
        ),
        Path(
            "src/contexts/execution_runtime/application/ports/"
            "work_item_lease_repository_port.py",
        ),
    )
    forbidden = (
        "knowledge_workbench",
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "Groq",
        "qwen",
        "Prompt",
        "DraftObservation",
        "source_unit",
        "postgres",
        "asyncpg",
        "psycopg",
        "SyncConnection",
        "asyncio.run",
        "run_until_complete",
    )

    offenders: list[str] = []
    for path in roots:
        source = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in source:
                offenders.append(f"{path}: {marker}")

    assert offenders == []


def test_postgres_lease_repository_has_no_foreign_runtime_imports_or_transaction_control() -> (
    None
):
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_lease_repository.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "knowledge_workbench",
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "Groq",
        "qwen",
        "Prompt",
        "DraftObservation",
        "source_unit",
        "psycopg",
        "SyncConnection",
        "asyncio.run",
        "run_until_complete",
        "commit(",
        "rollback(",
    )
    for marker in forbidden:
        assert marker not in source
