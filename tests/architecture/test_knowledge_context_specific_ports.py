from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_PORT = ROOT / "src/application/ports/knowledge_port.py"
PORT_DIR = ROOT / "src/application/ports/knowledge"

SERVICE_PORT_EXPECTATIONS = {
    "src/application/services/knowledge_structured_ingestion_service.py": (
        "KnowledgeStructuredIngestionRepositoryFactoryPort",
        "KnowledgeIngestionRepositoryFactoryPort",
    ),
    "src/application/services/knowledge_failed_batch_retry_service.py": (
        "KnowledgeFailedBatchRetryRepositoryFactoryPort",
        "KnowledgeIngestionRepositoryFactoryPort",
    ),
    "src/application/services/knowledge_ready_answer_publication_service.py": (
        "KnowledgeReadyAnswerPublicationRepositoryFactoryPort",
        "KnowledgeIngestionRepositoryFactoryPort",
    ),
    "src/application/services/knowledge_retighten_service.py": (
        "KnowledgeRetightenRepositoryFactoryPort",
        "KnowledgeIngestionRepositoryFactoryPort",
    ),
}


def _protocol_methods(path: Path, class_name: str) -> tuple[str, ...]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return tuple(
                item.name
                for item in node.body
                if isinstance(item, ast.AsyncFunctionDef | ast.FunctionDef)
            )

    raise AssertionError(f"{class_name} not found in {path}")


def test_context_specific_knowledge_port_modules_exist() -> None:
    expected = {
        "source_import.py",
        "structured_ingestion.py",
        "failed_batch_retry.py",
        "ready_answer_publication.py",
        "retighten.py",
        "artifact_cleanup.py",
    }

    existing = {path.name for path in PORT_DIR.glob("*.py")}
    assert expected <= existing


def test_services_use_context_specific_repository_factories() -> None:
    for relative_path, (expected, forbidden) in SERVICE_PORT_EXPECTATIONS.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")

        assert expected in source
        assert forbidden not in source


def test_knowledge_repository_port_remains_temporary_aggregate_without_methods() -> (
    None
):
    source = KNOWLEDGE_PORT.read_text(encoding="utf-8")

    assert "Temporary aggregate compatibility port" in source
    assert "Do not add knowledge-domain methods here" in source
    assert _protocol_methods(KNOWLEDGE_PORT, "KnowledgeRepositoryPort") == ()


def test_stage_e_publication_helper_uses_minimal_publication_port() -> None:
    source = (
        ROOT / "src/application/services/knowledge_ingestion_service.py"
    ).read_text(encoding="utf-8")

    assert "KnowledgeStageEPublicationPort" in source
    assert "repo: KnowledgeStageEPublicationPort" in source


def test_context_specific_ports_compose_bounded_ports_not_services() -> None:
    for name in (
        "source_import.py",
        "structured_ingestion.py",
        "failed_batch_retry.py",
        "ready_answer_publication.py",
        "retighten.py",
        "artifact_cleanup.py",
    ):
        source = (PORT_DIR / name).read_text(encoding="utf-8")

        assert "from src.application.services" not in source
        assert "Protocol" in source
