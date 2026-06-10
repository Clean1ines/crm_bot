from pathlib import Path


def test_source_ingestion_application_sagas_do_not_import_interfaces_or_infrastructure() -> (
    None
):
    saga_paths = tuple(
        sorted(
            Path("src/contexts/knowledge_workbench/application/sagas").glob("*.py"),
        ),
    )
    assert saga_paths

    forbidden_markers = [
        "src.interfaces",
        "src.infrastructure",
        "asyncpg",
        "postgres",
        "Postgres",
        "fastapi",
    ]

    text = "\n".join(path.read_text(encoding="utf-8") for path in saga_paths)
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders, "\n".join(offenders)


def test_source_ingestion_composition_does_not_import_future_runtime_or_later_phases() -> (
    None
):
    path = Path("src/interfaces/composition/source_ingestion_first_phase.py")
    assert path.is_file()

    text = path.read_text(encoding="utf-8")
    forbidden_markers = [
        "capacity_runtime",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "DraftObservationExtraction",
        "PROMPT_A",
        "worker_loop",
        "JobDispatcher",
        "outbox_events",
    ]

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders, "\n".join(offenders)


def test_draft_observation_extraction_planner_does_not_import_runtime_layers() -> None:
    path = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "plan_draft_observation_extraction_work.py",
    )
    assert path.is_file()

    text = path.read_text(encoding="utf-8")
    required_markers = [
        "WorkKind",
        "knowledge_workbench.draft_observation_extraction",
    ]
    forbidden_markers = [
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "execution_runtime.application",
        "execution_runtime.infrastructure",
        "Postgres",
        "asyncpg",
        "queue",
        "worker",
        "lease",
        "PROMPT_A_WORK_SCHEDULED",
    ]

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)


def test_draft_observation_plan_mapper_imports_only_execution_schedule_dto() -> None:
    path = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "map_draft_observation_plans_to_execution_schedule.py",
    )
    assert path.is_file()

    text = path.read_text(encoding="utf-8")
    required_markers = [
        "execution_runtime.application.use_cases.ensure_work_items_scheduled",
        "WorkItemSchedulePlan",
    ]
    forbidden_markers = [
        "EnsureWorkItemsScheduled",
        "WorkItemSchedulingUnitOfWorkPort",
        "execution_runtime.infrastructure",
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "Postgres",
        "asyncpg",
        "queue",
        "worker",
        "lease",
    ]

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)


def test_draft_observation_scheduler_service_imports_only_application_boundaries() -> (
    None
):
    path = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "schedule_draft_observation_extraction_work.py",
    )
    assert path.is_file()

    text = path.read_text(encoding="utf-8")
    required_markers = [
        "execution_runtime.application.use_cases.ensure_work_items_scheduled",
        "execution_runtime.application.ports.work_item_scheduling_unit_of_work_port",
    ]
    forbidden_markers = [
        "execution_runtime.infrastructure",
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "Postgres",
        "asyncpg",
        "queue",
        "worker",
        "lease",
    ]

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)


def test_draft_observation_phase_transition_delegates_to_scheduler_without_runtime_infrastructure() -> (
    None
):
    path = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "advance_to_draft_observation_scheduling_phase.py",
    )
    assert path.is_file()

    text = path.read_text(encoding="utf-8")
    required_markers = [
        "ScheduleDraftObservationExtractionWork",
        "ScheduleDraftObservationExtractionWorkCommand",
        "PROMPT_A_WORK_SCHEDULED",
        "execution_runtime.ensure_work_items_scheduled",
    ]
    forbidden_markers = [
        "EnsureWorkItemsScheduled",
        "WorkItemSchedulingUnitOfWorkPort",
        "WorkItemSchedulePlan",
        "execution_runtime.application",
        "execution_runtime.infrastructure",
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "Postgres",
        "asyncpg",
        "queue",
        "worker",
        "lease",
    ]

    missing = [marker for marker in required_markers if marker not in text]
    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)


def test_saga_checkpoint_replacement_uses_public_helper() -> None:
    helper = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "knowledge_extraction_checkpoints.py",
    )
    assert helper.exists()
    helper_text = helper.read_text(encoding="utf-8")
    assert "def replace_or_append_checkpoint" in helper_text
    assert "KnowledgeExtractionPhaseCheckpoint" in helper_text

    offenders: list[str] = []
    for path in Path("src/contexts/knowledge_workbench/application/sagas").rglob(
        "*.py"
    ):
        text = path.read_text(encoding="utf-8")
        if "import _replace_checkpoints" in text:
            offenders.append(str(path))
        if "import _replace_or_append_checkpoint" in text:
            offenders.append(str(path))
        if "from .knowledge_extraction_saga import _replace" in text:
            offenders.append(str(path))
        if "def _replace_checkpoints" in text:
            offenders.append(str(path))
        if "def _replace_or_append_checkpoint" in text:
            offenders.append(str(path))

    assert offenders == []
