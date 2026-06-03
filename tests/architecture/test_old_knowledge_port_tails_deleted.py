from __future__ import annotations

import ast
import importlib
from pathlib import Path


DELETED_PORT_TAILS = (
    "src/application/ports/knowledge/documents.py",
    "src/application/ports/knowledge/source_material.py",
    "src/application/ports/knowledge/source_import.py",
    "src/application/ports/knowledge/runtime_retrieval.py",
    "src/application/ports/knowledge/artifact_cleanup.py",
)

DELETED_MODULES = (
    "src.application.ports.knowledge.documents",
    "src.application.ports.knowledge." + "source_material",
    "src.application.ports.knowledge." + "source_import",
    "src.application.ports.knowledge.runtime_retrieval",
    "src.application.ports.knowledge." + "artifact_cleanup",
)


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    modules: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)

    return tuple(modules)


def test_old_knowledge_port_tail_files_are_deleted() -> None:
    for rel_path in DELETED_PORT_TAILS:
        assert not Path(rel_path).exists(), f"{rel_path} should be deleted"


def test_deleted_knowledge_port_tail_modules_are_not_importable() -> None:
    for module in DELETED_MODULES:
        assert importlib.util.find_spec(module) is None, f"{module} should be deleted"


def test_production_code_does_not_import_deleted_knowledge_port_tails() -> None:
    for path in Path("src").rglob("*.py"):
        imports = _imports(path)
        for deleted_module in DELETED_MODULES:
            for imported in imports:
                assert imported != deleted_module, f"{path} imports {deleted_module}"
                assert not imported.startswith(deleted_module + "."), (
                    f"{path} imports {imported}"
                )

def test_clean_roots_import_after_old_port_tail_deletion() -> None:
    modules = (
        "src.application.ports.knowledge",
        "src.interfaces.http.knowledge",
        "src.interfaces.composition.fastapi_lifespan",
        "src.infrastructure.queue.job_dispatcher",
        "src.infrastructure.queue.worker_loop",
        "src.infrastructure.db.knowledge_workbench_repository",
        "src.infrastructure.db.workbench_runtime_retrieval_repository",
    )

    for module in modules:
        importlib.import_module(module)
