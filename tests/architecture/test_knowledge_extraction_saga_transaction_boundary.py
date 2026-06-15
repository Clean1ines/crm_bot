from pathlib import Path


def test_saga_reconcile_uses_single_unit_of_work_boundary() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_saga.py",
    ).read_text(encoding="utf-8")

    assert "unit_of_work: KnowledgeExtractionSagaReconcileUnitOfWorkPort" in source
    assert "self._unit_of_work = unit_of_work" in source
    assert "await self._unit_of_work.commit()" in source
    assert "await self._unit_of_work.rollback()" in source
    assert "state_repository:" not in source
    assert "source_management_repository:" not in source
    assert "draft_observation_scheduling_phase:" not in source


def test_scheduling_repository_not_unit_of_work() -> None:
    assert not Path(
        "src/contexts/execution_runtime/application/ports/"
        "work_item_scheduling_unit_of_work_port.py",
    ).exists()
    assert Path(
        "src/contexts/execution_runtime/application/ports/"
        "work_item_scheduling_repository_port.py",
    ).exists()

    use_case = Path(
        "src/contexts/execution_runtime/application/use_cases/"
        "ensure_work_items_scheduled.py",
    ).read_text(encoding="utf-8")
    repository = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_scheduling_repository.py",
    ).read_text(encoding="utf-8")

    assert "WorkItemSchedulingRepositoryPort" in use_case
    assert "WorkItemSchedulingUnitOfWorkPort" not in use_case
    assert ".commit(" not in use_case
    assert ".rollback(" not in use_case
    assert "async def commit" not in repository
    assert "async def rollback" not in repository
    assert "transaction()" not in repository


def test_postgres_reconcile_uow_owns_transaction_and_repositories_share_connection() -> (
    None
):
    source = Path(
        "src/contexts/knowledge_workbench/infrastructure/postgres/"
        "postgres_knowledge_extraction_saga_reconcile_unit_of_work.py",
    ).read_text(encoding="utf-8")

    assert "_transaction = connection.transaction()" in source
    assert "PostgresKnowledgeExtractionSagaStateRepository" in source
    assert "PostgresSourceManagementRepository" in source
    assert "PostgresWorkItemSchedulingRepository" in source
    assert "owns_transaction" not in source


def test_no_forbidden_transaction_boundary_workarounds() -> None:
    roots = (
        Path("src/contexts/execution_runtime"),
        Path("src/contexts/knowledge_workbench/application/sagas"),
        Path("src/contexts/knowledge_workbench/infrastructure/postgres"),
        Path("src/interfaces/composition/knowledge_extraction_saga_reconcile.py"),
    )
    forbidden = (
        "owns_transaction",
        "SyncConnection",
        "psycopg",
        "asyncio.run",
        "run_until_complete",
        "DraftObservationExtractionSchedulingReconciler",
        "PostgresClaimExtractionWorkItemUnitOfWork",
        "ClaimExtractionStageRuntime",
    )

    offenders: list[str] = []
    for root in roots:
        paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in paths:
            if path == Path(__file__):
                continue
            source = path.read_text(encoding="utf-8")
            for marker in forbidden:
                if marker in source:
                    offenders.append(f"{path}: {marker}")

    assert offenders == []
