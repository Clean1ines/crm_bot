from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path


LEGACY_COMPILER_MODULE = "src.domain.project_plane." + "knowledge_compilation"


def _purge_imported_modules(*prefixes: str) -> None:
    for module_name in tuple(sys.modules):
        if module_name in prefixes or any(
            module_name.startswith(f"{prefix}.") for prefix in prefixes
        ):
            sys.modules.pop(module_name, None)


def _module_level_import_lines(source: str) -> tuple[str, ...]:
    lines: list[str] = []
    for line in source.splitlines():
        if line == line.lstrip() and line.startswith("from "):
            lines.append(line)
    return tuple(lines)


def test_fastapi_app_import_does_not_load_legacy_compiler_domain() -> None:
    _purge_imported_modules(
        "src.interfaces.http.app",
        "src.interfaces.http.knowledge_curation",
        "src.interfaces.http.rag_eval",
        "src.interfaces.http.webhooks",
        "src.interfaces.telegram.platform_bot",
        "src.interfaces.telegram.platform_admin.knowledge_upload",
        "src.infrastructure.db.repositories.rag_eval_repository",
        "src.domain.project_plane.knowledge_retrieval_surface",
        "src.application.dto.knowledge_dto",
        LEGACY_COMPILER_MODULE,
    )

    module = importlib.import_module("src.interfaces.http.app")

    assert getattr(module, "app") is not None
    assert LEGACY_COMPILER_MODULE not in sys.modules


def test_fastapi_app_does_not_mount_old_compiler_backed_http_surfaces() -> None:
    app_source = Path("src/interfaces/http/app.py").read_text(encoding="utf-8")

    forbidden_markers = (
        "from src.interfaces.http.knowledge_curation import",
        "from src.interfaces.http.rag_eval import",
        "app.include_router(knowledge_curation_router)",
        "app.include_router(rag_eval_router)",
    )

    for marker in forbidden_markers:
        assert marker not in app_source


def test_webhooks_do_not_import_telegram_processors_at_module_top() -> None:
    source = Path("src/interfaces/http/webhooks.py").read_text(encoding="utf-8")
    module_level_imports = _module_level_import_lines(source)

    forbidden_top_level_imports = (
        "from src.interfaces.telegram.platform_bot import process_admin_update",
        "from src.interfaces.telegram.client_bot import process_client_update",
        "from src.interfaces.telegram.manager_bot import process_manager_update",
    )

    for marker in forbidden_top_level_imports:
        assert marker not in module_level_imports

    assert "def _get_process_admin_update()" in source
    assert "def _get_process_client_update()" in source
    assert "def _get_process_manager_update()" in source


def test_fastapi_lifespan_does_not_import_knowledge_repository_at_module_top() -> None:
    module = importlib.import_module("src.interfaces.composition.fastapi_lifespan")
    source = Path(inspect.getsourcefile(module) or "").read_text(encoding="utf-8")

    before_register_builtin_tools = source.split("def register_builtin_tools", 1)[0]
    assert "knowledge_repository" not in before_register_builtin_tools
    assert "KnowledgeRepository" not in before_register_builtin_tools

    register_body = inspect.getsource(module.register_builtin_tools)

    assert (
        "src.infrastructure.db.repositories.knowledge_repository" not in register_body
    )
    assert "WorkbenchRuntimeRetrievalRepository" in register_body
    assert "KnowledgeRepository" not in register_body
