from __future__ import annotations

from pathlib import Path


UOW_PORT_PATH = Path(
    "src/contexts/artifact_runtime/application/ports/artifact_unit_of_work_port.py",
)

PERSISTENCE_USE_CASE_PATHS = (
    Path("src/contexts/artifact_runtime/application/use_cases/persist_artifact.py"),
    Path("src/contexts/artifact_runtime/application/use_cases/validate_artifact.py"),
    Path("src/contexts/artifact_runtime/application/use_cases/reject_artifact.py"),
    Path("src/contexts/artifact_runtime/application/use_cases/supersede_artifact.py"),
    Path("src/contexts/artifact_runtime/application/use_cases/expire_artifact.py"),
)


def test_artifact_unit_of_work_port_methods_are_async() -> None:
    source = UOW_PORT_PATH.read_text(encoding="utf-8")

    required = (
        "async def save_artifact",
        "async def append_event",
        "async def commit",
        "async def rollback",
    )
    for marker in required:
        assert marker in source


def test_artifact_persistence_use_cases_execute_async_and_await_uow() -> None:
    for path in PERSISTENCE_USE_CASE_PATHS:
        source = path.read_text(encoding="utf-8")

        assert "async def execute" in source
        assert "await self._unit_of_work.save_artifact" in source
        assert "await self._unit_of_work.append_event" in source
        assert "await self._unit_of_work.commit" in source
        assert "await self._unit_of_work.rollback" in source


def test_artifact_domain_entity_remains_sync() -> None:
    source = Path(
        "src/contexts/artifact_runtime/domain/entities/pipeline_artifact.py",
    ).read_text(encoding="utf-8")

    assert "async def" not in source


def test_artifact_async_persistence_contract_has_no_provider_or_workbench_leakage() -> (
    None
):
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (UOW_PORT_PATH, *PERSISTENCE_USE_CASE_PATHS)
    )

    forbidden = (
        "knowledge_workbench",
        "Groq",
        "LlmProviderPort",
        "ExecuteLlmTask",
        "ExecuteAndRecordLlmTask",
        "os.environ",
        "GROQ_API_KEY",
        "httpx",
        "requests",
    )
    for marker in forbidden:
        assert marker not in source
