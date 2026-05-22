from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "src/application/services/commercial_truth_review_service.py"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
    return imports


def test_commercial_truth_review_service_has_no_infrastructure_or_interface_imports() -> (
    None
):
    forbidden_prefixes = (
        "asyncpg",
        "fastapi",
        "src.infrastructure",
        "src.interfaces",
        "src.agent",
    )
    violations: list[str] = []

    for module in _imports(SERVICE):
        if any(
            module == prefix or module.startswith(f"{prefix}.")
            for prefix in forbidden_prefixes
        ):
            violations.append(module)

    assert violations == []


def test_commercial_truth_review_service_uses_domain_truth_layer() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "detect_commercial_fact_conflicts" in source
    assert "resolve_commercial_conflict_by_policy" in source
    assert "commercial_retrieval_surface_facts" in source
    assert "PublishedPriceFact" in source


def test_commercial_truth_review_service_does_not_persist_or_publish() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "CommercialPriceRepository" not in source
    assert "publish_price_facts" not in source
    assert "reject_price_facts" not in source
    assert "replace_price_facts_for_document" not in source
