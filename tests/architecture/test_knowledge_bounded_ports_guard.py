from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGGREGATE_PORT = ROOT / "src/application/ports/knowledge_port.py"
BOUNDED_PORTS_DIR = ROOT / "src/application/ports/knowledge"


def _protocol_methods(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name
                for item in node.body
                if isinstance(item, ast.AsyncFunctionDef | ast.FunctionDef)
            }
    raise AssertionError(f"{class_name} not found in {path}")


def test_aggregate_knowledge_repository_port_declares_no_methods() -> None:
    methods = _protocol_methods(AGGREGATE_PORT, "KnowledgeRepositoryPort")
    assert methods == set()


def test_bounded_knowledge_ports_exist() -> None:
    expected_files = {
        "__init__.py",
        "documents.py",
        "source_material.py",
        "compilation_trace.py",
        "answer_candidates.py",
        "canonical_entries.py",
        "runtime_retrieval.py",
        "curation.py",
    }
    existing_files = {
        path.name for path in BOUNDED_PORTS_DIR.iterdir() if path.is_file()
    }
    assert expected_files <= existing_files
