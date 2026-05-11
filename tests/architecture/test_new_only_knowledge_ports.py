from __future__ import annotations

from pathlib import Path


def test_new_only_knowledge_ports_do_not_expose_old_chunk_contract() -> None:
    files = (
        Path("src/application/ports/knowledge_document_parser_port.py"),
        Path("src/domain/project_plane/knowledge_document_structure.py"),
    )

    forbidden_markers = (
        "JsonObject",
        "json_value_from_unknown",
        "entry_type",
        "plain_enriched",
        "list[str |",
        "to_legacy",
        "from_legacy",
        "from_mapping",
        "chunk_from_mapping",
        "chunk_from_text",
        "add_knowledge_batch",
        "add_structured_knowledge_batch",
    )

    for file_path in files:
        source = file_path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in source, f"{file_path} contains forbidden {marker!r}"


def test_new_only_ports_depend_on_domain_not_infrastructure_or_interfaces() -> None:
    files = (Path("src/application/ports/knowledge_document_parser_port.py"),)

    forbidden_imports = (
        "src.infrastructure",
        "src.interfaces",
        "asyncpg",
        "fastapi",
        "httpx",
        "groq",
    )

    for file_path in files:
        source = file_path.read_text(encoding="utf-8")
        for marker in forbidden_imports:
            assert marker not in source, f"{file_path} contains forbidden {marker!r}"
