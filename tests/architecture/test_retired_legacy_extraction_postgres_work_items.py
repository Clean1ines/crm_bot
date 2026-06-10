from pathlib import Path


def test_retired_legacy_workbench_extraction_work_item_path_is_absent() -> None:
    roots = (
        Path("src"),
        Path("tests"),
    )
    forbidden_markers = (
        "postgres_claim_extraction_work_item_unit_of_work",
        "postgres_claim_extraction_stage_work_item_index",
        "claim_extraction_stage_composition",
        "PostgresClaimExtractionWorkItemUnitOfWork",
        "PostgresClaimExtractionStageWorkItemIndex",
        "ClaimExtractionStageRuntime",
        "ClaimExtractionStageWorkItemIndex",
        "ClaimExtractionWorkItemUnitOfWork",
        "RunClaimExtractionStageAsync",
    )

    offenders: list[str] = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if path == Path(__file__):
                continue
            text = path.read_text(encoding="utf-8")
            for marker in forbidden_markers:
                if marker in text:
                    offenders.append(f"{path}: {marker}")

    assert offenders == []


def test_canonical_scheduling_markers_exist() -> None:
    required = {
        "EnsureWorkItemsScheduled": Path(
            "src/contexts/execution_runtime/application/use_cases/"
            "ensure_work_items_scheduled.py",
        ),
        "WorkItemSchedulingUnitOfWorkPort": Path(
            "src/contexts/execution_runtime/application/ports/"
            "work_item_scheduling_unit_of_work_port.py",
        ),
        "PostgresWorkItemSchedulingUnitOfWork": Path(
            "src/contexts/execution_runtime/infrastructure/postgres/"
            "postgres_work_item_scheduling_unit_of_work.py",
        ),
        "ScheduleDraftObservationExtractionWork": Path(
            "src/contexts/knowledge_workbench/application/sagas/"
            "schedule_draft_observation_extraction_work.py",
        ),
    }

    for marker, path in required.items():
        assert path.is_file(), str(path)
        assert marker in path.read_text(encoding="utf-8")
