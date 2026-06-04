from __future__ import annotations

from pathlib import Path


def test_old_document_parser_port_is_deleted() -> None:
    assert not Path("src/application/ports/knowledge_document_parser_port.py").exists()


def test_current_workbench_port_file_is_the_current_knowledge_boundary() -> None:
    source = Path("src/application/ports/knowledge_workbench.py").read_text(
        encoding="utf-8"
    )

    assert "Protocol" in source
    assert "DocumentSection" in source
    assert "RegistrySnapshot" in source
    assert "ProcessingRun" in source


def test_knowledge_ports_do_not_reference_old_parser_domain() -> None:
    offenders: list[str] = []
    forbidden = (
        "ParsedKnowledgeDocument",
        "KnowledgeDocumentParserPort",
        "knowledge_document_structure",
        "knowledge_chunks",
    )

    for path in Path("src/application/ports").rglob("*.py"):
        source = path.read_text(encoding="utf-8", errors="ignore")
        for marker in forbidden:
            if marker in source:
                offenders.append(f"{path}: {marker}")

    assert offenders == []
