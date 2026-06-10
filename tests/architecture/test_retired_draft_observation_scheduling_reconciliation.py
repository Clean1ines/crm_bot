from pathlib import Path


THIS_FILE = Path(__file__).name


def _python_files_under(*roots: str) -> list[Path]:
    paths: list[Path] = []
    for root in roots:
        paths.extend(Path(root).rglob("*.py"))
    return paths


def test_legacy_draft_observation_scheduling_reconciliation_is_retired() -> None:
    forbidden = (
        "DraftObservationExtractionSchedulingReconciler",
        "DraftObservationExtractionSchedulingDecision",
        "DraftObservationExtractionSchedulingStatus",
        "DraftObservationExtractionWorkIndexPort",
        "knowledge_extraction_draft_observation_scheduling_reconciliation",
    )

    offenders: list[str] = []
    for path in _python_files_under("src", "tests"):
        if path.name == THIS_FILE:
            continue

        text = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in text:
                offenders.append(f"{path}:{marker}")

    assert offenders == []


def test_canonical_draft_observation_scheduling_path_is_preserved() -> None:
    expected_files = (
        Path(
            "src/contexts/knowledge_workbench/application/sagas/"
            "plan_draft_observation_extraction_work.py",
        ),
        Path(
            "src/contexts/knowledge_workbench/application/sagas/"
            "map_draft_observation_plans_to_execution_schedule.py",
        ),
        Path(
            "src/contexts/knowledge_workbench/application/sagas/"
            "schedule_draft_observation_extraction_work.py",
        ),
        Path(
            "src/contexts/knowledge_workbench/application/sagas/"
            "advance_to_draft_observation_scheduling_phase.py",
        ),
        Path(
            "src/contexts/execution_runtime/application/use_cases/"
            "ensure_work_items_scheduled.py",
        ),
    )

    missing_files = [str(path) for path in expected_files if not path.is_file()]
    assert missing_files == []

    canonical_markers = (
        "PlanDraftObservationExtractionWork",
        "MapDraftObservationPlansToExecutionSchedule",
        "ScheduleDraftObservationExtractionWork",
        "AdvanceToDraftObservationSchedulingPhase",
        "EnsureWorkItemsScheduled",
        "WorkItemSchedulePlan",
        "idempotency_key",
        "payload_hash",
        "PROMPT_A_WORK_SCHEDULED",
    )

    canonical_paths = _python_files_under(
        "src/contexts/knowledge_workbench/application/sagas",
        "src/contexts/execution_runtime/application",
    )

    missing_markers: list[str] = []
    for marker in canonical_markers:
        if not any(
            marker in path.read_text(encoding="utf-8") for path in canonical_paths
        ):
            missing_markers.append(marker)

    assert missing_markers == []


def test_retired_patch_does_not_add_capacity_llm_or_artifact_runtime_imports() -> None:
    changed_source_paths = (
        Path("src/contexts/knowledge_workbench/application/sagas/__init__.py"),
        Path(
            "src/contexts/knowledge_workbench/application/sagas/"
            "knowledge_extraction_saga_ports.py",
        ),
        Path(
            "src/contexts/knowledge_workbench/application/sagas/"
            "advance_to_draft_observation_scheduling_phase.py",
        ),
    )
    forbidden_import_fragments = (
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
    )

    offenders: list[str] = []
    for path in changed_source_paths:
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_import_fragments:
            if marker in text:
                offenders.append(f"{path}:{marker}")

    assert offenders == []
