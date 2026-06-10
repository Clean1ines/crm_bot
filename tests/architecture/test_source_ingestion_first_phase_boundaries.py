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
