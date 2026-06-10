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
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
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


def test_scheduling_port_and_use_case_are_async() -> None:
    port = Path(
        "src/contexts/execution_runtime/application/ports/"
        "work_item_scheduling_unit_of_work_port.py",
    ).read_text(encoding="utf-8")
    use_case = Path(
        "src/contexts/execution_runtime/application/use_cases/"
        "ensure_work_items_scheduled.py",
    ).read_text(encoding="utf-8")

    required_markers = (
        "async def get_work_item",
        "async def get_schedule_payload_hash",
        "async def save_scheduled_work_item",
        "async def commit",
        "async def rollback",
        "async def execute",
        "await self.unit_of_work.get_work_item",
        "await self.unit_of_work.save_scheduled_work_item",
        "await self.unit_of_work.commit",
        "await self.unit_of_work.rollback",
    )

    for marker in required_markers:
        assert marker in port + use_case
