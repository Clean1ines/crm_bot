from pathlib import Path


LEGACY_AGENT_TOOLS_PATH = Path("src/agent") / "tools.py"

FORBIDDEN_IMPORT_MARKERS = (
    "src.agent" + ".tools",
    "from src.agent import " + "tools",
    "from src.agent" + ".tools import",
    "import src.agent" + ".tools",
)


def test_legacy_agent_tools_module_is_removed():
    """
    The agent runtime must use src.tools.registry through injected ToolRegistry.

    Legacy LangChain wrappers in the former agent tools module are intentionally removed:
    - they relied on module-global project/thread context
    - they duplicated registry behavior
    - they were not used by the LangGraph runtime
    """
    assert not LEGACY_AGENT_TOOLS_PATH.exists()


def test_agent_layer_does_not_import_legacy_agent_tools():
    """
    No runtime or test code may import the removed legacy agent tools module.

    Tool execution must go through:
    - src.tools.registry.ToolRegistry
    - injected tool_registry dependencies in agent nodes
    - composition root registration of concrete tools
    """
    violations: list[str] = []

    for root in (Path("src"), Path("tests")):
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue

            text = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN_IMPORT_MARKERS:
                if marker in text:
                    violations.append(f"{path} imports removed legacy agent tools module")

    assert violations == []
