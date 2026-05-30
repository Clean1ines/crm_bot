from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAIN_MODULE = ROOT / "src/domain/project_plane/production_retrieval.py"


def test_production_retrieval_domain_module_has_no_infra_or_application_imports() -> (
    None
):
    source = DOMAIN_MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_prefixes = (
        "src.application",
        "src.infrastructure",
        "src.interfaces",
        "src.agent",
        "asyncpg",
        "fastapi",
        "groq",
        "sqlalchemy",
    )

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)

    for module in imported_modules:
        assert not module.startswith(forbidden_prefixes), module


def test_production_retrieval_domain_policy_documents_runtime_equivalence() -> None:
    source = DOMAIN_MODULE.read_text(encoding="utf-8")

    assert "knowledge_retrieval_surface" in source
    assert "diagnostic-only" in source
    assert "not runtime-equivalent" in source
