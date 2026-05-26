from pathlib import Path


def test_repository_has_surface_run_and_stage_methods() -> None:
    source = Path("src/infrastructure/db/repositories/knowledge_repository.py").read_text(
        encoding="utf-8"
    )

    assert "async def create_surface_compiler_run(" in source
    assert "INSERT INTO knowledge_surface_compiler_runs" in source
    assert "async def update_surface_compiler_run_status(" in source
    assert "UPDATE knowledge_surface_compiler_runs" in source
    assert "async def create_surface_compiler_stage(" in source
    assert "INSERT INTO knowledge_surface_compiler_stages" in source
