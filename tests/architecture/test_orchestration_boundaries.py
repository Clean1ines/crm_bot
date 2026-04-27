import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATION = ROOT / "src" / "application" / "orchestration"


def _iter_orchestration_files():
    yield from ORCHESTRATION.rglob("*.py")


def test_orchestration_does_not_import_infrastructure_or_http_clients():
    violations = []
    forbidden_modules = (
        "httpx",
        "requests",
        "aiohttp",
        "src.infrastructure",
        "src.interfaces",
    )

    for path in _iter_orchestration_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        rel = path.relative_to(ROOT)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_modules):
                        violations.append(f"{rel}:{node.lineno} import {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith(forbidden_modules):
                    violations.append(f"{rel}:{node.lineno} from {module} import ...")

    assert violations == []


def test_orchestration_does_not_read_project_settings_as_dict():
    violations = []

    forbidden_fragments = (
        "get_project_settings(",
        '.get("manager_bot_token")',
        ".get('manager_bot_token')",
        '["manager_bot_token"]',
        '.get("client_bot_token")',
        ".get('client_bot_token')",
        '["client_bot_token"]',
    )

    for path in _iter_orchestration_files():
        text = path.read_text()
        rel = path.relative_to(ROOT)

        for fragment in forbidden_fragments:
            if fragment in text:
                violations.append(
                    f"{rel}: forbidden orchestration dict/config access: {fragment}"
                )

    assert violations == []
