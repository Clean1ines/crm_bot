from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PORT_FILE = ROOT / "src/application/ports/commercial_price.py"


def _tree() -> ast.Module:
    return ast.parse(PORT_FILE.read_text(encoding="utf-8"))


def test_commercial_price_ports_do_not_import_infrastructure_or_interfaces() -> None:
    forbidden_prefixes = (
        "asyncpg",
        "fastapi",
        "src.agent",
        "src.infrastructure",
        "src.interfaces",
    )

    violations: list[str] = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if any(
                module == prefix or module.startswith(f"{prefix}.")
                for prefix in forbidden_prefixes
            ):
                violations.append(module)

        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if any(
                    name == prefix or name.startswith(f"{prefix}.")
                    for prefix in forbidden_prefixes
                ):
                    violations.append(name)

    assert violations == []


def test_commercial_price_ports_expose_bounded_protocols_only() -> None:
    class_names = {node.name for node in _tree().body if isinstance(node, ast.ClassDef)}

    assert class_names == {
        "CommercialPriceDocumentPort",
        "CommercialPriceSourceMaterialPort",
        "CommercialPriceFactPort",
        "CommercialPriceLookupPort",
        "CommercialPriceKnowledgePort",
    }


def test_commercial_price_aggregate_port_declares_no_methods() -> None:
    aggregate = next(
        node
        for node in _tree().body
        if isinstance(node, ast.ClassDef)
        and node.name == "CommercialPriceKnowledgePort"
    )

    methods = {
        node.name
        for node in aggregate.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }

    assert methods == set()
