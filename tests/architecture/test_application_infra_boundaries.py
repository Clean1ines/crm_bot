from __future__ import annotations

from pathlib import Path


def _python_sources(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*.py") if "__pycache__" not in path.parts
    )


def _forbidden_asyncpg_markers(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    return [
        marker
        for marker in ("import asyncpg", "from asyncpg", "asyncpg.")
        if marker in source
    ]


def test_application_layer_has_no_asyncpg_driver_dependency() -> None:
    offenders: list[str] = []

    for path in _python_sources(Path("src/application")):
        for marker in _forbidden_asyncpg_markers(path):
            offenders.append(f"{path.as_posix()} contains {marker!r}")

    assert offenders == []


def test_domain_layer_has_no_asyncpg_driver_dependency() -> None:
    offenders: list[str] = []

    for path in _python_sources(Path("src/domain")):
        for marker in _forbidden_asyncpg_markers(path):
            offenders.append(f"{path.as_posix()} contains {marker!r}")

    assert offenders == []


def test_knowledge_ingestion_service_is_deleted_with_old_compiler_layer() -> None:
    assert not Path("src/application/services/knowledge_ingestion_service.py").exists()
    assert not Path(
        "src/application/services/knowledge_ingestion_contracts.py"
    ).exists()
