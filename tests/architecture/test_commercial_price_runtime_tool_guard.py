from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILTINS = ROOT / "src/tools/builtins.py"
LIFESPAN = ROOT / "src/interfaces/composition/fastapi_lifespan.py"
AGENT_ROOT = ROOT / "src/agent"


def test_commercial_price_lookup_tool_is_registered_in_composition_root() -> None:
    builtins_source = BUILTINS.read_text(encoding="utf-8")
    lifespan_source = LIFESPAN.read_text(encoding="utf-8")

    assert "class CommercialPriceLookupTool(Tool):" in builtins_source
    assert 'name = "commercial_price_lookup"' in builtins_source
    assert "CommercialPriceRepository" in lifespan_source
    assert "CommercialPriceLookupTool(commercial_price_repo)" in lifespan_source


def test_commercial_price_lookup_tool_uses_published_lookup_port_only() -> None:
    builtins_source = BUILTINS.read_text(encoding="utf-8")

    assert "CommercialPriceLookupPort" in builtins_source
    assert "list_published_price_facts_for_lookup" in builtins_source
    assert "lookup_price_fact(" in builtins_source
    assert "publish_price_facts(" not in builtins_source
    assert "reject_price_facts(" not in builtins_source


def test_agent_graph_does_not_call_commercial_price_lookup_yet() -> None:
    violations: list[str] = []
    for path in AGENT_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "commercial_price_lookup" in source:
            violations.append(str(path.relative_to(ROOT)))

    assert violations == []
