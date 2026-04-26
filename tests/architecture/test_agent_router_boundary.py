from pathlib import Path


REMOVED_LEGACY_ROUTER_FILES = (
    Path("src/agent/schemas.py"),
    Path("src/agent/router/output_parser.py"),
)

FORBIDDEN_IMPORT_MARKERS = (
    "src.agent.schemas",
    "from src.agent.schemas import",
    "src.agent.router.output_parser",
    "from src.agent.router.output_parser import",
)

FORBIDDEN_SYMBOLS = (
    "RouterOutput",
    "IntentOutput",
    "parse_router_output",
    "parse_intent_output",
    "validate_router_output",
    "validate_intent_output",
    "build_fallback_response_from_kb",
)

ALLOWED_ROUTER_RUNTIME_IMPORTS = {
    "src/agent/nodes/intent_extractor.py",
    "src/agent/nodes/response_generator.py",
    "tests/agent/router/test_prompt_builder.py",
}


def iter_python_files():
    for root in (Path("src"), Path("tests")):
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            yield path


def test_legacy_router_parser_and_agent_schemas_are_removed():
    existing = [str(path) for path in REMOVED_LEGACY_ROUTER_FILES if path.exists()]

    assert existing == []


def test_no_runtime_code_imports_legacy_router_parser_or_agent_schemas():
    violations = []

    for path in iter_python_files():
        rel = path.as_posix()

        if rel == "tests/architecture/test_agent_router_boundary.py":
            continue

        source = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_IMPORT_MARKERS:
            if marker in source:
                violations.append(f"{rel} imports legacy router layer via {marker!r}")

    assert violations == []


def test_legacy_router_symbols_are_not_reintroduced():
    violations = []

    for path in iter_python_files():
        rel = path.as_posix()

        if rel == "tests/architecture/test_agent_router_boundary.py":
            continue

        source = path.read_text(encoding="utf-8")
        for symbol in FORBIDDEN_SYMBOLS:
            if symbol in source:
                violations.append(f"{rel} references removed legacy router symbol {symbol!r}")

    assert violations == []


def test_agent_router_package_is_prompt_helper_only():
    router_files = {
        path.as_posix()
        for path in Path("src/agent/router").rglob("*.py")
        if "__pycache__" not in path.parts
    }

    assert router_files == {
        "src/agent/router/__init__.py",
        "src/agent/router/prompt_builder.py",
        "src/agent/router/utils.py",
    }


def test_only_agent_nodes_and_prompt_tests_import_router_prompt_builder():
    violations = []

    for path in iter_python_files():
        rel = path.as_posix()

        if rel == "tests/architecture/test_agent_router_boundary.py":
            continue

        source = path.read_text(encoding="utf-8")

        if "src.agent.router.prompt_builder" not in source:
            continue

        if rel not in ALLOWED_ROUTER_RUNTIME_IMPORTS:
            violations.append(rel)

    assert violations == []
