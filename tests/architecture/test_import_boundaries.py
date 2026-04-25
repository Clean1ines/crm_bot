import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

LEGACY_FACADE_PREFIXES = {
    "src/api/",
    "src/database/",
    "src/core/",
    "src/services/",
    "src/worker.py",
    "src/main.py",
    "src/admin/",
    "src/clients/",
    "src/managers/",
}

FORBIDDEN_IMPORTS = (
    "src.database.",
    "src.api.",
    "src.admin.router",
    "src.admin.handlers",
    "src.admin.keyboards",
    "src.admin.knowledge_upload",
    "src.clients.router",
    "src.managers.router",
    "src.core.config",
    "src.core.logging",
    "src.core.lifespan",
    "src.core.model_registry",
    "src.services.orchestrator",
    "src.services.project_runtime_guards",
    "src.services.redis_client",
    "src.services.lock",
    "src.services.chunker",
    "src.services.embedding_service",
    "src.services.rag_service",
    "src.services.rate_limit_tracker",
    "src.services.model_selector",
    "src.worker",
    "src.main",
)

def _is_legacy_facade(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return any(rel == prefix or rel.startswith(prefix) for prefix in LEGACY_FACADE_PREFIXES)


def test_production_code_does_not_import_legacy_facades() -> None:
    offenders: list[str] = []

    for path in SRC.rglob("*.py"):
        if "__pycache__" in path.parts or _is_legacy_facade(path):
            continue

        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_IMPORTS:
            if forbidden in text:
                rel = path.relative_to(ROOT).as_posix()
                offenders.append(f"{rel}: {forbidden}")

    assert offenders == []


def test_legacy_facade_paths_are_absent() -> None:
    leftovers = [prefix for prefix in LEGACY_FACADE_PREFIXES if (ROOT / prefix).exists()]
    assert leftovers == []


def test_application_and_domain_do_not_import_http_framework_primitives() -> None:
    offenders: list[str] = []

    for root in (SRC / "application", SRC / "domain"):
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue

            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
            rel = path.relative_to(ROOT).as_posix()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in {"fastapi", "starlette"}:
                            offenders.append(f"{rel}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module.startswith("fastapi") or module.startswith("starlette"):
                        imported_names = ", ".join(alias.name for alias in node.names)
                        offenders.append(f"{rel}: from {module} import {imported_names}")

    assert offenders == []

def test_agent_tools_do_not_access_db_or_settings_directly():
    """Agent tool wrappers must delegate to ToolRegistry, not DB/settings."""
    import ast
    from pathlib import Path

    source_path = Path("src/agent/tools.py")
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_imports = {
        "asyncpg",
        "src.infrastructure.config.settings",
        "src.infrastructure.db.repositories.knowledge_repository",
    }

    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert not (imported_modules & forbidden_imports)
    assert "DATABASE_URL" not in source
    assert "asyncpg.connect" not in source
    assert ".connect(" not in source


def test_infrastructure_layer_does_not_import_agent_runtime():
    """Infrastructure must stay generic and must not depend on agent internals."""
    import ast
    from pathlib import Path

    violations: list[str] = []

    for path in Path("src/infrastructure").rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "src.agent" or module.startswith("src.agent."):
                    violations.append(f"{path}:{node.lineno} imports from {module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name == "src.agent" or name.startswith("src.agent."):
                        violations.append(f"{path}:{node.lineno} imports {name}")

    assert violations == []

