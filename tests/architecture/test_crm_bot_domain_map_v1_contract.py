from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_crm_bot_domain_map_v1_exists_and_names_core_contexts() -> None:
    document = ROOT / "docs/architecture/crm_bot_domain_map_v1.md"

    assert document.exists()

    text = document.read_text(encoding="utf-8")
    required_phrases = (
        "Knowledge Compilation Context",
        "Commercial Catalog / Pricing Context",
        "CRM Operational Context",
        "Evidence / Source Authority Context",
        "Answer Orchestration Context",
        "Action Safety / Approval Context",
        "LLM output is never authoritative evidence",
        "Production retrieval row means grounded canonical semantic answer entry",
    )

    for phrase in required_phrases:
        assert phrase in text


def test_new_domain_contract_modules_are_parseable_and_pure() -> None:
    paths = (
        ROOT / "src/domain/runtime/evidence.py",
        ROOT / "src/domain/runtime/source_authority.py",
        ROOT / "src/domain/commercial/pricing.py",
        ROOT / "src/domain/commercial/price_query.py",
    )
    forbidden_import_prefixes = (
        "fastapi",
        "asyncpg",
        "redis",
        "src.infrastructure",
        "src.interfaces",
        "src.agent",
    )

    for path in paths:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))

        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported_names = (node.module or "",)
            else:
                continue

            for imported_name in imported_names:
                assert not imported_name.startswith(forbidden_import_prefixes), (
                    f"{path} imports forbidden dependency {imported_name}"
                )
