from __future__ import annotations

from pathlib import Path


BOUNDARY_ROOTS = (Path("src/application"), Path("src/domain"))


def _python_sources() -> list[Path]:
    paths: list[Path] = []
    for root in BOUNDARY_ROOTS:
        paths.extend(
            path for path in root.rglob("*.py") if "__pycache__" not in path.parts
        )
    return sorted(paths)


def test_application_and_domain_do_not_import_asyncpg() -> None:
    offenders: list[str] = []
    forbidden = ("import asyncpg", "from asyncpg", "asyncpg.")

    for path in _python_sources():
        source = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in source:
                offenders.append(f"{path.as_posix()} contains {marker!r}")

    assert offenders == []


def test_application_and_domain_do_not_reference_asyncpg_fk_errors() -> None:
    offenders: list[str] = []

    for path in _python_sources():
        source = path.read_text(encoding="utf-8")
        if "ForeignKeyViolationError" in source:
            offenders.append(path.as_posix())

    assert offenders == []


def test_knowledge_surface_ingestion_does_not_import_infrastructure_llm() -> None:
    source = Path(
        "src/application/services/knowledge_surface_ingestion_service.py"
    ).read_text(encoding="utf-8")

    assert "src.infrastructure.llm" not in source
    assert "knowledge_surface_graph_compiler_v2" not in source
    assert "src.application.services.knowledge_surface_prompt_versions" in source
