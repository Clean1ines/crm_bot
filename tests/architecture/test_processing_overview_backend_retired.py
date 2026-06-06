from pathlib import Path


ROOTS = (
    Path("src"),
    Path("tests"),
)


def _source_files():
    for root in ROOTS:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ts", ".tsx"}:
                if "__pycache__" not in path.parts:
                    yield path


def test_processing_overview_backend_route_and_service_are_retired() -> None:
    assert not Path(
        "src/interfaces/composition/faq_workbench_processing_overview.py"
    ).exists()
    assert not Path(
        "src/application/workbench_observability/processing_overview.py"
    ).exists()

    knowledge_http = Path("src/interfaces/http/knowledge.py").read_text(
        encoding="utf-8"
    )
    repository = Path(
        "src/infrastructure/db/workbench_observability_repository.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        '"/processing-overview"',
        "knowledge_processing_overview",
        "fetch_workbench_processing_overview",
        "list_processing_overview_documents",
        "list_processing_overview_node_runs",
    )

    for marker in forbidden:
        assert marker not in knowledge_http
        assert marker not in repository


def test_processing_overview_is_not_imported_from_production_or_tests() -> None:
    allowed_files = {
        Path("tests/architecture/test_processing_overview_backend_retired.py"),
        Path(
            "tests/architecture/test_workbench_processing_overview_retired_from_frontend.py"
        ),
        Path("tests/architecture/test_workbench_card_single_source_guard.py"),
        Path("tests/architecture/test_legacy_production_edges_cut.py"),
    }

    forbidden = (
        "processing_overview",
        "processing-overview",
        "processingOverview",
        "ProcessingOverview",
        "KnowledgeProcessingOverview",
        "list_processing_overview",
        "fetch_workbench_processing_overview",
    )

    offenders: list[str] = []
    for path in _source_files():
        if path in allowed_files:
            continue
        source = path.read_text(encoding="utf-8")
        for marker in forbidden:
            if marker in source:
                offenders.append(f"{path}: {marker}")

    assert offenders == []
