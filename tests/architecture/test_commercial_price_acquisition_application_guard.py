from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PORT_FILE = ROOT / "src/application/ports/commercial_price_acquisition.py"
SERVICE_FILE = ROOT / "src/application/services/commercial_price_acquisition_service.py"
PREPARATION_FILE = (
    ROOT
    / "src/application/services/commercial_price_acquisition_preparation_service.py"
)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
    return imports


def test_price_acquisition_application_layer_has_no_infrastructure_imports() -> None:
    forbidden_prefixes = (
        "asyncpg",
        "fastapi",
        "src.agent",
        "src.infrastructure",
        "src.interfaces",
    )
    violations: list[str] = []

    for path in (PORT_FILE, SERVICE_FILE, PREPARATION_FILE):
        for module in _imports(path):
            if any(
                module == prefix or module.startswith(f"{prefix}.")
                for prefix in forbidden_prefixes
            ):
                violations.append(f"{path.relative_to(ROOT)}:{module}")

    assert violations == []


def test_price_acquisition_ports_define_adapter_boundary() -> None:
    source = PORT_FILE.read_text(encoding="utf-8")

    assert "CommercialPriceAcquisitionAdapterPort" in source
    assert "CommercialPriceAcquisitionServicePort" in source
    assert "PriceAcquisitionResult" in source
    assert "PriceAcquisitionUnit" in source


def test_price_acquisition_service_does_not_import_specific_format_adapters() -> None:
    source = SERVICE_FILE.read_text(encoding="utf-8").lower()

    forbidden_markers = (
        "csvadapter",
        "xlsxadapter",
        "pdfadapter",
        "markdownadapter",
        "htmladapter",
    )

    assert not any(marker in source for marker in forbidden_markers)


def test_price_acquisition_preparation_bridges_source_material_to_acquisition_units() -> (
    None
):
    source = PREPARATION_FILE.read_text(encoding="utf-8")

    assert "PriceSourceUnit" in source
    assert "PriceAcquisitionUnit" in source
    assert "price_acquisition_unit_from_source_unit" in source
    assert "CommercialPriceAcquisitionServicePort" in source
