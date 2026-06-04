from pathlib import Path


WORKER_HANDLER = Path(
    "src/infrastructure/queue/handlers/workbench_parallel_processing.py"
)
REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")


def test_default_claim_observations_runner_requires_fact_registry_and_snapshot() -> (
    None
):
    source = WORKER_HANDLER.read_text()

    assert "get_fact_registry_for_run" in source
    assert "claim observations runner requires fact registry" in source
    assert "get_latest_registry_snapshot" in source
    assert "claim observations runner requires latest registry snapshot" in source


def test_repository_has_real_fact_registry_reader_sql_for_prompt_a_runner() -> None:
    source = REPOSITORY.read_text()

    assert "async def get_fact_registry_for_run(" in source
    start = source.index("async def get_fact_registry_for_run(")
    end = source.index("async def get_processing_run(", start)
    method = source[start:end]

    assert "FROM knowledge_workbench_fact_registries" in method
    assert "registry_id" in method
    assert "fact_registry_id" not in method
    assert "FactRegistry(" in method
